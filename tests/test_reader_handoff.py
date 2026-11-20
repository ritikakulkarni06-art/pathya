import io
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from PIL import Image

from app.clock import now_utc
from app.db.repos import jobs
from app.schemas.p1.models import Document
from app.services.ingest import import_extraction
from app.services.retrieval.eligibility import is_eligible
from app.services.retrieval.index import build_index
from app.worker.runner import run_once
from tests.test_auth import session_app as session_app
from tests.test_auth import signed_client
from tests.test_jobs import worker_client as worker_client
from tests.test_revisions import edit
from tests.test_uploads import image_bytes, pdf_bytes, upload
from tests.test_uploads import upload_client as upload_client


def test_reader_jobs_and_owner_retry_preserve_privacy_and_attempt_history(session_app):
    db = session_app.state.database
    with db.write_tx() as connection:
        public_job = jobs.enqueue(
            connection, "d", "build_index", {"revision": 1}, 2, None, now_utc()
        )
        private_job = jobs.enqueue(
            connection, "d", "build_audio", {"user_id": "reader"}, 2, None, now_utc()
        )
        connection.execute(
            "UPDATE jobs SET state='failed',attempts=2,error_message='Processing stopped.' WHERE id=?",
            (public_job,),
        )
    with signed_client(session_app, "other") as client:
        assert client.get("/jobs").json() == []
    with signed_client(session_app, "reader") as client:
        assert {row["id"] for row in client.get("/jobs").json()} == {public_job, private_job}
        assert client.post(f"/jobs/{public_job}/retry").status_code == 403
    with signed_client(session_app, "u") as client:
        assert [row["id"] for row in client.get("/jobs").json()] == [public_job]
        assert client.get(f"/jobs/{private_job}").status_code == 404
        retry = client.post(f"/jobs/{public_job}/retry")
        assert retry.status_code == 202
        assert retry.json()["state"] == "queued" and retry.json()["attempts"] == 0
        assert client.post(f"/jobs/{public_job}/retry").json()["id"] == retry.json()["id"]
        assert client.get(f"/jobs/{public_job}").json()["attempts"] == 2


def test_usage_is_private_and_durable_and_history_only_shows_accepted_edits(session_app):
    session_app.state.settings.daily_question_limit = 1
    with signed_client(session_app, "u") as client:
        assert client.get("/usage").json() == {"limit": 1, "remaining": 1}
        assert (
            client.post(
                "/questions", json={"document_id": "missing", "question": "Sky?"}
            ).status_code
            == 404
        )
        question = {"document_id": "d", "question": "What is this?"}
        asked = client.post("/questions", json=question)
        assert asked.status_code == 200
        assert asked.json()["usage"]["remaining"] == 0
        limited = client.post("/questions", json=question)
        assert limited.status_code == 429 and limited.json()["code"] == "daily_question_limit"
        assert edit(client, "b", 1, "Updated text.").status_code == 200
        assert edit(client, "b", 1, "Stale text.").status_code == 409
        assert client.get("/documents/d/revisions").json()[0]["after"] == "Updated text."
    with signed_client(session_app, "reader") as client:
        history = client.get("/documents/d/revisions").json()
        assert len(history) == 1 and history[0]["before"] == "Synthetic text"
        assert client.get("/usage").json()["remaining"] == 1
    with signed_client(session_app, "other") as client:
        assert client.get("/documents/d/revisions").status_code == 404


def test_source_image_preview_and_crop_use_the_uploaded_working_image(upload_client):
    doc = upload(upload_client, image_bytes(), name="page.png").json()["document_id"]
    db = upload_client.app.state.database
    fixture = json.loads(Path("tests/fixtures/chapter_demo.json").read_bytes())
    page = fixture["pages"][0]
    page.update(width=10, height=10, rotation=0)
    source_block = next(
        block
        for block in fixture["blocks"]
        if block["page_id"] == page["id"] and block["parent_id"] is None
    )
    source_block.update(parent_id=None, metadata={}, bbox=[0, 0, 0.5, 0.5])
    fixture.update(pages=[page], blocks=[source_block], edges=[])
    imported = import_extraction(db, doc, fixture)
    page_id, block_id = (imported.id_map[item["id"]] for item in (page, source_block))
    preview = upload_client.get(f"/documents/{doc}/pages/{page_id}/preview").json()
    assert upload_client.get(preview["image_url"]).status_code == 200
    crop = upload_client.get(f"/blocks/{block_id}/crop")
    assert crop.status_code == 200
    assert Image.open(io.BytesIO(crop.content)).size == (5, 5)


def test_p1_worker_import_current_content_revision_and_uncertain_pages(worker_client):
    settings = worker_client.app.state.settings
    settings.extraction_adapter = "p1:tests.fixtures.p1_extractor:extract"
    settings.segmenter = "pathya"
    source = upload(worker_client, pdf_bytes(2)).json()
    doc_id = source["document_id"]
    db = worker_client.app.state.database
    assert run_once(db, settings)
    processed = worker_client.get(f"/jobs/{source['job_id']}")
    assert processed.json()["state"] == "review_required", processed.text
    response = worker_client.get(f"/documents/{doc_id}/content")
    assert response.headers["X-Document-Revision"] == "1"
    body = response.json()
    fixture_root = Path("tests/fixtures/p1_contract")
    schema = json.loads((fixture_root / "pathya_content.v1.1.0.schema.json").read_bytes())
    Draft202012Validator(schema).validate(body)
    assert str(Document.model_validate(body).id) == doc_id
    partial_id = next(page["id"] for page in body["pages"] if page["status"] == "partial")
    block = next(
        block
        for block in body["blocks"]
        if block["block_type"] == "paragraph" and block["page_id"] != partial_id
    )
    with db.read_conn() as connection:
        receipt = connection.execute(
            "SELECT p1_source_json FROM extraction_imports WHERE document_id=?", (doc_id,)
        ).fetchone()
        assert json.loads(receipt["p1_source_json"])["source_asset"]["uri"].startswith("https:")
        assert body["source_asset"]["uri"].startswith("/assets/")
        affected = connection.execute(
            "SELECT * FROM blocks WHERE page_id=?", (partial_id,)
        ).fetchall()
        assert affected and all(not is_eligible(row) for row in affected)
    changed = edit(worker_client, block["id"], 1, "First.  Second.")
    assert changed.status_code == 200, changed.text
    newer = worker_client.get(f"/documents/{doc_id}/content")
    assert newer.headers["X-Document-Revision"] == "2"
    Draft202012Validator(schema).validate(newer.json())
    Document.model_validate(newer.json())
    assert (
        next(item for item in newer.json()["blocks"] if item["id"] == block["id"])["current_text"]
        == "First.  Second."
    )
    assert worker_client.get(f"/blocks/{block['id']}").json()["sentences"] == [
        {"start": 0, "end": 8},
        {"start": 8, "end": 15},
    ]
    build_index(db, settings, doc_id)
    with db.read_conn() as connection:
        chunks = connection.execute(
            "SELECT block_ids_json FROM chunks WHERE document_id=?", (doc_id,)
        ).fetchall()
    assert not (
        {row["id"] for row in affected}
        & {bid for chunk in chunks for bid in json.loads(chunk["block_ids_json"])}
    )
    preview = worker_client.get(f"/documents/{doc_id}/pages/{partial_id}/preview").json()
    assert preview["source_url"].endswith("#page=2") and preview["image_url"] is None
