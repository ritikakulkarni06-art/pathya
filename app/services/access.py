import sqlite3
from typing import Any, Literal

from app.db.connection import Database
from app.db.repos import documents
from app.errors import Problem

DocumentRole = Literal["reader", "reviewer", "owner"]
ROLE_RANK = {"reader": 1, "reviewer": 2, "owner": 3}


def require_document(
    database: Database, document_id: str, user_id: str, minimum: DocumentRole = "reader"
) -> dict[str, Any]:
    with database.read_conn() as connection:
        return check_document(connection, document_id, user_id, minimum)


def check_document(
    connection: sqlite3.Connection, document_id: str, user_id: str, minimum: DocumentRole = "reader"
) -> dict[str, Any]:
    document = documents.get_document(connection, document_id)
    if document is None or document["state"] in {"deleting", "deleted"}:
        raise Problem(404, "document_not_found", "This document is unavailable.")
    role = "owner" if document["owner_id"] == user_id else None
    if role is None:
        grant = documents.get_grant(connection, document_id, user_id)
        role = grant["role"] if grant is not None else None
    if role is None:
        raise Problem(404, "document_not_found", "This document is unavailable.")
    if ROLE_RANK[role] < ROLE_RANK[minimum]:
        raise Problem(
            403, "insufficient_role", "Ask the document owner for the required permission."
        )
    document["_access_user_id"] = user_id
    return document
