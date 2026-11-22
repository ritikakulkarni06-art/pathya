import errno
import hashlib
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import uuid4

from app.db.connection import Database
from app.db.repos.assets import get_asset
from app.errors import Problem
from app.services.access import require_document

AssetKind = Literal["source", "crop", "thumbnail", "audio", "package"]


@dataclass
class DeletionResult:
    files_removed: int = 0
    bytes_removed: int = 0
    failures: list[str] = field(default_factory=list)


class FileStore:
    def __init__(self, root: Path, database: Database, min_free_bytes: int = 100_000_000) -> None:
        self.root = root.resolve()
        self.database = database
        self.min_free_bytes = min_free_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def safe_path(self, *parts: str) -> Path:
        for part in parts:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", part):
                raise Problem(400, "invalid_path", "The file identifier is invalid.")
        target = self.root.joinpath(*parts).resolve()
        if not target.is_relative_to(self.root):
            raise Problem(400, "invalid_path", "The file location is outside private storage.")
        return target

    def _space(self, additional: int = 0) -> None:
        if shutil.disk_usage(self.root).free < self.min_free_bytes + additional:
            raise Problem(
                507,
                "storage_full",
                "Storage is full. Ask the maintainer to free space, then retry.",
            )

    def put_source(
        self,
        document_id: str,
        stream: BinaryIO,
        max_bytes: int,
        mime: str = "application/octet-stream",
    ) -> tuple[str, str, int]:
        return self._put(document_id, None, "source", stream, max_bytes, mime)

    def put_derived(
        self,
        document_id: str,
        artifact_id: str,
        stream: BinaryIO,
        max_bytes: int,
        kind: AssetKind = "audio",
        mime: str = "application/octet-stream",
    ) -> tuple[str, str, int]:
        if kind == "source":
            raise ValueError("Use put_source for immutable source content.")
        return self._put(document_id, artifact_id, kind, stream, max_bytes, mime)

    def _put(
        self,
        document_id: str,
        artifact_id: str | None,
        kind: AssetKind,
        stream: BinaryIO,
        max_bytes: int,
        mime: str,
    ) -> tuple[str, str, int]:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        directory = (
            self.safe_path("sources", document_id)
            if artifact_id is None
            else self.safe_path("derived", document_id, artifact_id)
        )
        temporary_dir = self.safe_path("tmp")
        temporary_dir.mkdir(parents=True, exist_ok=True)
        self._space()
        temporary: Path | None = None
        target: Path | None = None
        published = False
        try:
            digest = hashlib.sha256()
            count = 0
            with tempfile.NamedTemporaryFile(
                dir=temporary_dir,
                prefix=hashlib.sha256(document_id.encode()).hexdigest() + "-",
                delete=False,
            ) as destination:
                temporary = Path(destination.name)
                while True:
                    part = stream.read(min(65536, max_bytes - count + 1))
                    if not part:
                        break
                    count += len(part)
                    if count > max_bytes:
                        raise Problem(
                            413, "too_large", "This file is too large. Upload a smaller chapter."
                        )
                    self._space(len(part))
                    digest.update(part)
                    destination.write(part)
                destination.flush()
                os.fsync(destination.fileno())
            sha256 = digest.hexdigest()
            target = directory / sha256
            relative = target.relative_to(self.root).as_posix()
            with self.database.write_tx() as connection:
                document = connection.execute(
                    "SELECT state FROM documents WHERE id=?", (document_id,)
                ).fetchone()
                if document is None or document["state"] in {"deleting", "deleted"}:
                    raise Problem(404, "document_not_found", "This document is unavailable.")
                existing = connection.execute(
                    "SELECT id,sha256,bytes FROM assets WHERE private_path=? AND deleted_at IS NULL",
                    (relative,),
                ).fetchone()
                if existing:
                    return existing["id"], existing["sha256"], existing["bytes"]
                directory.mkdir(parents=True, exist_ok=True)
                # Atomic, create-only publication on the same filesystem; never overwrite a source.
                try:
                    os.link(temporary, target)
                    published = True
                except FileExistsError:
                    with target.open("rb") as existing_stream:
                        existing_hash = hashlib.file_digest(existing_stream, "sha256").hexdigest()
                    if existing_hash != sha256:
                        raise Problem(
                            500,
                            "storage_integrity",
                            "Stored file verification failed. Contact the maintainer.",
                        ) from None
                temporary.unlink()
                temporary = None
                target.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
                asset_id = str(uuid4())
                connection.execute(
                    "INSERT INTO assets(id,document_id,kind,sha256,bytes,mime,private_path,immutable,created_at) VALUES (?,?,?,?,?,?,?,1,?)",
                    (
                        asset_id,
                        document_id,
                        kind,
                        sha256,
                        count,
                        mime,
                        relative,
                        datetime.now(UTC).isoformat(),
                    ),
                )
            return asset_id, sha256, count
        except BaseException as error:
            if published and target is not None:
                target.chmod(stat.S_IWRITE | stat.S_IREAD)
                target.unlink(missing_ok=True)
            if isinstance(error, OSError) and error.errno in {errno.ENOSPC, errno.EDQUOT}:
                raise Problem(
                    507, "storage_full", "Storage is full. Free space before retrying."
                ) from None
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def open_asset(self, asset_id: str, requester: str) -> BinaryIO:
        with self.database.read_conn() as connection:
            asset = get_asset(connection, asset_id)
        if asset is None:
            raise Problem(404, "asset_not_found", "This file is unavailable.")
        require_document(self.database, asset["document_id"], requester)
        path = self.safe_path(*Path(asset["private_path"]).parts)
        if not path.is_file():
            raise Problem(
                404, "asset_not_found", "This file is unavailable. Please try rebuilding it."
            )
        return path.open("rb")

    def secure_delete_document(self, document_id: str) -> DeletionResult:
        result = DeletionResult()
        self.safe_path("sources", document_id)
        for path in self.safe_path("tmp").glob(
            hashlib.sha256(document_id.encode()).hexdigest() + "-*"
        ):
            try:
                if path.is_symlink():
                    path.unlink()
                elif path.is_file():
                    size = path.stat().st_size
                    path.chmod(stat.S_IWRITE | stat.S_IREAD)
                    path.unlink()
                    result.files_removed += 1
                    result.bytes_removed += size
                else:
                    result.failures.append("temporary_removal_failed")
            except OSError:
                result.failures.append("temporary_removal_failed")
        for section in ("sources", "derived"):
            directory = self.safe_path(section, document_id)
            if not directory.exists():
                continue
            for path in sorted(
                directory.rglob("*"), key=lambda entry: len(entry.parts), reverse=True
            ):
                try:
                    if path.is_symlink():
                        path.unlink()
                    elif path.is_file():
                        size = path.stat().st_size
                        path.chmod(stat.S_IWRITE | stat.S_IREAD)
                        path.unlink()
                        result.files_removed += 1
                        result.bytes_removed += size
                    elif path.is_dir():
                        path.rmdir()
                except OSError:
                    result.failures.append("file_removal_failed")
            try:
                directory.rmdir()
            except OSError:
                result.failures.append("directory_removal_failed")
        return result
