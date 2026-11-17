"""Regenerate contract/pathya_content.schema.json from the Pydantic models.

Usage: .venv\\Scripts\\python.exe scripts\\export_schema.py [--check]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from pathya_document_ai.schema import render_json_schema, write_json_schema

TARGET = Path(__file__).resolve().parents[1] / "contract" / "pathya_content.schema.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed schema is stale")
    args = parser.parse_args()
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != render_json_schema():
            print(f"STALE: {TARGET} differs from the models; rerun without --check.")
            return 1
        print(f"OK: {TARGET} is current.")
        return 0
    write_json_schema(TARGET)
    print(f"Wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
