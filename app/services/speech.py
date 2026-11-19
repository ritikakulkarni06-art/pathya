import hashlib
import io
import json
import re
import unicodedata
from dataclasses import replace
from typing import Any
from uuid import uuid4

from app.adapters.speech import SpeechProvider, SpeechUnavailable, provider, segment
from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.db.repos import jobs
from app.errors import Problem
from app.schemas.content import Block
from app.schemas.speech import GlossaryRequest
from app.services.access import check_document
from app.services.manifests import artifact_current, assert_job_lease
from app.services.storage import FileStore


def glossary(database: Database, document_id: str, user_id: str | None) -> list[dict[str, Any]]:
    with database.read_conn() as connection:
        rows = list(
            connection.execute(
                "SELECT * FROM glossary_terms WHERE document_id=? OR (scope='user' AND user_id=?) ORDER BY scope,term,language",
                (document_id, user_id),
            )
        )
    merged = {(row["term"].casefold(), row["language"]): row for row in rows}
    return list(merged.values())


def cache_key(
    block: dict[str, Any],
    terms: list[dict[str, Any]],
    voice: str,
    engine: str,
    segmenter_version: str,
) -> tuple[str, str]:
    overrides = [
        {key: row[key] for key in ("term", "language", "spoken_alias", "phoneme")}
        for row in terms
        if row["language"] == block["lang"] and _matches(block["text_current"], row["term"])
    ]
    overrides.sort(key=lambda row: (row["term"], row["spoken_alias"]))
    glossary_hash = hashlib.sha256(json.dumps(overrides, sort_keys=True).encode()).hexdigest()
    key = hashlib.sha256(
        json.dumps(
            [
                block["id"],
                block["revision"],
                hashlib.sha256(block["text_current"].encode()).hexdigest(),
                block["lang"],
                voice,
                engine,
                segmenter_version,
                glossary_hash,
            ]
        ).encode()
    ).hexdigest()
    return key, glossary_hash


def _word_character(value: str) -> bool:
    return (
        value == "_"
        or ord(value) in {0x200C, 0x200D}
        or unicodedata.category(value)[0] in {"L", "M", "N"}
    )


def _whole_match(text: str, match: re.Match[str]) -> bool:
    return not (match.start() and _word_character(text[match.start() - 1])) and not (
        match.end() < len(text) and _word_character(text[match.end()])
    )


def _matches(text: str, term: str) -> bool:
    return any(
        _whole_match(text, match) for match in re.finditer(re.escape(term), text, re.IGNORECASE)
    )


def set_glossary(
    database: Database, document_id: str, user_id: str, payload: GlossaryRequest, settings: Settings
) -> str:
    if payload.phoneme:
        raise Problem(
            422,
            "phoneme_unsupported",
            "This adapter contract supports spoken aliases. Phoneme markup needs a separately tested provider extension.",
        )
    with database.write_tx() as connection:
        check_document(
            connection,
            document_id,
            user_id,
            "reviewer" if payload.scope == "document" else "reader",
        )
        row = connection.execute(
            "SELECT id FROM glossary_terms WHERE term=? AND language=? AND scope=? AND document_id IS ? AND user_id IS ?",
            (
                payload.term,
                payload.language,
                payload.scope,
                document_id if payload.scope == "document" else None,
                user_id if payload.scope == "user" else None,
            ),
        ).fetchone()
        term_id = row["id"] if row else str(uuid4())
        if row:
            connection.execute(
                "UPDATE glossary_terms SET spoken_alias=?,phoneme=? WHERE id=?",
                (payload.spoken_alias, payload.phoneme, term_id),
            )
        else:
            connection.execute(
                "INSERT INTO glossary_terms VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    term_id,
                    document_id if payload.scope == "document" else None,
                    user_id if payload.scope == "user" else None,
                    payload.term,
                    payload.language,
                    payload.scope,
                    payload.spoken_alias,
                    payload.phoneme,
                    now_utc(),
                ),
            )
        _invalidate_glossary(
            connection, document_id, user_id, payload.scope, payload.term, payload.language
        )
        jobs.enqueue(
            connection,
            document_id,
            "build_audio",
            {"user_id": user_id if payload.scope == "user" else None},
            settings.job_max_attempts,
            None,
            now_utc(),
        )
        return str(term_id)


