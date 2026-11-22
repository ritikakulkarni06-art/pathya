import hashlib
import json

import httpx
import pytest

from app.adapters.embeddings import FakeEmbeddingProvider
from app.adapters.llm import FakeLLM
from app.main import create_app
from app.services.retrieval.index import build_index
from scripts.seed_demo import demo_settings, drain
from tests.test_uploads import pdf_bytes


def explanation(block_id, revision, document_revision, text):
    return {
        "origin": "ai_explanation",
        "document_revision": document_revision,
        "claims": [
            {"text": json.dumps(text), "evidence": [{"block_id": block_id, "rev": revision}]}
        ],
        "abstain": False,
        "uncertainty_notes": [],
        "model_id": "fake-scripted-v1",
    }


@pytest.mark.asyncio
async def test_golden_upload_review_correct_rebuild_answer_package_delete(tmp_path):
    settings = demo_settings(tmp_path / "golden")
    app = create_app(settings)
    embedder = FakeEmbeddingProvider()
    app.state.embedding_provider = embedder
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            uploaded = await client.post(
                "/documents",
                files={"file": ("synthetic.pdf", pdf_bytes(10), "application/pdf")},
                data={
                    "title": "Synthetic golden flow",
                    "rights_note": "Synthetic authorized development fixture",
                    "languages": "en,hi",
                },
            )
            assert uploaded.status_code == 202
            identifiers = uploaded.json()
            document_id = identifiers["document_id"]
            drain(app.state.database, settings)
            status = await client.get("/jobs/" + identifiers["job_id"])
            assert status.json()["state"] == "review_required"
            review = await client.get("/documents/" + document_id + "/review-queue")
            assert review.json()["blocks"] and review.json()["blocks"][0]["critical_flag"]
            with app.state.database.read_conn() as c:
                block_id = c.execute(
                    "SELECT internal_id FROM extraction_identifiers WHERE document_id=? AND external_id='column-left'",
                    (document_id,),
                ).fetchone()["internal_id"]
            original = (await client.get("/blocks/" + block_id)).json()["text_current"]
            assert (await client.post("/blocks/" + block_id + "/audio", json={})).status_code == 202
            drain(app.state.database, settings)
            audio = (await client.get("/blocks/" + block_id + "/audio")).json()
            assert audio["synthetic"] and audio["status"] == "ready"
            build_index(app.state.database, settings, document_id, embedder=embedder)
            app.state.llm_client = FakeLLM([explanation(block_id, 1, 1, original)])
            old_answer = (
                await client.post(
                    "/questions", json={"document_id": document_id, "question": "sunlight"}
                )
            ).json()
            assert not old_answer["abstain"]
            corrected = await client.patch(
                "/blocks/" + block_id,
                json={
                    "base_revision": 1,
                    "operations": [
                        {
                            "op": "replace_text",
                            "text": "Verified chlorophyll passage for the synthetic chapter.",
                        }
                    ],
                    "reason": "Synthetic golden correction",
                },
            )
            assert corrected.status_code == 200
            counts = corrected.json()["stale"]
            assert all(counts[key] >= 1 for key in ["audio", "chunks", "embeddings", "answers"])
            historical = (await client.get("/answers/" + old_answer["id"])).json()
            assert historical["stale"] and historical["current_document_revision"] == 2
            drain(app.state.database, settings)
            build_index(app.state.database, settings, document_id, embedder=embedder)
            manifest = await client.get("/documents/" + document_id + "/manifest")
            assert manifest.status_code == 200 and manifest.json()["revision"] == 2
            assert hashlib.sha256(manifest.content).hexdigest() == manifest.headers["ETag"].strip(
                '"'
            )
            assert all(a["status"] != "stale" for a in manifest.json()["artifacts"])
            app.state.llm_client = FakeLLM(
                [
                    explanation(
                        block_id, 2, 2, "Verified chlorophyll passage for the synthetic chapter."
                    )
                ]
            )
            current = (
                await client.post(
                    "/questions",
                    json={"document_id": document_id, "revision": 2, "question": "chlorophyll"},
                )
            ).json()
            assert not current["abstain"] and current["claims"][0]["evidence"] == [
                {"block_id": block_id, "rev": 2}
            ]
            unsupported = (
                await client.post(
                    "/questions", json={"document_id": document_id, "question": "unicorn habitat"}
                )
            ).json()
            assert unsupported["abstain"]
            package = await client.post("/documents/" + document_id + "/packages")
            assert package.status_code == 201 and package.json()["revision"] == 2
            receipt = (await client.delete("/documents/" + document_id)).json()
            assert (await client.get("/documents/" + document_id + "/manifest")).status_code == 410
            assert (await client.get("/blocks/" + block_id)).status_code == 404
            drain(app.state.database, settings)
            assert (await client.get(receipt["status_url"])).json()["status"] == "complete"
            assert not (settings.pathya_data_dir / "sources" / document_id).exists()
            assert not (settings.pathya_data_dir / "derived" / document_id).exists()
