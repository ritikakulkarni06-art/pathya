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
    doc = upgrade_document_data(copy.deepcopy(base), "1.1.0")  # pinned: these vectors are frozen 1.1.0 artifacts
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
    """The frozen 1.0.0/1.1.0 vector set (byte-identical to commit 39331e4)."""
    base = json.loads(SAMPLE.read_text(encoding="utf-8"))
    files: dict[str, str] = {}
    index = []
    for name, description, make, expected in _vectors(base):
        files[f"{name}.json"] = json.dumps(make(), ensure_ascii=False, indent=2) + "\n"
        index.append({"file": f"{name}.json", "description": description, "expected_valid": expected})
    files["index.json"] = json.dumps({"vectors": index}, ensure_ascii=False, indent=2) + "\n"
    return files


# ------------------------------------------------------------------ 1.2.0 set

OUT_V12 = OUT / "v1.2.0"
_FIXED = "2026-11-19T10:00:00Z"


def _id(n: int) -> str:
    return f"7d1e4c52-0000-4000-8000-0000000012{n:02d}"


def _v12(base: Doc) -> Doc:
    """Upgraded sample with every 1.2.0 producer field exercised."""
    doc = upgrade_document_data(copy.deepcopy(base), "1.2.0")
    _block(doc, "a1")["heading_level"] = 1
    _block(doc, "b1")["heading_level"] = 1
    _block(doc, "a9")["role"] = "footnote"
    b5 = _block(doc, "b5")  # OCR list item, already reviewed (revision 2, approved)
    b5["quality_flags"].append("critical_symbol_uncertain")
    return doc


def _with_backend(doc: Doc) -> Doc:
    import hashlib

    from pathya_document_ai.sentences import SEGMENTER, segment_sentences

    doc["integration"] = {"document_revision": 3, "backend_document_id": "p3-doc-opaque-42"}
    a2 = _block(doc, "a2")
    text = a2["current_text"]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    a2["integration"] = {
        "sentences": {"text_revision": a2["revision"], "text_sha256": digest, "segmenter": SEGMENTER,
                      "ranges": [{"start": s, "end": e} for s, e in segment_sentences(text)]},
        "voice_language": "en",
        "audio": [{"uri": "audio://p3/opaque-a2-0", "media_type": "audio/mpeg", "voice_language": "en",
                   "text_revision": a2["revision"], "text_sha256": digest, "sentence_index": 0,
                   "duration_ms": 5400, "document_revision": 3}],
    }
    b2 = _block(doc, "b2")  # Hindi paragraph: original tag kept, Hindi voice chosen
    b2["integration"] = {"sentences": None, "voice_language": "hi", "audio": []}
    return doc


def _after_corrections(doc: Doc) -> Doc:
    from pathya_document_ai.corrections import apply_correction
    from pathya_document_ai.models import Correction, Document

    document = Document.model_validate(doc)
    steps = [
        ("a2", {"operation": "replace_text",
                "new_text": _block(doc, "a2")["current_text"].replace("velocity", "speed")}),
        ("b5", {"operation": "set_block_type", "new_block_type": "paragraph"}),
        ("b4", {"operation": "set_reading_order", "new_reading_order": 0}),
    ]
    for n, (suffix, change) in enumerate(steps, start=1):
        block = next(b for b in document.blocks if str(b.id).endswith(suffix))
        correction = Correction(id=_id(n), document_id=document.id, block_id=block.id,
                                base_revision=block.revision, created_at=_FIXED,
                                author_ref="reviewer:opaque-17", reason="conformance vector", **change)
        document = apply_correction(document, correction)
    return json.loads(document.model_dump_json())


