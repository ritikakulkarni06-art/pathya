"""Command line: ``python -m pathya_document_ai {extract,validate} ...``

  python -m pathya_document_ai extract chapter.pdf -o chapter.json --source-uri asset://p3/123
  python -m pathya_document_ai extract page.png -o page.json --ocr always
  python -m pathya_document_ai extract chapter.pdf -o v11.json --target-version 1.1.0 --drop heading_level,role
  python -m pathya_document_ai validate chapter.json

Exit codes: 0 success; 2 unsupported or unreadable input; 3 contract validation
failed; 4 a required engine is unavailable; 5 the requested export version
cannot represent the document without loss.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pathya_document_ai", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    ex = sub.add_parser("extract", help="extract a PDF/PNG/JPEG/TIFF into a validated contract Document")
    ex.add_argument("source", type=Path)
    ex.add_argument("-o", "--output", type=Path, help="write JSON here (default: stdout)")
    ex.add_argument("--source-uri", help="opaque source reference assigned by P3")
    ex.add_argument("--title")
    ex.add_argument("--languages", default="hin,eng", help="Tesseract languages, comma separated")
    ex.add_argument("--ocr", choices=["auto", "always", "never"], default="auto")
    ex.add_argument("--layout", choices=["auto", "required", "never"], default="auto")
    ex.add_argument("--dpi", type=float, default=300.0, help="render DPI for OCR")
    ex.add_argument("--tessdata-dir", type=Path)
    ex.add_argument("--tesseract-cmd", type=Path)
    ex.add_argument("--docling-artifacts", type=Path)
    ex.add_argument("--target-version", help="export version (default: current)")
    ex.add_argument("--drop", default="", help="1.2.0 producer fields to drop explicitly when exporting older "
                                               "versions: heading_level,role")
    ex.add_argument("--indent", type=int, default=2)
    ex.add_argument("--report", type=Path, help="write engines, notes and timing as JSON here")

    va = sub.add_parser("validate", help="validate a contract Document JSON file")
    va.add_argument("document", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    from pydantic import ValidationError

    from pathya_document_ai.models import IncompatibleVersionError
    from pathya_document_ai.pdf import PdfInputError
    from pathya_document_ai.pipeline import (
        EngineUnavailableError,
        ExtractionOptions,
        ProducerContractError,
        extract_document,
        validate_document_json,
    )

    try:
        if args.command == "validate":
            document = validate_document_json(args.document.read_text(encoding="utf-8"))
            print(f"OK: {document.contract_family or 'pathya P1 content'} {document.schema_version}, "
                  f"{len(document.pages)} pages, {len(document.blocks)} blocks")
            return 0
        options = ExtractionOptions(
            source_uri=args.source_uri, title=args.title,
            languages=tuple(x.strip() for x in args.languages.split(",") if x.strip()),
            ocr=args.ocr, layout=args.layout, ocr_dpi=args.dpi, tessdata_dir=args.tessdata_dir,
            tesseract_cmd=args.tesseract_cmd, docling_artifacts=args.docling_artifacts)
        result = extract_document(args.source, options)
        drop = tuple(x.strip() for x in args.drop.split(",") if x.strip())
        text = result.to_json(args.target_version, drop=drop, indent=args.indent)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        else:
            sys.stdout.write(text + "\n")
        if args.report:
            args.report.write_text(json.dumps({"engines": result.engines, "notes": result.notes,
                                               "elapsed_s": result.elapsed_s}, indent=2) + "\n", encoding="utf-8")
        statuses = [p.status.value for p in result.document.pages]
        print(f"OK: {len(result.document.pages)} pages ({', '.join(sorted(set(statuses)))}), "
              f"{len(result.document.blocks)} blocks; engines {result.engines}", file=sys.stderr)
        return 0
    except EngineUnavailableError as exc:
        print(f"ERROR (engine): {exc}", file=sys.stderr)
        return 4
    except IncompatibleVersionError as exc:
        print(f"ERROR (export): {exc}", file=sys.stderr)
        return 5
    except (ProducerContractError, ValidationError) as exc:
        print(f"ERROR (contract): {exc}", file=sys.stderr)
        return 3
    except (PdfInputError, OSError) as exc:
        print(f"ERROR (input): {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
