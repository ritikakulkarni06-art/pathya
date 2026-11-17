from typing import Any

from app.config import Settings
from app.db.connection import Database
from app.errors import Problem
from app.services.backups import prune_backups
from app.services.deletions import purge_document, sweep_retention
from app.services.jobs import finish


def handle(database: Database, settings: Settings, job: dict[str, Any]) -> None:
    if job["kind"] == "retention_sweep":
        count = sweep_retention(database, settings)
        pruned = prune_backups(settings)
        message = (
            "Expired documents scheduled for deletion: "
            + str(count)
            + ". Old backups removed: "
            + str(pruned)
            + "."
        )
    else:
        if not purge_document(
            database, settings, job["document_id"], lease=(job["id"], job["lease_owner"])
        ):
            raise Problem(
                503,
                "deletion_incomplete",
                "Some private files could not be removed. The deletion receipt shows progress.",
            )
        message = "Document files and content rows were removed. Older backups expire separately."
    finish(database, job["id"], job["lease_owner"], "ready", message)