def _invalidate_glossary(
    connection: Any, document_id: str, user_id: str, scope: str, term: str, language: str
) -> None:
    if scope == "document":
        blocks = list(
            connection.execute(
                "SELECT id,document_id,text_current,lang FROM blocks WHERE document_id=?",
                (document_id,),
            )
        )
    else:
        blocks = list(
            connection.execute(
                "SELECT id,document_id,text_current,lang FROM blocks WHERE document_id=? OR EXISTS (SELECT 1 FROM artifacts WHERE artifacts.block_id=blocks.id AND scope_user_id=?)",
                (document_id, user_id),
            )
        )
    for block in blocks:
        if block["lang"] != language or not _matches(block["text_current"], term):
            continue
        if scope == "document":
            connection.execute(
                "UPDATE artifacts SET status='stale',stale_reason='glossary_changed',updated_at=? WHERE document_id=? AND (block_id=? OR kind='package')",
                (now_utc(), document_id, block["id"]),
            )
        else:
            connection.execute(
                "UPDATE artifacts SET status='stale',stale_reason='glossary_changed',updated_at=? WHERE document_id=? AND block_id=? AND scope_user_id=?",
                (now_utc(), block["document_id"], block["id"], user_id),
            )


def delete_glossary(
    database: Database, document_id: str, user_id: str, term_id: str, settings: Settings
) -> None:
    with database.write_tx() as connection:
        row = connection.execute(
            "SELECT * FROM glossary_terms WHERE id=? AND (document_id=? OR user_id=?)",
            (term_id, document_id, user_id),
        ).fetchone()
        if row is None:
            raise Problem(404, "term_not_found", "This pronunciation override is unavailable.")
        check_document(
            connection, document_id, user_id, "reviewer" if row["scope"] == "document" else "reader"
        )
        connection.execute("DELETE FROM glossary_terms WHERE id=?", (term_id,))
        _invalidate_glossary(
            connection, document_id, user_id, row["scope"], row["term"], row["language"]
        )
        jobs.enqueue(
            connection,
            document_id,
            "build_audio",
            {"user_id": user_id if row["scope"] == "user" else None},
            settings.job_max_attempts,
            None,
            now_utc(),
        )


