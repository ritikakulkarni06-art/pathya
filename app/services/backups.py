"""Consistent private SQLite/file snapshots. Run with the service account's permissions."""

import json
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.db.connection import Database


def confined_child(root: Path, child: Path) -> Path:
    base = root.resolve()
    target = child.resolve()
    if target == base or not target.is_relative_to(base):
        raise ValueError("The backup target must stay inside its configured directory.")
    return target


def copy_private_tree(source: Path, target: Path) -> None:
    if not source.exists():
        return
    if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
        raise ValueError("Private snapshots cannot follow symbolic links.")
    shutil.copytree(source, target)


def create_backup(settings: Settings) -> Path:
    data = settings.pathya_data_dir.resolve()
    assert settings.backup_dir is not None
    root = settings.backup_dir.resolve()
    if root == data or root.is_relative_to(data):
        raise ValueError("Keep backups outside the live data directory.")
    root.mkdir(parents=True, exist_ok=True)
    target = confined_child(
        root, root / ("backup-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex)
    )
    target.mkdir()
    assert settings.pathya_db_path is not None
    database = Database(settings.pathya_db_path)
    try:
        # A separate writer lock prevents file/asset publication during this snapshot.
        with database.write_tx():
            with (
                database.read_conn() as source,
                closing(sqlite3.connect(target / "pathya.sqlite3")) as destination,
            ):
                source.backup(destination)
            for section in ("sources", "derived"):
                copy_private_tree(data / section, target / section)
            (target / "backup.json").write_text(
                json.dumps(
                    {
                        "format": 1,
                        "created_at": datetime.now(UTC).isoformat(),
                        "database": "pathya.sqlite3",
                        "sections": ["sources", "derived"],
                    }
                ),
                encoding="utf-8",
            )
    except BaseException:
        # Only remove the verified, newly-created child, never the backup root.
        shutil.rmtree(confined_child(root, target), onerror=_writable_remove)
        raise
    prune_backups(settings)
    return target


def _writable_remove(function: object, path: str, exc_info: object) -> None:
    import os
    import stat

    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    if os.path.isdir(path):
        os.rmdir(path)
    else:
        os.unlink(path)


def prune_backups(settings: Settings) -> int:
    assert settings.backup_dir is not None
    root = settings.backup_dir.resolve()
    if not root.is_dir():
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=settings.backup_days)
    count = 0
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir() or not child.name.startswith("backup-"):
            continue
        target = confined_child(root, child)
        metadata = target / "backup.json"
        if not metadata.is_file() or metadata.is_symlink():
            continue
        try:
            created = datetime.fromisoformat(
                json.loads(metadata.read_text(encoding="utf-8"))["created_at"]
            )
            expired = created.tzinfo is not None and created < cutoff
        except (ValueError, KeyError, TypeError):
            continue
        if expired:
            shutil.rmtree(target, onerror=_writable_remove)
            count += 1
    return count


def restore_backup(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if (
        source == destination
        or destination.is_relative_to(source)
        or source.is_relative_to(destination)
    ):
        raise ValueError("Restore source and destination must not overlap.")
    if destination.exists():
        raise ValueError("Restore only into a new, empty location.")
    metadata = json.loads((source / "backup.json").read_text(encoding="utf-8"))
    if metadata.get("format") != 1 or not (source / "pathya.sqlite3").is_file():
        raise ValueError("This backup format is unsupported.")
    if (source / "pathya.sqlite3").is_symlink():
        raise ValueError("A database snapshot cannot be a symbolic link.")
    with closing(sqlite3.connect(source / "pathya.sqlite3")) as database:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("The database snapshot failed its integrity check.")
    destination.mkdir(parents=True)
    shutil.copy2(source / "pathya.sqlite3", destination / "pathya.sqlite3")
    with closing(sqlite3.connect(destination / "pathya.sqlite3")) as restored:
        restored.execute("DELETE FROM sessions")
        restored.commit()
    for section in ("sources", "derived"):
        copy_private_tree(source / section, destination / section)
