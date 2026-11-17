"""Delete only document IDs recorded by the synthetic demo seeder."""

import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from scripts.seed_demo import DEFAULT_DEMO_DIR, DEMO_FORMAT, demo_settings, drain


def reset_demo(directory: Path = DEFAULT_DEMO_DIR) -> int:
    marker = directory / "demo.json"
    data = json.loads(marker.read_text(encoding="utf-8"))
    if data.get("format") != DEMO_FORMAT:
        raise ValueError("Reset requires a marker from the synthetic demo seeder.")
    settings = demo_settings(directory)
    with TestClient(create_app(settings)) as client:
        receipts = []
        for document_id in data.get("document_ids", []):
            response = client.delete("/documents/" + document_id)
            if response.status_code != 202:
                raise RuntimeError("A recorded demo document could not be deleted.")
            receipts.append(response.json()["status_url"])
        drain(client.app.state.database, settings)
        if any(client.get(url).json()["status"] != "complete" for url in receipts):
            raise RuntimeError("Demo deletion is incomplete. Check the deletion receipts.")
    marker.write_text(
        json.dumps({"format": DEMO_FORMAT, "document_ids": []}) + "\n", encoding="utf-8"
    )
    return len(receipts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset only the recorded synthetic demo documents."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DEMO_DIR)
    args = parser.parse_args()
    print("Synthetic demo documents removed: " + str(reset_demo(args.data_dir)))


if __name__ == "__main__":
    main()
