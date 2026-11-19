"""Regenerate the versioned contract schemas from the Pydantic models.

Writes:
  contract/schemas/pathya_content.v1.0.0.schema.json  (frozen, published at 39331e4)
  contract/schemas/pathya_content.v1.1.0.schema.json  (frozen, published at 39331e4)
  contract/schemas/pathya_content.v1.2.0.schema.json  (current, generated from the models)
  contract/pathya_content.schema.json                 (frozen alias of 1.1.0; never moves)

Usage: python scripts/export_schema.py [--check]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from pathya_document_ai.schema import SCHEMA_VERSIONS, render_json_schema

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {ROOT / "contract" / "schemas" / f"pathya_content.v{v}.schema.json": v for v in SCHEMA_VERSIONS}
# The unversioned path is a frozen alias of 1.1.0 (what P2/P3 integrated against at 39331e4).
# New consumers should use the versioned files; this alias never silently moves to a newer version.
TARGETS[ROOT / "contract" / "pathya_content.schema.json"] = "1.1.0"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if any committed schema is stale")
    args = parser.parse_args()
    stale = []
    for path, version in TARGETS.items():
        expected = render_json_schema(version)
        if args.check:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != expected:
                stale.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8", newline="\n")
            print(f"Wrote {path.relative_to(ROOT)} ({version})")
    if stale:
        for path in stale:
            print(f"STALE: {path.relative_to(ROOT)}; rerun without --check.")
        return 1
    if args.check:
        print(f"OK: {len(TARGETS)} schema files are current.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
