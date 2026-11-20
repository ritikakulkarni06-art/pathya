import hashlib
import json
from pathlib import Path


def extract(path: Path, languages: list[str]) -> bytes:
    """Whole-document producer stand-in for the worker and HTTP handoff test."""
    fixture = Path(__file__).parent / "p1_contract" / "valid_v1_1_0_status_and_flags.json"
    body = json.loads(fixture.read_bytes())
    body["source_asset"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    body["source_asset"]["uri"] = "https://invalid.example/untrusted-producer-pointer"
    body["pages"][1]["status"] = "partial"
    body["corrections"] = []
    for block in body["blocks"]:
        block["revision"] = 1
        block["current_text"] = block["raw_text"]
    return json.dumps(body, ensure_ascii=False).encode()