def _vectors_v12(base: Doc) -> list[tuple[str, str, Callable[[], Doc], dict[str, bool]]]:
    def make(*steps: Callable[[Doc], Any]) -> Callable[[], Doc]:
        def build_doc() -> Doc:
            doc = _v12(base)
            for step in steps:
                result = step(doc)
                doc = result if isinstance(result, dict) else doc
            return doc
        return build_doc

    def old(version: str, *steps: Callable[[Doc], Any]) -> Callable[[], Doc]:
        def build_doc() -> Doc:
            doc = upgrade_document_data(copy.deepcopy(base), version)
            for step in steps:
                step(doc)
            return doc
        return build_doc

    valid12 = {"schema_1_0_0": False, "schema_1_1_0": False, "schema_1_2_0": True, "python": True}
    nowhere = {"schema_1_0_0": False, "schema_1_1_0": False, "schema_1_2_0": False, "python": False}
    python_only = {"schema_1_0_0": False, "schema_1_1_0": False, "schema_1_2_0": True, "python": False}

    def stale_text(doc: Doc) -> None:
        a2 = _block(doc, "a2")
        a2["current_text"] = a2["current_text"] + " Edited."
        a2["revision"] = 2  # text changed but derived fields still describe revision 1

    def audio_only_stale(doc: Doc) -> None:
        a2 = _block(doc, "a2")
        a2["integration"]["sentences"] = None
        a2["integration"]["audio"][0]["sentence_index"] = None
        a2["integration"]["audio"][0]["text_revision"] = 7

    return [
        ("valid_v1_2_0_producer_fields", "1.2.0: contract_family, heading levels, footnote role, critical flag "
         "on an approved block.", make(), valid12),
        ("valid_v1_2_0_backend_fields", "1.2.0: document revision, sentence ranges, voice_language and "
         "revision-bound audio on blocks.", make(_with_backend), valid12),
        ("valid_v1_2_0_after_corrections", "1.2.0: text, block-type and reading-order corrections applied by "
         "apply_correction (ids kept, revisions bumped, history appended).", make(_after_corrections), valid12),
        ("invalid_v1_2_0_missing_contract_family", "1.2.0 requires contract_family.",
         make(lambda d: d.pop("contract_family")), nowhere),
        ("invalid_v1_2_0_wrong_contract_family", "Another payload family reusing the version string.",
         make(lambda d: d.update(contract_family="pathya.p3.extraction")), nowhere),
        ("invalid_v1_2_0_missing_role", "1.2.0 blocks require a role.",
         make(lambda d: _block(d, "a2").pop("role")), nowhere),
        ("invalid_v1_2_0_heading_level_on_paragraph", "heading_level only on headings.",
         make(lambda d: _block(d, "a2").update(heading_level=2)), nowhere),
        ("invalid_v1_2_0_critical_unreviewed", "A critical-symbol block cannot be unreviewed.",
         make(lambda d: _block(d, "b5").update(review_status="unreviewed")), nowhere),
        ("invalid_v1_2_0_voice_language_mul", "voice_language is en or hi; language stays separate.",
         make(_with_backend, lambda d: _block(d, "b2")["integration"].update(voice_language="mul")), nowhere),
        ("invalid_python_only_v1_2_0_stale_sentences", "Sentence ranges/audio from an older revision "
         "(JSON Schema cannot hash text).", make(_with_backend, stale_text), python_only),
        ("invalid_python_only_v1_2_0_stale_audio", "Audio bound to another revision.",
         make(_with_backend, audio_only_stale), python_only),
        ("invalid_v1_1_0_with_1_2_role", "A 1.1.0 document cannot carry a non-body role.",
         old("1.1.0", lambda d: _block(d, "a2").update(role="page_header")), nowhere),
        ("invalid_v1_1_0_with_critical_flag", "critical_symbol_uncertain requires 1.2.0.",
         old("1.1.0", lambda d: _block(d, "b5")["quality_flags"].append("critical_symbol_uncertain")), nowhere),
    ]


def build_v12() -> dict[str, str]:
    base = json.loads(SAMPLE.read_text(encoding="utf-8"))
    files: dict[str, str] = {}
    index = []
    for name, description, make, expected in _vectors_v12(base):
        files[f"{name}.json"] = json.dumps(make(), ensure_ascii=False, indent=2) + "\n"
        index.append({"file": f"{name}.json", "description": description, "expected_valid": expected})
    files["index.json"] = json.dumps({"contract_family": "pathya.p1.content", "schema_version": "1.2.0",
                                      "vectors": index}, ensure_ascii=False, indent=2) + "\n"
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sets = [(OUT, build()), (OUT_V12, build_v12())]
    if args.check:
        stale = [str((out / n).relative_to(ROOT)) for out, files in sets for n, text in files.items()
                 if not (out / n).exists() or (out / n).read_text(encoding="utf-8") != text]
        if stale:
            print("STALE conformance vectors:", stale)
            return 1
        print(f"OK: {sum(len(f) for _, f in sets)} conformance files are current.")
        return 0
    for out, files in sets:
        out.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            (out / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {len(files)} files to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
