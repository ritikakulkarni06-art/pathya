import hashlib
import io
import wave

import pytest

from app.adapters.speech import SpeechClip, StubSpeechProvider, segment
from app.errors import Problem
from app.schemas.speech import GlossaryRequest
from app.services.manifests import publish_manifest
from app.services.packages import build_package
from app.services.speech import _matches, build_block, set_glossary
from tests.test_jobs import worker_client as worker_client
from tests.test_revisions import chapter as chapter
from tests.test_revisions import edit


class CountingSpeech(StubSpeechProvider):
    def __init__(self):
        self.calls = 0
        self.seen = []

    def synthesize(self, units, voice, language):
        self.calls += 1
        self.seen.extend(units)
        return super().synthesize(units, voice, language)


def test_cache_sentence_offsets_wave_and_range(chapter):
    client, ids, mapping = chapter
    settings = client.app.state.settings
    settings.speech_provider = "stub"
    speaker = CountingSpeech()
    block = mapping["column-left"]
    first = build_block(client.app.state.database, settings, block, "default", speaker=speaker)
    assert first["synthetic"]
    assert (
        build_block(client.app.state.database, settings, block, "default", speaker=speaker) == first
    )
    assert speaker.calls == 1
    source = client.get("/blocks/" + block).json()["text_current"]
    unit = first["units"][0]
    assert source[unit["text_offset_start"] : unit["text_offset_end"]] == speaker.seen[0].text
    downloaded = client.get("/assets/" + unit["clip_asset_id"])
    assert downloaded.status_code == 200, downloaded.text
    with wave.open(io.BytesIO(downloaded.content), "rb") as stream:
        assert stream.getframerate() == 8000
        assert stream.getnframes() * 1000 // 8000 == unit["duration_ms"]
    ranged = client.get("/assets/" + unit["clip_asset_id"], headers={"Range": "bytes=0-15"})
    assert ranged.status_code == 206
    assert ranged.content == downloaded.content[:16]
    assert ranged.headers["content-range"].startswith("bytes 0-15/")
    ready = client.get("/blocks/" + block + "/audio")
    assert ready.status_code == 200
    assert (
        ready.json()["text_sha256"]
        == first["text_sha256"]
        == hashlib.sha256(source.encode()).hexdigest()
    )
    assert ready.json()["segmenter"] == first["segmenter"] == settings.active_segmenter_version
    assert edit(client, block, 1, "The synthetic sunlight value changed.").status_code == 200
    assert client.get("/blocks/" + block + "/audio").status_code == 409
    assert client.get("/assets/" + unit["clip_asset_id"]).status_code == 409


def test_glossary_scope_and_only_affected_cache_changes(chapter):
    client, ids, mapping = chapter
    settings = client.app.state.settings
    settings.speech_provider = "stub"
    db = client.app.state.database
    speaker = CountingSpeech()
    left = build_block(db, settings, mapping["column-left"], "default", speaker=speaker)
    right = build_block(db, settings, mapping["column-right"], "default", speaker=speaker)
    assert speaker.calls == 2
    owner = client.get("/auth/me").json()["id"]
    term = set_glossary(
        db,
        ids["document_id"],
        owner,
        GlossaryRequest(term="sunlight", language="en", spoken_alias="sun light"),
        settings,
    )
    with db.read_conn() as connection:
        stale = {
            row["block_id"]
            for row in connection.execute("SELECT block_id FROM artifacts WHERE status='stale'")
        }
    assert mapping["column-left"] in stale
    assert mapping["column-right"] not in stale
    assert build_block(db, settings, mapping["column-right"], "default", speaker=speaker) == right
    assert speaker.calls == 2
    regenerated = build_block(db, settings, mapping["column-left"], "default", speaker=speaker)
    assert speaker.calls == 3
    assert regenerated["glossary_hash"] != left["glossary_hash"]
    assert speaker.seen[-1].alias_applied
    assert "sun light" in speaker.seen[-1].text
    assert "sunlight" in client.get("/blocks/" + mapping["column-left"]).json()["text_current"]
    assert (
        client.delete("/documents/" + ids["document_id"] + "/glossary?term_id=" + term).status_code
        == 204
    )
    assert _matches("lead, leading and leader", "lead")
    assert not _matches("leading and leader", "lead")
    assert _matches(
        "\u092a\u094d\u0930\u0915\u093e\u0936\u0964", "\u092a\u094d\u0930\u0915\u093e\u0936"
    )
    assert not _matches(
        "\u092a\u094d\u0930\u0915\u093e\u0936\u093f\u0924", "\u092a\u094d\u0930\u0915\u093e\u0936"
    )


