import hashlib
import io
import json
import random

import pytest

from app.errors import Problem
from app.services.manifests import publish_manifest
from app.services.storage import FileStore
from app.worker.runner import run_once
from tests.test_auth import session_app as session_app
from tests.test_auth import signed_client
from tests.test_jobs import worker_client as worker_client
from tests.test_uploads import pdf_bytes, upload


@pytest.fixture
def chapter(worker_client):
    identifiers = upload(worker_client, pdf_bytes(10)).json()
    db = worker_client.app.state.database
    settings = worker_client.app.state.settings
    assert run_once(db, settings)
    with db.read_conn() as connection:
        mapping = {
            row["external_id"]: row["internal_id"]
            for row in connection.execute(
                "SELECT * FROM extraction_identifiers WHERE document_id=?",
                (identifiers["document_id"],),
            )
        }
    return worker_client, identifiers, mapping


def edit(client, block_id, revision, text):
    return client.patch(
        "/blocks/" + block_id,
        json={
            "base_revision": revision,
            "operations": [{"op": "replace_text", "text": text}],
            "reason": "Synthetic reviewer correction",
        },
    )


def seed_dependents(client, document_id, block_id):
    db = client.app.state.database
    store = FileStore(client.app.state.settings.pathya_data_dir, db, min_free_bytes=0)
    asset_id, digest, _ = store.put_derived(
        document_id, "seed-audio", io.BytesIO(b"synthetic audio"), 100, "audio", "audio/wav"
    )
    with db.write_tx() as connection:
        connection.execute(
            "INSERT INTO artifacts(id,document_id,kind,block_id,dependency_revisions_json,content_hash,status,asset_id,created_at,updated_at) VALUES ('audio',?,'audio_block',?,?,?,'ready',?,'now','now')",
            (document_id, block_id, json.dumps({block_id: 1}), digest, asset_id),
        )
        connection.execute(
            "INSERT INTO chunks VALUES ('chunk',?,1,?,'','Synthetic source',2,'[]',1,'current')",
            (document_id, json.dumps([block_id])),
        )
        connection.execute(
            "INSERT INTO chunk_embeddings(chunk_id,model_id,dim,vector) VALUES ('chunk','fake',1,?)",
            (b"0000",),
        )
        user = connection.execute(
            "SELECT owner_id FROM documents WHERE id=?", (document_id,)
        ).fetchone()["owner_id"]
        connection.execute(
            "INSERT INTO answers VALUES ('answer',?,1,?,'question-hash','ai_explanation',?,'fake','test','current',0,'now')",
            (
                document_id,
                user,
                json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Synthetic claim",
                                "evidence": [{"block_id": block_id, "rev": 1}],
                            }
                        ]
                    }
                ),
            ),
        )
    return asset_id


def test_correction_invalidates_dependencies_and_publishes_fallback(chapter):
    client, ids, mapping = chapter
    block_id = mapping["damaged-minus"]
    asset_id = seed_dependents(client, ids["document_id"], block_id)
    publish_manifest(
        client.app.state.database, client.app.state.settings.pathya_data_dir, ids["document_id"], 1
    )
    old = client.get("/documents/" + ids["document_id"] + "/manifest")
    assert old.status_code == 200
    response = edit(client, block_id, 1, "The synthetic value is -5.")
    assert response.status_code == 200, response.text
    assert response.json()["document_revision"] == 2
    assert response.json()["block_revision"] == 2
    assert response.json()["stale"] == {"audio": 1, "chunks": 1, "embeddings": 1, "answers": 1}
    with client.app.state.database.read_conn() as connection:
        assert (
            connection.execute("SELECT status FROM artifacts WHERE id='audio'").fetchone()["status"]
            == "stale"
        )
        assert connection.execute(
            "SELECT status,eligible FROM chunks WHERE id='chunk'"
        ).fetchone() == {"status": "stale", "eligible": 0}
        assert (
            connection.execute(
                "SELECT status FROM chunk_embeddings WHERE chunk_id='chunk'"
            ).fetchone()["status"]
            == "stale"
        )
        assert (
            connection.execute("SELECT status FROM answers WHERE id='answer'").fetchone()["status"]
            == "stale"
        )
        assert (
            connection.execute(
                "SELECT text FROM block_versions WHERE block_id=? AND revision=1", (block_id,)
            ).fetchone()["text"]
            != "The synthetic value is -5."
        )
    assert client.get("/assets/" + asset_id).status_code == 409
    assert run_once(client.app.state.database, client.app.state.settings)
    manifest = client.get("/documents/" + ids["document_id"] + "/manifest")
    assert manifest.status_code == 200, manifest.text
    assert manifest.json()["revision"] == 2
    assert all(item.get("artifact_id") != "audio" for item in manifest.json()["artifacts"])
    assert (
        next(item for item in manifest.json()["artifacts"] if item["block_id"] == block_id)[
            "status"
        ]
        == "text_only"
    )
    assert hashlib.sha256(manifest.content).hexdigest() == manifest.headers["etag"].strip('"')
    assert (
        client.get(
            "/documents/" + ids["document_id"] + "/manifest",
            headers={"If-None-Match": manifest.headers["etag"]},
        ).status_code
        == 304
    )
    historical = client.get("/documents/" + ids["document_id"] + "/manifest?revision=1")
    assert historical.content == old.content


