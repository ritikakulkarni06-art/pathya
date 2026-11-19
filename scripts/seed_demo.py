"""Create only synthetic demo content through the real API, with all online adapters off."""

import argparse
import io
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.config import Settings
from app.db.connection import Database
from app.main import create_app
from app.worker.runner import run_once

DEMO_FORMAT = "pathya-synthetic-demo-v1"
DEFAULT_DEMO_DIR = Path("data/demo")


def demo_settings(directory: Path) -> Settings:
    return Settings(
        _env_file=None,
        pathya_env="dev",
        auth_mode="local",
        session_secret="",
        pathya_data_dir=directory,
        pathya_db_path=directory / "pathya.sqlite3",
        backup_dir=directory.parent / "demo-backups",
        storage_min_free_bytes=0,
        llm_enabled=False,
        llm_provider="none",
        llm_model_id="",
        gemini_api_key="",
        embeddings_enabled=False,
        embedding_model_path=None,
        extraction_adapter="fixture",
        extraction_command=[],
        extraction_fixture_path=Path(__file__).resolve().parents[1]
        / "tests/fixtures/chapter_demo.json",
        speech_provider="stub",
        speech_voice="default",
        speech_engine_version="",
        segmenter="",
        segmenter_version="demo-regex-v1",
        job_lease_seconds=30,
    )


def drain(database: Database, settings: Settings) -> None:
    for _ in range(100):
        if not run_once(database, settings):
            return
    raise RuntimeError("The synthetic demo worker did not finish within its attempt limit.")


def seed_demo(directory: Path = DEFAULT_DEMO_DIR) -> dict[str, Any]:
    settings = demo_settings(directory)
    marker = directory / "demo.json"
    prior: dict[str, Any] = {}
    if marker.exists():
        prior = json.loads(marker.read_text(encoding="utf-8"))
        if prior.get("format") != DEMO_FORMAT:
            raise ValueError("This directory is not a recognized synthetic demo.")
    elif directory.exists() and any(directory.iterdir()):
        raise ValueError("Choose an empty directory or a recognized synthetic demo directory.")
    writer = PdfWriter()
    for _ in range(10):
        writer.add_blank_page(width=612, height=792)
    source = io.BytesIO()
    writer.write(source)
    with TestClient(create_app(settings)) as client:
        uploaded = client.post(
            "/documents",
            files={"file": ("synthetic-demo.pdf", source.getvalue(), "application/pdf")},
            data={
                "title": "Synthetic Pathya demonstration",
                "rights_note": "Generated synthetic development material; no textbook content.",
                "languages": "en,hi",
            },
        )
        if uploaded.status_code not in {200, 202}:
            raise RuntimeError("The synthetic demo upload was refused.")
        document_id = uploaded.json()["document_id"]
        drain(client.app.state.database, settings)
        content = client.get("/documents/" + document_id + "/content")
        if content.status_code != 200:
            raise RuntimeError("The synthetic demo content is unavailable.")
        block = next(
            (
                b
                for b in content.json()["blocks"]
                if b["type"] == "paragraph"
                and not b["critical_flag"]
                and b["status"] in {"ok", "reviewed", "corrected", "not_scored"}
            ),
            None,
        )
        if block is None:
            raise RuntimeError("No eligible demo paragraph was produced.")
        scheduled = client.post("/blocks/" + block["id"] + "/audio", json={})
        if scheduled.status_code != 202:
            raise RuntimeError("Synthetic demo audio could not be scheduled.")
        drain(client.app.state.database, settings)
        audio = client.get("/blocks/" + block["id"] + "/audio")
        if audio.status_code != 200 or audio.json().get("synthetic") is not True:
            raise RuntimeError("The demo did not produce explicitly synthetic audio.")
        package = client.post("/documents/" + document_id + "/packages")
        if package.status_code != 201:
            raise RuntimeError("The synthetic demo download plan could not be built.")
        owner = client.get("/auth/me").json()["id"]
        info = {
            "format": DEMO_FORMAT,
            "document_ids": sorted(set(prior.get("document_ids", [])) | {document_id}),
            "document_id": document_id,
            "block_id": block["id"],
            "package_id": package.json()["id"],
            "owner_id": owner,
            "llm_enabled": False,
            "synthetic_audio": True,
            "notice": "Synthetic fixtures and silent WAV audio; no real OCR, narration or accuracy result.",
        }
    marker.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed an offline synthetic Pathya demo.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DEMO_DIR)
    args = parser.parse_args()
    print(json.dumps(seed_demo(args.data_dir), indent=2))


if __name__ == "__main__":
    main()