def test_review_only_revisions_preserve_audio_and_offline_package(chapter):
    client, ids, mapping = chapter
    settings = client.app.state.settings
    settings.speech_provider = "stub"
    database = client.app.state.database
    document_id = ids["document_id"]
    block_id = mapping["column-left"]
    speaker = CountingSpeech()
    audio = build_block(database, settings, block_id, "default", speaker=speaker)
    publish_manifest(database, settings.pathya_data_dir, document_id, 1)
    owner = client.get("/auth/me").json()["id"]
    package = build_package(database, settings, document_id, owner)
    package_url = f"/documents/{document_id}/packages/{package['id']}"
    package_asset_url = f"/assets/{package['asset_id']}"
    clip_url = f"/assets/{audio['units'][0]['clip_asset_id']}"
    original_package = client.get(package_url)
    assert original_package.status_code == 200
    assert client.get(clip_url).status_code == 200

    for revision in (1, 2):
        review = client.patch(
            f"/blocks/{block_id}",
            json={
                "base_revision": revision,
                "operations": [{"op": "mark_reviewed"}],
                "reason": "Confirmed the source passage",
            },
        )
        assert review.status_code == 200, review.text
        assert review.json()["document_revision"] == revision + 1
        assert review.json()["block_revision"] == revision + 1
        assert review.json()["stale"]["audio"] == 0

    assert build_block(database, settings, block_id, "default", speaker=speaker) == audio
    assert speaker.calls == 1
    ready_audio = client.get(f"/blocks/{block_id}/audio")
    assert ready_audio.status_code == 200, ready_audio.text
    assert ready_audio.json() == audio
    assert client.get(clip_url).status_code == 200
    saved_package = client.get(package_url)
    assert saved_package.status_code == 200, saved_package.text
    assert saved_package.headers["etag"] == original_package.headers["etag"]
    assert saved_package.content == original_package.content
    assert client.get(package_asset_url).status_code == 200

    correction = client.patch(
        f"/blocks/{block_id}",
        json={
            "base_revision": 3,
            "operations": [
                {"op": "replace_text", "text": "A changed passage."},
                {"op": "mark_reviewed"},
            ],
            "reason": "Corrected the passage and confirmed the edit",
        },
    )
    assert correction.status_code == 200, correction.text
    assert client.get(f"/blocks/{block_id}/audio").status_code == 409
    assert client.get(clip_url).status_code == 409
    assert client.get(package_url).status_code == 409
    assert client.get(package_asset_url).status_code == 409


def test_voice_unavailable_and_paid_budget_fallback(chapter):
    client, ids, mapping = chapter
    settings = client.app.state.settings
    result = build_block(
        client.app.state.database,
        settings,
        mapping["column-left"],
        "unavailable",
        speaker=StubSpeechProvider(),
    )
    assert result["status"] == "text_only"
    assert result["reason"] == "voice_unavailable"

    class PaidSpeech(CountingSpeech):
        paid = True

    paid = PaidSpeech()
    with pytest.raises(Problem, match="budget_exhausted"):
        build_block(
            client.app.state.database, settings, mapping["column-right"], "default", speaker=paid
        )
    assert paid.calls == 0