def test_offline_conflict_is_recorded_without_overwriting(chapter):
    client, ids, mapping = chapter
    block = mapping["paragraph-1"]
    assert edit(client, block, 1, "First accepted correction.").status_code == 200
    response = edit(client, block, 1, "Second offline correction.")
    assert response.status_code == 409
    assert response.json()["code"] == "revision_conflict"
    assert response.json()["current_text"] == "First accepted correction."
    assert response.json()["your_text"] == "Second offline correction."
    assert response.json()["your_base"] == 1
    with client.app.state.database.read_conn() as connection:
        assert (
            connection.execute(
                "SELECT count(*) AS n FROM corrections WHERE state='conflict'"
            ).fetchone()["n"]
            == 1
        )
        assert (
            connection.execute(
                "SELECT current_revision FROM documents WHERE id=?", (ids["document_id"],)
            ).fetchone()["current_revision"]
            == 2
        )


def test_failure_after_block_update_rolls_back_every_change(chapter):
    client, ids, mapping = chapter
    block = mapping["paragraph-1"]
    seed_dependents(client, ids["document_id"], block)
    with client.app.state.database.write_tx() as connection:
        connection.execute(
            "CREATE TRIGGER injected_correction_crash BEFORE INSERT ON revisions WHEN new.revision=2 BEGIN SELECT RAISE(ABORT,'injected crash'); END"
        )
    before = client.get("/blocks/" + block).json()
    response = edit(client, block, 1, "Must roll back.")
    assert response.status_code == 500
    assert client.get("/blocks/" + block).json() == before
    with client.app.state.database.read_conn() as connection:
        assert (
            connection.execute(
                "SELECT count(*) AS n FROM block_versions WHERE block_id=?", (block,)
            ).fetchone()["n"]
            == 1
        )
        assert connection.execute("SELECT count(*) AS n FROM corrections").fetchone()["n"] == 0
        assert (
            connection.execute("SELECT status FROM artifacts WHERE id='audio'").fetchone()["status"]
            == "ready"
        )
        assert (
            connection.execute(
                "SELECT current_revision FROM documents WHERE id=?", (ids["document_id"],)
            ).fetchone()["current_revision"]
            == 1
        )


