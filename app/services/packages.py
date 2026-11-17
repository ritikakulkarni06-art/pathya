import io
import json
from typing import Any
from uuid import uuid4

from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.errors import Problem
from app.services.access import check_document
from app.services.manifests import artifact_current
from app.services.storage import FileStore


def build_package(
    database: Database, settings: Settings, document_id: str, user_id: str
) -> dict[str, Any]:
    with database.read_conn() as connection:
        connection.execute("BEGIN")
        document = check_document(connection, document_id, user_id)
        revision = document["current_revision"]
        manifest = connection.execute(
            "SELECT * FROM manifests WHERE document_id=? AND revision=? ORDER BY build_seq DESC LIMIT 1",
            (document_id, revision),
        ).fetchone()
        if manifest is None:
            raise Problem(
                409,
                "manifest_pending",
                "Wait for the chapter manifest before requesting a package.",
            )
        source = json.loads(manifest["body_json"])
        blocks = list(
            connection.execute(
                "SELECT id,text_current,revision FROM blocks WHERE document_id=? AND json_array_length(successor_ids_json)=0",
                (document_id,),
            )
        )
        files = []
        for entry in source["artifacts"]:
            if entry["status"] != "ready":
                continue
            artifact = connection.execute(
                "SELECT * FROM artifacts WHERE id=?", (entry["artifact_id"],)
            ).fetchone()
            if (
                artifact is None
                or artifact.get("scope_user_id") is not None
                or not artifact_current(connection, artifact)
            ):
                raise Problem(
                    409,
                    "package_stale",
                    "Audio changed. Refresh the manifest before building this package.",
                )
            audio = connection.execute(
                "SELECT body_json FROM audio_manifests WHERE artifact_id=?", (artifact["id"],)
            ).fetchone()
            if audio is None:
                continue
            files.append(
                {"asset_id": entry["asset_id"], "hash": entry["hash"], "bytes": entry["bytes"]}
            )
            for unit in json.loads(audio["body_json"])["units"]:
                files.append(
                    {
                        "asset_id": unit["clip_asset_id"],
                        "hash": unit["hash"],
                        "bytes": unit["bytes"],
                    }
                )
        unique = {entry["asset_id"]: entry for entry in files}
        body = {
            "document_id": document_id,
            "revision": revision,
            "manifest_id": manifest["id"],
            "manifest_sha256": manifest["sha256"],
            "manifest": source,
            "text": [dict(row) for row in blocks],
            "files": list(unique.values()),
            "model_downloads_included": False,
        }
        encoded = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        total = len(encoded) + sum(entry["bytes"] for entry in unique.values())
        if total > settings.package_max_mb * 1024 * 1024:
            raise Problem(
                413,
                "package_too_large",
                "This chapter package is too large. Choose a smaller chapter or omit audio.",
            )
        dependencies = {row["id"]: row["revision"] for row in blocks}
    package_id = str(uuid4())
    artifact_id = str(uuid4())
    store = FileStore(settings.pathya_data_dir, database, settings.storage_min_free_bytes)
    asset_id, digest, _ = store.put_derived(
        document_id,
        artifact_id,
        io.BytesIO(encoded),
        settings.package_max_mb * 1024 * 1024,
        "package",
        "application/json",
    )
    with database.write_tx() as connection:
        current = check_document(connection, document_id, user_id)
        if current["current_revision"] != revision:
            raise Problem(
                409,
                "stale_revision",
                "The chapter changed while its package was built. Request a new package.",
            )
        for block_id, expected in dependencies.items():
            row = connection.execute(
                "SELECT revision FROM blocks WHERE id=? AND document_id=?", (block_id, document_id)
            ).fetchone()
            if row is None or row["revision"] != expected:
                raise Problem(
                    409, "stale_revision", "The chapter changed while its package was built."
                )
        for entry in source["artifacts"]:
            if entry["status"] != "ready":
                continue
            dependency = connection.execute(
                "SELECT * FROM artifacts WHERE id=?", (entry["artifact_id"],)
            ).fetchone()
            if dependency is None or not artifact_current(connection, dependency):
                raise Problem(
                    409,
                    "package_stale",
                    "Audio changed while the package was prepared. Refresh and try again.",
                )
        now = now_utc()
        connection.execute(
            "INSERT INTO artifacts(id,document_id,kind,dependency_revisions_json,content_hash,status,asset_id,created_at,updated_at) VALUES (?,?,'package',?,?,'ready',?,?,?)",
            (artifact_id, document_id, json.dumps(dependencies), digest, asset_id, now, now),
        )
        connection.execute(
            "INSERT INTO packages VALUES (?,?,?,?,?,?,?,?,?)",
            (
                package_id,
                document_id,
                revision,
                manifest["id"],
                artifact_id,
                encoded.decode(),
                digest,
                total,
                now,
            ),
        )
    return {
        "id": package_id,
        "revision": revision,
        "sha256": digest,
        "total_bytes": total,
        "asset_id": asset_id,
    }