def test_personal_overrides_are_not_shared_through_assets_or_manifest(chapter):
    client, ids, mapping = chapter
    settings = client.app.state.settings
    settings.speech_provider = "stub"
    db = client.app.state.database
    with db.write_tx() as connection:
        connection.execute(
            "INSERT INTO users VALUES ('reader','reader@example.test',NULL,'user','now')"
        )
        owner = connection.execute(
            "SELECT owner_id FROM documents WHERE id=?", (ids["document_id"],)
        ).fetchone()["owner_id"]
        connection.execute(
            "INSERT INTO document_grants VALUES (?, 'reader','reader',?,'now')",
            (ids["document_id"], owner),
        )
    set_glossary(
        db,
        ids["document_id"],
        "reader",
        GlossaryRequest(
            term="sunlight", language="en", scope="user", spoken_alias="private personal alias"
        ),
        settings,
    )
    personal = build_block(
        db,
        settings,
        mapping["column-left"],
        "default",
        user_id="reader",
        speaker=StubSpeechProvider(),
    )
    asset = personal["units"][0]["clip_asset_id"]
    assert client.get("/assets/" + asset).status_code in {404, 409}
    manifest = publish_manifest(db, settings.pathya_data_dir, ids["document_id"], 1)
    assert asset not in manifest["body_json"]
    from app.services.auth import current_user

    client.app.dependency_overrides[current_user] = lambda: {"id": "reader", "role": "user"}
    assert client.get("/assets/" + asset).status_code == 200
    assert client.get("/blocks/" + mapping["column-left"] + "/audio").status_code == 200
    client.app.dependency_overrides.clear()


def test_package_hash_download_and_size_cap_preserve_old_package(chapter):
    client, ids, mapping = chapter
    db = client.app.state.database
    settings = client.app.state.settings
    owner = client.get("/auth/me").json()["id"]
    package = build_package(db, settings, ids["document_id"], owner)
    response = client.get("/documents/" + ids["document_id"] + "/packages/" + package["id"])
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1
    assert response.json()["model_downloads_included"] is False
    assert response.headers["etag"].strip('"') == package["sha256"]
    settings.package_max_mb = 1

    class LargeSpeech(StubSpeechProvider):
        engine_version = "stub-large-test-v1"

        def synthesize(self, units, voice, language):
            clips = []
            for unit in units:
                data = io.BytesIO()
                with wave.open(data, "wb") as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(8000)
                    stream.writeframes(bytes(8000 * 2 * 80))
                clips.append(SpeechClip(unit.unit_id, data.getvalue(), "audio/wav", 80000))
            return clips

    build_block(db, settings, mapping["column-left"], "default", speaker=LargeSpeech())
    publish_manifest(db, settings.pathya_data_dir, ids["document_id"], 1)
    with pytest.raises(Problem, match="package_too_large"):
        build_package(db, settings, ids["document_id"], owner)
    assert (
        client.get("/documents/" + ids["document_id"] + "/packages/" + package["id"]).status_code
        == 200
    )


def test_demo_segmenter_preserves_hindi_danda_offsets(chapter):
    client, ids, mapping = chapter
    block = client.get("/blocks/" + mapping["paragraph-7"]).json()
    units = segment(block, client.app.state.settings)
    assert len(units) == 2
    for unit in units:
        assert block["text_current"][unit.offset_start : unit.offset_end] == unit.text


def test_budget_failed_worker_still_publishes_text_fallback(chapter):
    from app.worker.runner import run_once

    client, ids, mapping = chapter
    client.app.state.settings.speech_provider = "python:tests.fixtures.paid_speech:PaidSpeech"
    response = client.post("/blocks/" + mapping["column-left"] + "/audio", json={})
    assert response.status_code == 202
    assert run_once(client.app.state.database, client.app.state.settings)
    job = client.get("/jobs/" + response.json()["job_id"]).json()
    assert job["state"] == "failed"
    assert job["last_error_code"] == "budget_exhausted"
    assert job["attempts"] == 1
    assert client.get("/documents/" + ids["document_id"] + "/content").status_code == 200
    assert client.get("/documents/" + ids["document_id"] + "/manifest").status_code == 200
    assert (
        client.get("/blocks/" + mapping["column-left"] + "/audio").json()["reason"]
        == "budget_exhausted"
    )


def test_audio_and_package_records_are_immutable(chapter):
    import sqlite3

    client, ids, mapping = chapter
    database = client.app.state.database
    settings = client.app.state.settings
    build_block(database, settings, mapping["column-left"], "default", speaker=StubSpeechProvider())
    owner = client.get("/auth/me").json()["id"]
    build_package(database, settings, ids["document_id"], owner)
    for statement in [
        "UPDATE audio_manifests SET body_json='{}'",
        "DELETE FROM audio_manifests",
        "UPDATE packages SET body_json='{}'",
        "DELETE FROM packages",
    ]:
        with pytest.raises(sqlite3.IntegrityError):
            with database.write_tx() as connection:
                connection.execute(statement)