def test_split_merge_preserves_historical_identifiers(chapter):
    client, ids, mapping = chapter
    block = mapping["paragraph-1"]
    response = client.patch(
        "/blocks/" + block,
        json={
            "base_revision": 1,
            "operations": [{"op": "split", "at_offsets": [20]}],
            "reason": "Split synthetic prose",
        },
    )
    assert response.status_code == 200, response.text
    successors = response.json()["successor_ids"]
    assert len(successors) == 2
    assert client.get("/blocks/" + block).json()["historical"]
    assert client.get("/blocks/" + block).json()["successor_ids"] == successors
    response = client.patch(
        "/blocks/" + successors[0],
        json={
            "base_revision": 1,
            "operations": [
                {"op": "merge", "with_block_id": successors[1], "with_base_revision": 1}
            ],
            "reason": "Merge synthetic prose",
        },
    )
    assert response.status_code == 200, response.text
    merged = response.json()["successor_ids"]
    assert len(merged) == 1
    assert client.get("/blocks/" + successors[1]).json()["successor_ids"] == merged
    with client.app.state.database.read_conn() as connection:
        assert (
            connection.execute(
                "SELECT count(*) AS n FROM edges WHERE relation='supersedes'"
            ).fetchone()["n"]
            == 4
        )


def test_review_queue_and_reextract_preserve_teacher_text(chapter):
    client, ids, mapping = chapter
    queue = client.get("/documents/" + ids["document_id"] + "/review-queue").json()["blocks"]
    assert any(item["id"] == mapping["damaged-minus"] for item in queue)
    block = mapping["paragraph-1"]
    assert edit(client, block, 1, "Teacher verified synthetic explanation.").status_code == 200
    # Finish the correction rebuild before the later extraction job.
    assert run_once(client.app.state.database, client.app.state.settings)
    job = client.post("/documents/" + ids["document_id"] + "/reextract")
    assert job.status_code == 202
    assert run_once(client.app.state.database, client.app.state.settings)
    result = client.get("/jobs/" + job.json()["job_id"]).json()
    assert result["state"] == "review_required", result
    candidate_id = result["progress"]["candidate_id"]
    candidate = client.get(
        "/documents/" + ids["document_id"] + "/candidates/" + candidate_id
    ).json()
    preserved = next(
        item for item in candidate["body"]["reconciliation"]["matches"] if item["block_id"] == block
    )
    assert preserved["action"] == "preserve_correction"
    assert preserved["text"] == "Teacher verified synthetic explanation."
    assert client.get("/blocks/" + block).json()["text_current"] == preserved["text"]
    assert client.get("/documents/" + ids["document_id"]).json()["current_revision"] == 2


def test_random_edit_sequence_never_leaves_ready_stale_audio(chapter):
    client, ids, mapping = chapter
    block = mapping["paragraph-1"]
    seed_dependents(client, ids["document_id"], block)
    store = FileStore(
        client.app.state.settings.pathya_data_dir, client.app.state.database, min_free_bytes=0
    )
    asset_id, digest, _ = store.put_derived(
        ids["document_id"], "untouched-audio", io.BytesIO(b"unchanged"), 100, "audio", "audio/wav"
    )
    with client.app.state.database.write_tx() as connection:
        connection.execute(
            "INSERT INTO artifacts(id,document_id,kind,block_id,dependency_revisions_json,content_hash,status,asset_id,created_at,updated_at) VALUES ('untouched',?,'audio_block',?,?,?,'ready',?,'now','now')",
            (
                ids["document_id"],
                mapping["paragraph-2"],
                json.dumps({mapping["paragraph-2"]: 1}),
                digest,
                asset_id,
            ),
        )
    randomizer = random.Random(12)
    for revision in range(1, 7):
        response = edit(
            client, block, revision, "Synthetic value " + str(randomizer.randint(1, 1000))
        )
        assert response.status_code == 200
        with client.app.state.database.read_conn() as connection:
            ready = list(connection.execute("SELECT * FROM artifacts WHERE status='ready'"))
            assert {item["id"] for item in ready} == {"untouched"}
            for artifact in ready:
                for block_id, expected in json.loads(artifact["dependency_revisions_json"]).items():
                    assert (
                        connection.execute(
                            "SELECT revision FROM blocks WHERE id=?", (block_id,)
                        ).fetchone()["revision"]
                        == expected
                    )


