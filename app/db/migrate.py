import hashlib
import sqlite3
from pathlib import Path

from app.config import load_settings
from app.db.connection import Database

MIGRATIONS = Path(__file__).parent / "migrations"


def _statements(script: str) -> list[str]:
    statements = []
    current = ""
    for line in script.splitlines(keepends=True):
        current += line
        if sqlite3.complete_statement(current):
            statements.append(current)
            current = ""
    if current.strip():
        raise ValueError("Migration ends with an incomplete SQL statement.")
    return statements


def migrate(database: Database, directory: Path = MIGRATIONS, *, apply: bool = True) -> None:
    files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    with database.write_tx() as connection:
        if apply:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
            )
        applied = {
            row["name"]: row["checksum"]
            for row in connection.execute("SELECT name, checksum FROM schema_migrations")
        }
        if set(applied) - {path.name for path in files}:
            raise ValueError("An applied migration file is missing.")
        for path in files:
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.name in applied:
                if applied[path.name] != checksum:
                    raise ValueError("An applied migration checksum changed: " + path.name)
            elif not apply:
                raise ValueError("A database migration has not been applied.")
            else:
                for statement in _statements(path.read_text(encoding="utf-8")):
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(name,checksum) VALUES (?,?)",
                    (path.name, checksum),
                )


def main() -> None:
    settings = load_settings()
    assert settings.pathya_db_path is not None
    migrate(Database(settings.pathya_db_path))
    print("Migrations are current.")


if __name__ == "__main__":
    main()
