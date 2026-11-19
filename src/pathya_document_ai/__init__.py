"""Pathya's P1 document-extraction package.

Public entry point (contract 1.2.0)::

    from pathya_document_ai import ExtractionOptions, extract_document, extract_to_json, validate_document_json

or on the command line: ``python -m pathya_document_ai extract <pdf|image> -o doc.json``.

Importing this package must not load engines, download models or write files,
so the public names are resolved lazily on first use.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ExtractionOptions", "ExtractionResult", "extract_document", "extract_to_json", "validate_document_json"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from pathya_document_ai import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module 'pathya_document_ai' has no attribute {name!r}")