def test_invalid_operations_and_cross_document_references_are_rejected(chapter):
    client, ids, mapping = chapter
    target = mapping["paragraph-1"]
    response = client.patch(
        "/blocks/" + target,
        json={
            "base_revision": 1,
            "operations": [{"op": "replace_text", "text": "x", "unknown": True}],
            "reason": "Invalid schema",
        },
    )
    assert response.status_code == 422
    response = client.patch(
        "/blocks/" + target,
        json={
            "base_revision": 1,
            "operations": [
                {"op": "reorder", "parent_id": target, "before_block_id": mapping["heading-1"]}
            ],
            "reason": "Invalid parent",
        },
    )
    assert response.status_code == 422
    assert client.get("/blocks/" + target).json()["revision"] == 1


def test_all_metadata_and_order_operations(chapter):
    client, ids, mapping = chapter

    def operation(block, operations):
        revision = client.get("/blocks/" + block).json()["revision"]
        response = client.patch(
            "/blocks/" + block,
            json={
                "base_revision": revision,
                "operations": operations,
                "reason": "Synthetic contract operation",
            },
        )
        assert response.status_code == 200, response.text
        return client.get("/blocks/" + block).json()

    paragraph = mapping["paragraph-1"]
    moved = operation(
        paragraph, [{"op": "reorder", "parent_id": None, "before_block_id": mapping["heading-1"]}]
    )
    assert moved["order_key"] < client.get("/blocks/" + mapping["heading-1"]).json()["order_key"]
    assert operation(paragraph, [{"op": "set_language", "lang": "hi"}])["lang"] == "hi"
    assert (
        operation(mapping["paragraph-2"], [{"op": "set_type", "type": "heading"}])["type"]
        == "heading"
    )
    flagged = mapping["damaged-minus"]
    assert operation(flagged, [{"op": "set_language", "lang": "en"}])["critical_flag"]
    assert not operation(flagged, [{"op": "mark_reviewed"}])["critical_flag"]
    figure = operation(
        mapping["figure-1"],
        [
            {
                "op": "set_alt_text",
                "short": "A synthetic blue square beside a red circle.",
                "extended": "Synthetic demonstration only.",
            },
            {"op": "mark_reviewed"},
        ],
    )
    assert figure["metadata"]["alt_text_extended"] == "Synthetic demonstration only."
    equation = client.get("/blocks/" + mapping["equation-1"]).json()
    assert (
        operation(
            mapping["equation-1"],
            [
                {
                    "op": "set_mathml",
                    "mathml": equation["metadata"]["mathml"],
                    "spoken_fallback": "Two plus two equals four.",
                },
                {"op": "mark_reviewed"},
            ],
        )["status"]
        == "reviewed"
    )
    table = operation(
        mapping["table-1"],
        [
            {
                "op": "set_table_headers",
                "header_cell_ids": [mapping["header-kind"], mapping["header-count"]],
            }
        ],
    )
    assert table["metadata"]["header_cell_ids"] == [mapping["header-kind"], mapping["header-count"]]
    assert client.get("/blocks/" + mapping["cell-count"]).json()["metadata"]["header_cell_ids"] == [
        mapping["header-count"]
    ]


@pytest.mark.parametrize(
    "user_id,expected",
    [(None, 401), ("other", 404), ("reader", 403), ("reviewer", 200), ("u", 200), ("admin", 404)],
)
def test_actual_correction_route_role_matrix(session_app, user_id, expected):
    with signed_client(session_app, user_id) as client:
        assert edit(client, "b", 1, "Synthetic permitted edit.").status_code == expected


def test_manifest_rejects_invalid_asset_checksum(chapter):
    client, ids, mapping = chapter
    asset_id = seed_dependents(client, ids["document_id"], mapping["paragraph-1"])
    with client.app.state.database.write_tx() as connection:
        before = connection.execute("SELECT count(*) AS n FROM manifests").fetchone()["n"]
        connection.execute("UPDATE assets SET sha256=? WHERE id=?", ("bad-checksum", asset_id))
    with pytest.raises(Problem, match="manifest_asset_invalid"):
        publish_manifest(
            client.app.state.database,
            client.app.state.settings.pathya_data_dir,
            ids["document_id"],
            1,
        )
    with client.app.state.database.read_conn() as connection:
        assert connection.execute("SELECT count(*) AS n FROM manifests").fetchone()["n"] == before