def build_block(
    database: Database,
    settings: Settings,
    block_id: str,
    voice: str,
    *,
    user_id: str | None = None,
    speaker: SpeechProvider | None = None,
    lease: tuple[str, str] | None = None,
) -> dict[str, Any]:
    speaker = speaker or provider(settings)
    with database.read_conn() as connection:
        block = connection.execute("SELECT * FROM blocks WHERE id=?", (block_id,)).fetchone()
    if block is None or json.loads(block["successor_ids_json"]):
        raise Problem(404, "block_not_found", "This passage is unavailable.")
    terms = glossary(database, block["document_id"], user_id)
    scope_user = (
        user_id
        if any(
            row["scope"] == "user"
            and row["language"] == block["lang"]
            and _matches(block["text_current"], row["term"])
            for row in terms
        )
        else None
    )
    key, glossary_hash = cache_key(
        block, terms, voice, speaker.engine_version, settings.active_segmenter_version
    )
    if user_id is not None and voice != settings.speech_voice:
        scope_user = user_id
    if scope_user is not None:
        key = hashlib.sha256((key + ":" + scope_user).encode()).hexdigest()
    with database.read_conn() as connection:
        cached = connection.execute(
            "SELECT artifacts.*,audio_manifests.body_json FROM artifacts JOIN audio_manifests ON audio_manifests.artifact_id=artifacts.id WHERE audio_manifests.cache_key=? ORDER BY artifacts.created_at DESC LIMIT 1",
            (key,),
        ).fetchone()
        if cached and artifact_current(connection, cached):
            cached_body: dict[str, Any] = json.loads(cached["body_json"])
            return cached_body
    artifact_id = str(uuid4())
    now = now_utc()

    def fallback(reason: str) -> dict[str, Any]:
        with database.write_tx() as connection:
            assert_job_lease(connection, lease)
            connection.execute(
                "INSERT INTO artifacts(id,document_id,kind,block_id,dependency_revisions_json,language,voice,engine_version,status,created_at,updated_at,stale_reason,scope_user_id) VALUES (?,?,'audio_block',?,?,?,?,?,'failed',?,?,?,?)",
                (
                    artifact_id,
                    block["document_id"],
                    block_id,
                    json.dumps({block_id: block["revision"]}),
                    block["lang"],
                    voice,
                    speaker.engine_version,
                    now,
                    now,
                    reason,
                    scope_user,
                ),
            )
        return {
            "status": "text_only",
            "reason": reason,
            "block_id": block_id,
            "artifact_id": artifact_id,
        }

    if speaker.engine_version == "disabled":
        return fallback("voice_unavailable")
    normalized = {
        key: block[key]
        for key in (
            "id",
            "page_id",
            "type",
            "parent_id",
            "order_key",
            "text_raw",
            "text_current",
            "lang",
            "revision",
            "status",
            "critical_flag",
        )
    }
    for name in ("bbox", "confidence", "provenance", "successor_ids", "metadata"):
        normalized[name] = json.loads(block[name + "_json"])
    units = segment(Block.model_validate(normalized).model_dump(mode="json"), settings)
    if not units:
        return fallback("no_speech_units")
    if len({unit.unit_id for unit in units}) != len(units):
        raise Problem(502, "invalid_speech_units", "Sentence identifiers must be unique.")
    for unit in units:
        if unit.block_id != block_id or not 0 <= unit.offset_start <= unit.offset_end <= len(
            block["text_current"]
        ):
            raise Problem(
                502, "invalid_speech_units", "A sentence does not reference the current passage."
            )
        if (
            not unit.alias_applied
            and unit.text != block["text_current"][unit.offset_start : unit.offset_end]
        ):
            raise Problem(
                502, "invalid_speech_units", "Sentence offsets do not match the source text."
            )
    spoken = []
    for unit in units:
        relevant = {
            term["term"].casefold(): str(term["spoken_alias"])
            for term in terms
            if term["language"] == unit.lang
        }
        text = unit.text
        if relevant:
            pattern = "|".join(re.escape(term) for term in sorted(relevant, key=len, reverse=True))

            def apply_override(
                match: re.Match[str],
                original: str = unit.text,
                overrides: dict[str, str] = relevant,
            ) -> str:
                return (
                    overrides.get(match.group().casefold(), match.group())
                    if _whole_match(original, match)
                    else match.group()
                )

            text = re.sub(pattern, apply_override, text, flags=re.IGNORECASE)
        spoken.append(
            replace(unit, text=text, alias_applied=unit.alias_applied or text != unit.text)
        )
    if speaker.paid:
        result = fallback(
            "budget_exhausted" if settings.api_budget_inr_hard_cap <= 0 else "pricing_unverified"
        )
        raise Problem(
            402,
            result["reason"],
            "Paid speech is unavailable until its budget and verified tariff are configured. Text remains available.",
        )
    try:
        clips = speaker.synthesize(spoken, voice, block["lang"])
    except SpeechUnavailable as error:
        return fallback(error.code)
    if {clip.unit_id for clip in clips} != {unit.unit_id for unit in spoken} or len(clips) != len(
        spoken
    ):
        raise Problem(
            502, "invalid_speech_output", "The audio provider returned unmatched sentence clips."
        )
    store = FileStore(settings.pathya_data_dir, database, settings.storage_min_free_bytes)
    manifest_units = []
    for unit, clip in zip(
        spoken,
        sorted(
            clips,
            key=lambda clip: next(
                index for index, item in enumerate(spoken) if item.unit_id == clip.unit_id
            ),
        ),
        strict=True,
    ):
        if (
            not clip.mime.startswith("audio/")
            or clip.duration_ms < 0
            or len(clip.audio_bytes) > settings.max_audio_clip_mb * 1024 * 1024
        ):
            raise Problem(
                502, "invalid_speech_output", "An audio clip has an unsupported size or format."
            )
        asset_id, digest, size = store.put_derived(
            block["document_id"],
            artifact_id,
            io.BytesIO(clip.audio_bytes),
            settings.max_audio_clip_mb * 1024 * 1024,
            "audio",
            clip.mime,
        )
        manifest_units.append(
            {
                "unit_id": unit.unit_id,
                "text_offset_start": unit.offset_start,
                "text_offset_end": unit.offset_end,
                "clip_asset_id": asset_id,
                "duration_ms": clip.duration_ms,
                "hash": digest,
                "bytes": size,
                "alias_applied": unit.alias_applied,
            }
        )
    body = {
        "status": "ready",
        "block_id": block_id,
        "block_revision": block["revision"],
        "voice": voice,
        "language": block["lang"],
        "engine_version": speaker.engine_version,
        "glossary_hash": glossary_hash,
        "synthetic": speaker.engine_version.startswith("stub-"),
        "units": manifest_units,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    asset_id, digest, _ = store.put_derived(
        block["document_id"],
        artifact_id,
        io.BytesIO(encoded),
        settings.package_max_mb * 1024 * 1024,
        "audio",
        "application/json",
    )
    with database.write_tx() as connection:
        assert_job_lease(connection, lease)
        current = connection.execute(
            "SELECT revision FROM blocks WHERE id=?", (block_id,)
        ).fetchone()
        # Recheck glossary after synthesis too; results from an obsolete override must not become current.
        _, current_glossary = cache_key(
            block,
            glossary(database, block["document_id"], user_id),
            voice,
            speaker.engine_version,
            settings.active_segmenter_version,
        )
        if (
            current is None
            or current["revision"] != block["revision"]
            or current_glossary != glossary_hash
        ):
            raise Problem(
                409, "stale_revision", "The passage or glossary changed while audio was built."
            )
        connection.execute(
            "UPDATE artifacts SET status='stale',stale_reason='audio_rebuilt',updated_at=? WHERE id IN (SELECT artifact_id FROM audio_manifests WHERE cache_key=?)",
            (now, key),
        )
        connection.execute(
            "INSERT INTO artifacts(id,document_id,kind,block_id,dependency_revisions_json,content_hash,language,voice,engine_version,status,asset_id,created_at,updated_at,scope_user_id) VALUES (?,?,'audio_block',?,?,?,?,?,?,'ready',?,?,?,?)",
            (
                artifact_id,
                block["document_id"],
                block_id,
                json.dumps({block_id: block["revision"]}),
                digest,
                block["lang"],
                voice,
                speaker.engine_version,
                asset_id,
                now,
                now,
                scope_user,
            ),
        )
        connection.execute(
            "INSERT INTO audio_manifests VALUES (?,?,?,?,?)",
            (artifact_id, key, json.dumps(body), glossary_hash, now),
        )
        for entry in manifest_units:
            connection.execute(
                "INSERT OR IGNORE INTO artifact_clips VALUES (?,?)",
                (artifact_id, entry["clip_asset_id"]),
            )
        connection.execute(
            "INSERT INTO usage_events VALUES (?,?,?,'tts',?,?,0,0,?,?)",
            (
                str(uuid4()),
                block["document_id"],
                user_id,
                speaker.engine_version,
                sum(len(unit.text) for unit in spoken),
                now,
                json.dumps({"synthetic": body["synthetic"], "paid": False}),
            ),
        )
    return body
