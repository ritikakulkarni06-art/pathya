import asyncio

import httpx
import pytest

from app.adapters.llm import GeminiClient
from app.config import Settings
from app.errors import Problem
from app.main import create_app
from app.services.auth import current_user
from app.services.retrieval.index import build_index
from app.services.storage import FileStore
from tests.test_jobs import worker_client as worker_client
from tests.test_llm import llm_settings as llm_settings
from tests.test_revisions import chapter as chapter
from tests.test_uploads import pdf_bytes, upload


def test_llm_timeout_then_budget_refusal_keeps_reading_and_search(
    seeded, worker_client, llm_settings
):
    client = worker_client
    client.app.dependency_overrides[current_user] = lambda: {"id": "u", "role": "user"}
    llm_settings.api_budget_inr_hard_cap = 0.0064
    llm_settings.document_budget_inr_hard_cap = 0.0064
    client.app.state.settings = llm_settings
    build_index(seeded, llm_settings, "d")
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    client.app.state.llm_client = GeminiClient(
        llm_settings, seeded, "d", "u", transport=httpx.MockTransport(timeout)
    )
    payload = {"document_id": "d", "question": "Synthetic"}
    first = client.post("/questions", json=payload).json()
    second = client.post("/questions", json=payload).json()
    assert first["reason"] == "assistant_unavailable" and first["evidence"]
    assert second["reason"] == "budget_exhausted" and second["evidence"]
    assert len(calls) == 1
    assert client.get("/documents/d/content").status_code == 200
    assert client.get("/documents/d/search", params={"q": "Synthetic"}).json()["results"]


def test_disk_failure_mid_source_write_leaves_no_partial_upload(worker_client, monkeypatch):
    calls = [0]
    original = FileStore._space

    def no_space(self, additional=0):
        calls[0] += 1
        if calls[0] >= 3:
            raise Problem(507, "storage_full", "Synthetic disk-full drill.")
        return original(self, additional)

    monkeypatch.setattr(FileStore, "_space", no_space)
    response = upload(worker_client, pdf_bytes(1))
    assert response.status_code == 507
    assert worker_client.get("/documents").json()["documents"] == []
    assert list((worker_client.app.state.settings.pathya_data_dir / "tmp").iterdir()) == []


@pytest.mark.asyncio
async def test_concurrent_http_corrections_accept_one_and_record_one_conflict(seeded):
    settings = Settings(
        _env_file=None,
        pathya_env="test",
        pathya_data_dir=seeded.path.parent,
        pathya_db_path=seeded.path,
    )
    app = create_app(settings)
    app.dependency_overrides[current_user] = lambda: {"id": "u", "role": "user"}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:

            def payload(text):
                return {
                    "base_revision": 1,
                    "operations": [{"op": "replace_text", "text": text}],
                    "reason": "Synthetic conflict drill",
                }

            responses = await asyncio.gather(
                client.patch("/blocks/b", json=payload("First proposed source.")),
                client.patch("/blocks/b", json=payload("Second proposed source.")),
            )
    assert sorted(r.status_code for r in responses) == [200, 409]
    with seeded.read_conn() as c:
        assert (
            c.execute("SELECT current_revision FROM documents WHERE id='d'").fetchone()[
                "current_revision"
            ]
            == 2
        )
        assert {r["state"] for r in c.execute("SELECT state FROM corrections")} == {
            "accepted",
            "conflict",
        }


def test_interrupted_package_publication_preserves_previous_package(chapter, monkeypatch):
    client, ids, mapping = chapter
    url = "/documents/" + ids["document_id"] + "/packages"
    previous = client.post(url)
    assert previous.status_code == 201
    original = FileStore.put_derived

    def interrupted(
        self,
        document_id,
        artifact_id,
        stream,
        maximum,
        kind="audio",
        mime="application/octet-stream",
    ):
        result = original(self, document_id, artifact_id, stream, maximum, kind, mime)
        if kind == "package":
            raise Problem(507, "storage_full", "Synthetic interrupted-package drill.")
        return result

    monkeypatch.setattr(FileStore, "put_derived", interrupted)
    assert client.post(url).status_code == 507
    old = client.get(url + "/" + previous.json()["id"])
    assert old.status_code == 200 and old.headers["ETag"].strip('"') == previous.json()["sha256"]
