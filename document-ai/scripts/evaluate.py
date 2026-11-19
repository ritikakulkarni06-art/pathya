"""Run the P1 extraction stack on a ground-truth dataset and report metrics.

  python scripts/evaluate.py --manifest evaluation/<dataset>/manifest.json --out evaluation/results/<name>
  python scripts/evaluate.py --synthetic --out <dir>      # harness smoke test on generated pages

Manifest format (paths relative to the manifest)::

    {"dataset": "name", "synthetic": false, "authorization": "who approved use, licence",
     "documents": [{"pdf": "book1.pdf", "gold": "book1.gold.json"}]}

Each gold file is a JSON list of page objects (see pathya_document_ai.evaluation).
Real textbook PDFs must be authorized for this use, kept out of git (the
evaluation/private/ folder is ignored) and never uploaded to external services.
OCR and Docling run only if available locally; what ran is recorded.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

from pathya_document_ai.evaluation import PageScore, score_page, to_json

ROOT = Path(__file__).resolve().parents[1]


def _engines() -> tuple[Any, Any, list[str]]:
    notes = []
    ocr_engine = layout_engine = None
    try:
        from pathya_document_ai.ocr import TesseractEngine
        from pathya_document_ai.tesseract import TesseractConfig

        tessdata = os.environ.get("PATHYA_TESSDATA_DIR") or (ROOT / "local" / "tessdata")
        ocr_engine = TesseractEngine(TesseractConfig(tessdata_dir=Path(tessdata) if Path(tessdata).is_dir() else None))
        notes.append(f"OCR: tesseract {ocr_engine.info.version}")
    except Exception as exc:  # reported, never hidden
        notes.append(f"OCR unavailable: {exc}")
    try:
        from pathya_document_ai.layout_docling import DoclingConfig, DoclingLayoutEngine

        artifacts = os.environ.get("PATHYA_DOCLING_ARTIFACTS") or (ROOT / "local" / "docling-models")
        layout_engine = DoclingLayoutEngine(DoclingConfig(artifacts_path=Path(artifacts)))
        notes.append(f"Layout: docling {layout_engine.version}")
    except Exception as exc:
        notes.append(f"Layout unavailable: {exc}")
    return ocr_engine, layout_engine, notes


def run_document(pdf: Path, ocr_engine: Any, layout_engine: Any) -> tuple[Any, float, int]:
    from pathya_document_ai.layout import build_layout_document
    from pathya_document_ai.ocr import merge_ocr_into_document, ocr_pdf_pages
    from pathya_document_ai.pdf import extract_native_pdf, to_contract_document

    started = time.monotonic()
    extraction = extract_native_pdf(pdf)
    ocr_results = {}
    if ocr_engine is not None:
        run = ocr_pdf_pages(pdf, extraction, engine=ocr_engine, include_recommended=True)
        ocr_results = {r.page_index: r for r in run.results}
    if layout_engine is not None:
        layouts = layout_engine.analyze_document(pdf, extraction)
        document = build_layout_document(extraction, layouts, ocr_results, source_uri=f"eval://{pdf.name}").document
    else:
        document = to_contract_document(extraction, source_uri=f"eval://{pdf.name}")
        if ocr_results:
            document, _ = merge_ocr_into_document(document, ocr_results.values(), extraction=extraction)
    return document, time.monotonic() - started, extraction.page_count


def evaluate(documents: list[tuple[Path, list[dict[str, Any]]]]) -> tuple[list[PageScore], list[str]]:
    ocr_engine, layout_engine, notes = _engines()
    scores: list[PageScore] = []
    for pdf, gold_pages in documents:
        try:
            document, seconds, pages = run_document(pdf, ocr_engine, layout_engine)
        except Exception as exc:  # a crash is a measured failure, not a skipped document
            notes.append(f"{pdf.name}: FAILED {type(exc).__name__}: {exc}")
            scores += [PageScore(pdf.name, g["page_index"], g.get("category", []), "crashed", None, None,
                                 {"pairwise_accuracy": None}, {}) for g in gold_pages]
            continue
        for gold in gold_pages:
            scores.append(score_page(document, gold, source=pdf.name, seconds=seconds / max(pages, 1)))
    return scores, notes


def _synthetic(work: Path) -> list[tuple[Path, list[dict[str, Any]]]]:
    sys.path.insert(0, str(ROOT / "tests" / "unit"))
    import _layout_fixtures as fx  # type: ignore[import-not-found]

    pdf = fx.write_textbook(work / "synthetic_textbook.pdf")
    items = ["1. Distance is the length of the path travelled.",
             "2. Displacement is the shortest distance between two points.",
             "3. Speed is distance travelled per unit time."]
    gold = [
        {"page_index": 0, "category": ["english", "single_column", "lists"],
         "reading_order": ["Chapter 4 Motion", "4.1 Describing Motion", fx.PARA_A, fx.PARA_B, "Key ideas",
                           *items, fx.PARA_C]},
        {"page_index": 1, "category": ["english", "multi_column"],
         "reading_order": ["4.2 Speed and Velocity", fx.PARA_A, fx.PARA_B, fx.PARA_C, fx.PARA_C,
                           fx.PARA_A.replace("Motion", "Movement"), fx.PARA_B]},
        {"page_index": 2, "category": ["english", "tables"],
         "reading_order": ["4.3 Units of Measurement", "Table 4.1 Quantities and their SI units", fx.PARA_B],
         "tables": [{"bbox": [0.15, 0.17, 0.87, 0.33],
                     "rows": [["Quantity", "SI unit", "Symbol"], ["Distance", "metre", "m"],
                              ["Time", "second", "s"], ["Speed", "metre per second", "m/s"]]}]},
        {"page_index": 3, "category": ["english", "figures"],
         "reading_order": ["4.4 Graphs of Motion", fx.PARA_A, "Figure 4.2 Distance-time graph of a moving bicycle"]},
        {"page_index": 4, "category": ["english", "equations"],
         "reading_order": ["4.5 Equations of Motion", fx.PARA_C, "v = u + a t (4.1)", fx.PARA_B]},
    ]
    return [(pdf, gold)]


def _markdown(report: dict[str, Any], notes: list[str]) -> str:
    lines = [f"# Evaluation: {report['dataset']}", "", f"**{report['warning']}**", "", "Engines: " + "; ".join(notes), "",
             "| Category | Pages | CER | WER | Reading order | Layout F1 | Table cells | Failure rate | s/page (incl. first model load) |",
             "|---|---|---|---|---|---|---|---|---|"]

    def f(value: Any) -> str:
        return "n/a" if value is None else f"{value:.3f}"

    for category, row in report["summary"].items():
        lines.append(f"| {category} | {row['pages']} | {f(row['mean_cer'])} | {f(row['mean_wer'])} | "
                     f"{f(row['mean_reading_order_pairwise'])} | {f(row['mean_layout_f1'])} | "
                     f"{f(row['mean_table_cell_accuracy'])} | {f(row['failure_rate'])} | {f(row['mean_seconds_per_page'])} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--synthetic", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pathya_eval_") as tmp:
        if args.synthetic:
            documents, name, synthetic = _synthetic(Path(tmp)), "synthetic-textbook", True
        else:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            base = args.manifest.parent
            documents = [(base / d["pdf"], json.loads((base / d["gold"]).read_text(encoding="utf-8")))
                         for d in manifest["documents"]]
            name, synthetic = manifest["dataset"], bool(manifest.get("synthetic", False))
        scores, notes = evaluate(documents)
    report = to_json(scores, dataset=name, synthetic=synthetic)
    report["engines"] = notes
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out / "report.md").write_text(_markdown(report, notes), encoding="utf-8")
    print(_markdown(report, notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
