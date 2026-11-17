"""Verify (default) or download the pinned model files in requirements/models.lock.json.

  python scripts/fetch_models.py --verify    [--models-dir local/docling-models] [--tessdata-dir local/tessdata]
  python scripts/fetch_models.py --download  (explicit opt-in; fetches only pinned revisions, verifies SHA-256)

Security:
* Downloads only the listed files, from the pinned commit of each repository.
* Each file is written to a temporary name, checked against the manifest's
  size and SHA-256, and only then moved into place; mismatches are deleted.
* Pickle-format weights (.pt, .pth, .bin, .pkl, .ckpt, .check) are refused:
  Docling inference loads safetensors only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "requirements" / "models.lock.json"
PICKLE_SUFFIXES = {".pt", ".pth", ".bin", ".pkl", ".pickle", ".ckpt", ".check"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict:  # type: ignore[type-arg]
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def verify(models_dir: Path | None, tessdata_dir: Path | None) -> list[str]:
    """Return a list of problems; empty means every requested file matches the manifest."""
    manifest = load_manifest()
    problems: list[str] = []
    checks: list[tuple[Path, dict]] = []  # type: ignore[type-arg]
    if models_dir is not None:
        for repo in manifest["docling"]:
            base = models_dir / repo["local_dir"]
            checks += [(base / f["path"], f) for f in repo["files"]]
            if base.is_dir():
                problems += [f"pickle-format weight file present (refused): {p}"
                             for p in base.rglob("*") if p.suffix.lower() in PICKLE_SUFFIXES]
    if tessdata_dir is not None:
        checks += [(tessdata_dir / f["path"], f) for f in manifest["tessdata"]["files"]]
    for path, entry in checks:
        if not path.is_file():
            problems.append(f"missing: {path}")
        elif path.stat().st_size != entry["size"]:
            problems.append(f"size mismatch: {path} ({path.stat().st_size} != {entry['size']})")
        elif sha256(path) != entry["sha256"]:
            problems.append(f"SHA-256 mismatch: {path}")
    return problems


def _place(tmp: Path, target: Path, entry: dict) -> None:  # type: ignore[type-arg]
    if tmp.stat().st_size != entry["size"] or sha256(tmp) != entry["sha256"]:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"Downloaded file failed verification and was deleted: {target}")
    os.replace(tmp, target)


def download(models_dir: Path, tessdata_dir: Path) -> None:
    from huggingface_hub import hf_hub_download

    manifest = load_manifest()
    for repo in manifest["docling"]:
        base = models_dir / repo["local_dir"]
        for entry in repo["files"]:
            target = base / entry["path"]
            if target.is_file() and sha256(target) == entry["sha256"]:
                continue
            if Path(entry["path"]).suffix.lower() in PICKLE_SUFFIXES:
                raise SystemExit(f"Refusing pickle-format file {entry['path']}")
            staging = models_dir / ".staging" / repo["local_dir"]
            fetched = Path(hf_hub_download(repo_id=repo["repo_id"], filename=entry["path"],
                                           revision=repo["revision"], local_dir=staging))
            target.parent.mkdir(parents=True, exist_ok=True)
            _place(fetched, target, entry)
            print(f"verified {repo['repo_id']}@{repo['revision'][:12]}:{entry['path']}")
    source = manifest["tessdata"]
    tessdata_dir.mkdir(parents=True, exist_ok=True)
    for entry in source["files"]:
        target = tessdata_dir / entry["path"]
        if target.is_file() and sha256(target) == entry["sha256"]:
            continue
        url = (f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/"
               f"{source['revision']}/{entry['path']}")
        tmp = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as response, tmp.open("wb") as out:  # noqa: S310 (pinned https)
            while chunk := response.read(1 << 20):
                out.write(chunk)
        _place(tmp, target, entry)
        print(f"verified tessdata_fast@{source['revision'][:12]}:{entry['path']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="check files against the manifest (default)")
    mode.add_argument("--download", action="store_true", help="download pinned files, then verify")
    parser.add_argument("--models-dir", type=Path, default=Path(os.environ.get(
        "PATHYA_DOCLING_ARTIFACTS", ROOT / "local" / "docling-models")))
    parser.add_argument("--tessdata-dir", type=Path, default=Path(os.environ.get(
        "PATHYA_TESSDATA_DIR", ROOT / "local" / "tessdata")))
    args = parser.parse_args()
    if args.download:
        download(args.models_dir, args.tessdata_dir)
    problems = verify(args.models_dir, args.tessdata_dir)
    for problem in problems:
        print("PROBLEM:", problem)
    if not problems:
        print(f"OK: model files match {MANIFEST.relative_to(ROOT)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
