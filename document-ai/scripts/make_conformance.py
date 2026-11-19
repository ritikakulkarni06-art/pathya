"""Regenerate contract/conformance/: valid and invalid documents with expected verdicts.

Each vector says whether it should be accepted by the 1.0.0 JSON Schema, the
1.1.0 JSON Schema and the Python validator (``models.Document``). Vectors that
only the Python validator rejects document the rules JSON Schema cannot express;
consumers in other languages must implement those checks themselves.

Usage: python scripts/make_conformance.py [--check]
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
from typing import Any, Callable

from pathya_document_ai.models import upgrade_document_data

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "contract" / "samples" / "sample_document_en_hi.json"
OUT = ROOT / "contract" / "conformance"

Doc = dict[str, Any]


def _block(doc: Doc, suffix: str) -> Doc:
    return next(b for b in doc["blocks"] if b["id"].endswith(suffix))


def _v11(base: Doc) -> Doc:
    doc = upgrade_document_data(copy.deepcopy(base))
    doc["pages"][1]["warnings"] = [{"stage": "ocr", "code": "ocr_applied",
                                    "message": "Tesseract 5.4.0 (hin+eng): 41 words, mean confidence 0.87"}]
    _block(doc, "b5")["quality_flags"].append("duplicate_content")
    return doc


def _uncertain_table(doc: Doc) -> Doc:
    table = _block(doc, "a4")
    table["table"] = {"row_count": None, "column_count": None, "cell_ids": []}
    table["quality_flags"] = ["table_structure_uncertain"]
    table["raw_text"] = table["current_text"] = "Quantity SI unit Acceleration m/s²"
    doc["blocks"] = [b for b in doc["blocks"] if b["block_type"] != "table_cell"]
    doc["edges"] = [e for e in doc["edges"] if e["edge_type"] not in ("header_for", "contains")]
    return doc


def _vectors(base: Doc) -> list[tuple[str, str, Callable[[], Doc], dict[str, bool]]]:
    def v10(fn: Callable[[Doc], Any] | None = None) -> Callable[[], Doc]:
        def make() -> Doc:
            doc = copy.deepcopy(base)
            if fn:
                fn(doc)
            return doc
        return make

    def v11(fn: Callable[[Doc], Any] | None = None) -> Callable[[], Doc]:
        def make() -> Doc:
            doc = _v11(base)
            if fn:
                fn(doc)
            return doc
        return make

    yes10_11 = {"schema_1_0_0": True, "schema_1_1_0": True, "python": True}
    only11 = {"schema_1_0_0": False, "schema_1_1_0": True, "python": True}
    nowhere = {"schema_1_0_0": False, "schema_1_1_0": False, "python": False}
    python_only = {"schema_1_0_0": False, "schema_1_1_0": True, "python": False}
    return [
        ("valid_v1_0_0_sample", "Committed 1.0.0 sample; valid everywhere.", v10(), yes10_11),
        ("valid_v1_1_0_status_and_flags", "1.1.0: page status/warnings and a duplicate_content flag.", v11(), only11),
        ("valid_v1_1_0_uncertain_table", "1.1.0: table with null counts and no cells.",
         v11(_uncertain_table), only11),
        ("invalid_v1_1_0_missing_block_id", "1.1.0 requires every id.",
         v11(lambda d: d["blocks"][0].pop("id")), nowhere),
        ("invalid_v1_0_0_with_1_1_flag", "A 1.0.0 document may not use 1.1.0 flags.",
         v10(lambda d: _block(d, "a2")["quality_flags"].append("orphan_caption")), nowhere),
        ("invalid_v1_0_0_with_page_status", "A 1.0.0 document may not carry page status.",
         v10(lambda d: d["pages"][0].update(status="ok", warnings=[])), nowhere),
        ("invalid_v1_1_0_page_without_status", "1.1.0 pages require a status.",
         v11(lambda d: d["pages"][0].pop("status")), {"schema_1_0_0": False, "schema_1_1_0": False,
                                                       "python": False}),
        ("invalid_v1_1_0_counts_without_cells", "A table with no cells must have null counts.",
         v11(lambda d: _uncertain_table(d)["blocks"][3]["table"].update(row_count=2, column_count=2)), nowhere),
        ("invalid_unknown_version", "Unknown schema_version.", v11(lambda d: d.update(schema_version="2.0.0")),
         nowhere),
        ("invalid_python_only_reversed_bbox", "bbox x0 >= x1 (JSON Schema cannot compare items).",
         v11(lambda d: _block(d, "a1").update(bbox=[0.62, 0.06, 0.1, 0.1])), python_only),
        ("invalid_python_only_unknown_parent", "parent_id references a block that does not exist.",
         v11(lambda d: _block(d, "a1").update(parent_id="7d1e4c52-0000-4000-8000-00000000dead")), python_only),
        ("invalid_python_only_blank_page_with_blocks", "A blank page cannot have blocks.",
         v11(lambda d: d["pages"][0].update(status="blank")), python_only),
    ]


def build() -> dict[str, str]:
    base = json.loads(SAMPLE.read_text(encoding="utf-8"))
    files: dict[str, str] = {}
    index = []
    for name, description, make, expected in _vectors(base):
        files[f"{name}.json"] = json.dumps(make(), ensure_ascii=False, indent=2) + "\n"
        index.append({"file": f"{name}.json", "description": description, "expected_valid": expected})
    files["index.json"] = json.dumps({"vectors": index}, ensure_ascii=False, indent=2) + "\n"
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = build()
    if args.check:
        stale = [n for n, text in files.items()
                 if not (OUT / n).exists() or (OUT / n).read_text(encoding="utf-8") != text]
        if stale:
            print("STALE conformance vectors:", stale)
            return 1
        print(f"OK: {len(files)} conformance files are current.")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {len(files)} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
