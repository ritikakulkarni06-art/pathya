"""Deterministic, synthetic OpenAPI examples and application-wide problem catalog."""

import ast
import re
from pathlib import Path
from typing import Any, get_args

from pydantic_core.core_schema import ErrorType

DOC = "11111111-1111-4111-8111-111111111111"
BLOCK = "22222222-2222-4222-8222-222222222222"
ITEM = "33333333-3333-4333-8333-333333333333"
TEXT = "Synthetic authorized passage."


def problem(code: str, status: int, detail: str) -> dict[str, Any]:
    return {
        "type": "urn:pathya:error:" + code,
        "title": code.replace("_", " ").capitalize(),
        "status": status,
        "detail": detail,
        "code": code,
    }


def error_catalog() -> dict[str, dict[str, Any]]:
    codes: dict[str, dict[str, Any]] = {}

    def add(code: str, status: int, detail: str, origin: str = "application") -> None:
        entry = codes.setdefault(
            code, {"statuses": [], "origin": origin, "example": problem(code, status, detail)}
        )
        if status not in entry["statuses"]:
            entry["statuses"].append(status)
            entry["statuses"].sort()

    root = Path(__file__).resolve().parents[1]
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id in {"Problem", "problem_response"} and len(node.args) >= 3:
                status = (
                    node.args[0].value
                    if isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, int)
                    else 500
                )
                detail = (
                    node.args[2].value
                    if isinstance(node.args[2], ast.Constant)
                    and isinstance(node.args[2].value, str)
                    else "The operation could not be completed. Check the problem code."
                )
                candidates = (
                    [node.args[1].value]
                    if isinstance(node.args[1], ast.Constant)
                    else [
                        n.value
                        for n in ast.walk(node.args[1])
                        if isinstance(n, ast.Constant)
                        and isinstance(n.value, str)
                        and "_" in n.value
                    ]
                )
                for code in candidates:
                    if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]+", code):
                        add(code, status, detail)
            if (
                node.func.id == "PydanticCustomError"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                add(
                    str(node.args[0].value),
                    422,
                    "Extraction content is invalid. Check the schema and referenced page/block identifiers.",
                    "extraction_validation",
                )
            if (
                node.func.id == "rate_limit"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                add(
                    str(node.args[0].value) + "_rate_limited",
                    429,
                    "Too many requests for this action. Please wait before trying again.",
                )
    for code in get_args(ErrorType):
        add(
            str(code),
            422,
            "Extraction content is invalid. Check the schema and referenced page/block identifiers.",
            "pydantic_extraction_catalog",
        )
    for code in ["budget_exhausted", "pricing_unverified"]:
        add(
            code,
            402,
            "Paid speech is unavailable until its budget and verified tariff are configured. Text remains available.",
        )
    add(
        "invalid_extraction",
        422,
        "Extraction content is invalid. Check the schema and referenced page/block identifiers.",
    )
    return dict(sorted(codes.items()))


def structural_example(
    schema: dict[str, Any], components: dict[str, Any], name: str = "", depth: int = 0
) -> Any:
    if depth > 8:
        return None
    if "$ref" in schema:
        schema = components.get(schema["$ref"].rsplit("/", 1)[-1], {})
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    alternatives = schema.get("anyOf", schema.get("oneOf", []))
    if alternatives:
        return structural_example(
            next((s for s in alternatives if s.get("type") != "null"), alternatives[0]),
            components,
            name,
            depth + 1,
        )
    kind = schema.get("type")
    if kind == "object":
        return {
            key: structural_example(value, components, key, depth + 1)
            for key, value in schema.get("properties", {}).items()
            if key in schema.get("required", [])
        }
    if kind == "array":
        if "prefixItems" in schema:
            return [
                structural_example(s, components, name, depth + 1) for s in schema["prefixItems"]
            ]
        return [
            structural_example(schema.get("items", {}), components, name, depth + 1)
            for _ in range(schema.get("minItems", 0))
        ]
    if kind == "boolean":
        return False
    if kind in {"integer", "number"}:
        return max(1, schema.get("minimum", 1))
    if kind == "string":
        if name == "email":
            return "student@example.invalid"
        if name == "password":
            return "EXAMPLE-only-password-123"
        if name.endswith("id") or name.endswith("_id"):
            return ITEM
        return "Synthetic example value"[: schema.get("maxLength", 128)]
    return {} if not schema else None


def answer_example(abstain: bool = False) -> dict[str, Any]:
    return {
        "id": ITEM,
        "origin": "ai_explanation",
        "label": "AI explanation",
        "document_id": DOC,
        "document_revision": 1,
        "claims": []
        if abstain
        else [{"text": '"' + TEXT + '"', "evidence": [{"block_id": BLOCK, "rev": 1}]}],
        "abstain": abstain,
        "reason": "assistant_disabled" if abstain else None,
        "uncertainty_notes": [],
        "needs_human_check": False,
        "model_id": "EXAMPLE_MODEL_ID",
        "prompt_version": "answer_v1",
        "status": "current",
        "stale": False,
        "evidence": [
            {
                "block_id": BLOCK,
                "rev": 1,
                "text": TEXT,
                "page_id": ITEM,
                "page_refs": [{"id": ITEM, "pdf_index_0": 0, "printed_label": "1"}],
                "markers": ["not_scored"],
            }
        ],
        "evidence_candidates": [],
        "next_action": "read_evidence",
        "return_token": {"id": ITEM, "document_id": DOC, "revision": 1, "block_id": BLOCK},
    }


def block_example() -> dict[str, Any]:
    return {
        "id": BLOCK,
        "page_id": ITEM,
        "type": "paragraph",
        "parent_id": None,
        "order_key": 1,
        "text_current": TEXT,
        "lang": "en",
        "revision": 1,
        "status": "not_scored",
        "bbox": [0, 0, 100, 20],
        "confidence": {},
        "provenance": {"parser": "synthetic_example"},
        "successor_ids": [],
        "metadata": {},
        "critical_flag": False,
        "historical": False,
        "origin": "source_text",
        "synthetic": True,
    }


def document_example() -> dict[str, Any]:
    return {
        "id": DOC,
        "title": "Synthetic authorized chapter",
        "rights_note": "Synthetic example material.",
        "languages": ["en", "hi"],
        "current_revision": 1,
        "state": "review_required",
        "retention_until": "2026-12-18T00:00:00Z",
        "created_at": "2026-11-18T00:00:00Z",
        "updated_at": "2026-11-18T00:00:00Z",
        "counts": {"pages": 1, "blocks": 1},
    }


def enhance_openapi(schema: dict[str, Any]) -> dict[str, Any]:
    catalog = error_catalog()
    schema["x-pathya-error-catalog"] = catalog
    schema["x-pathya-catalog-note"] = (
        "Application-wide and extraction-library catalog; not every code occurs on every route. All values/examples are synthetic."
    )
    schema["x-pathya-abstention-reasons"] = [
        "no_evidence",
        "low_support",
        "source_needs_review",
        "stale_revision",
        "assistant_disabled",
        "assistant_unavailable",
        "budget_exhausted",
        "answer_failed_validation",
    ]
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components["Problem"] = {
        "type": "object",
        "required": ["type", "title", "status", "detail", "code"],
        "properties": {
            "type": {"type": "string"},
            "title": {"type": "string"},
            "status": {"type": "integer"},
            "detail": {"type": "string"},
            "code": {"type": "string"},
        },
        "additionalProperties": True,
    }
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "patch", "put", "delete", "head", "options"}:
                continue
            for content in operation.get("requestBody", {}).get("content", {}).values():
                content.setdefault(
                    "examples",
                    {
                        "synthetic": {
                            "summary": "Synthetic structural example; upload file values represent binary form parts.",
                            "value": structural_example(content.get("schema", {}), components),
                        }
                    },
                )
            responses = operation.setdefault("responses", {})
            responses["default"] = {
                "description": "RFC 7807-style problem. Consult x-pathya-error-catalog and the frontend handoff for operation-specific codes.",
                "content": {
                    "application/problem+json": {
                        "schema": {"$ref": "#/components/schemas/Problem"},
                        "examples": {
                            "problem": {
                                "value": problem(
                                    "invalid_request",
                                    422,
                                    "Some fields are invalid. Please check the request format.",
                                )
                            }
                        },
                    }
                },
            }
            if "422" in responses:
                responses["422"] = {
                    "description": "Safe field validation problem; input values are not echoed.",
                    "content": {
                        "application/problem+json": {
                            "schema": {"$ref": "#/components/schemas/Problem"},
                            "examples": {
                                "invalid_request": {
                                    "value": problem(
                                        "invalid_request",
                                        422,
                                        "Some fields are invalid. Please check the request format.",
                                    )
                                }
                            },
                        }
                    },
                }
            for status, response in responses.items():
                if not status.startswith("2") or status == "204":
                    continue
                content = response.setdefault("content", {}).setdefault(
                    "application/json", {"schema": {"type": "object"}}
                )
                value = structural_example(content.get("schema", {}), components)
                if path == "/healthz":
                    value = {"status": "ok"}
                elif path == "/readyz":
                    value = {"status": "ready"}
                elif path == "/documents" and method == "post":
                    value = {"document_id": DOC, "job_id": ITEM}
                elif path == "/documents" and method == "get":
                    value = {"documents": [document_example()]}
                elif path == "/documents/{document_id}" and method == "get":
                    value = document_example()
                elif path == "/documents/{document_id}/content":
                    value = {"document_id": DOC, "revision": 1, "blocks": [block_example()]}
                elif path == "/blocks/{block_id}" and method == "get":
                    value = {**block_example(), "document_revision": 1}
                elif path == "/documents/{document_id}/review-queue":
                    value = {
                        "blocks": [
                            {
                                **block_example(),
                                "status": "needs_review",
                                "critical_flag": True,
                                "printed_label": "1",
                                "reason": "A critical extraction symbol needs review.",
                                "crop_reference": None,
                            }
                        ]
                    }
                elif path == "/documents/{document_id}/manifest":
                    value = {
                        "demo_mode": True,
                        "import_quality_flags": ["synthetic_demo_only"],
                        "document_id": DOC,
                        "revision": 1,
                        "pages": [
                            {
                                "id": ITEM,
                                "pdf_index_0": 0,
                                "printed_label": "1",
                                "width": 612,
                                "height": 792,
                                "rotation": 0,
                            }
                        ],
                        "blocks": [{"id": BLOCK, "revision": 1, "status": "not_scored"}],
                        "edges": [],
                        "artifacts": [{"block_id": BLOCK, "status": "text_only"}],
                        "packages": [],
                        "text_available": True,
                    }
                elif path == "/documents/{document_id}/search":
                    value = {
                        "document_revision": 1,
                        "results": [
                            {
                                "id": ITEM,
                                "document_revision": 1,
                                "text": TEXT,
                                "heading_context": "",
                                "block_ids": [BLOCK],
                                "block_revisions": {BLOCK: 1},
                                "page_refs": [{"id": ITEM, "pdf_index_0": 0, "printed_label": "1"}],
                                "markers": ["not_scored"],
                                "offsets": [{"block_id": BLOCK, "start": 0, "end": len(TEXT)}],
                                "evidence": [
                                    {"block_id": BLOCK, "rev": 1, "text": TEXT, "page_id": ITEM}
                                ],
                                "score": 1 / 61,
                                "lexical_score": 1.0,
                                "neighbor_block_ids": [],
                            }
                        ],
                    }
                elif path == "/answers/{answer_id}":
                    value = {**answer_example(), "current_document_revision": 1, "warning": None}
                elif path == "/documents/{document_id}/packages" and method == "post":
                    value = {
                        "id": ITEM,
                        "revision": 1,
                        "sha256": "a" * 64,
                        "total_bytes": 2048,
                        "asset_id": ITEM,
                    }
                elif path == "/documents/{document_id}/packages/{package_id}":
                    value = {
                        "document_id": DOC,
                        "revision": 1,
                        "manifest_id": ITEM,
                        "manifest_sha256": "a" * 64,
                        "manifest": {"document_id": DOC, "revision": 1},
                        "text": [{"id": BLOCK, "text_current": TEXT, "revision": 1}],
                        "files": [],
                        "model_downloads_included": False,
                    }
                elif path == "/documents/{document_id}/reindex":
                    value = {
                        "job_id": ITEM,
                        "message": "The current eligible chapter text will be indexed.",
                    }
                elif path == "/blocks/{block_id}/audio" and method == "post":
                    value = {"job_id": ITEM}
                elif path == "/documents/{document_id}/glossary" and method == "get":
                    value = {"terms": []}
                elif path == "/admin/jobs":
                    value = {"jobs": []}
                elif path == "/admin/storage":
                    value = {"documents": [], "bytes_stored": 0, "free_bytes": 100000000}
                elif path == "/admin/metrics":
                    value = {
                        "queue_depth": 0,
                        "failures": 0,
                        "jobs": [],
                        "observed_stage_durations": [],
                        "bytes_stored": 0,
                        "usage": {"attempts": 0, "cost_inr_micro": 0},
                    }
                elif path == "/admin/usage":
                    value = {
                        "total": {"cost_inr_micro": 0},
                        "by_kind": [],
                        "by_document": [],
                        "by_day": [],
                        "by_call": [],
                    }
                elif path == "/jobs/{job_id}":
                    value = {
                        "id": ITEM,
                        "document_id": DOC,
                        "state": "review_required",
                        "attempts": 1,
                        "max_attempts": 3,
                        "last_error_code": None,
                        "reason": "A critical extraction symbol needs review.",
                        "progress": {"pages_total": 10, "pages_done": 10},
                    }
                elif path == "/blocks/{block_id}" and method == "patch":
                    value = {
                        "document_revision": 2,
                        "block_revision": 2,
                        "stale": {"audio": 1, "chunks": 1, "embeddings": 0, "answers": 1},
                        "rebuild_job_id": ITEM,
                        "successor_ids": [],
                    }
                elif path == "/questions":
                    content["examples"] = {
                        "answer": {
                            "summary": "Synthetic generated explanation shape; no real model result.",
                            "value": answer_example(),
                        },
                        "assistant_disabled": {
                            "summary": "Extractive source fallback with generation disabled.",
                            "value": answer_example(True),
                        },
                    }
                    continue
                elif path == "/documents/{document_id}" and method == "delete":
                    value = {
                        "receipt_id": ITEM,
                        "document_id": DOC,
                        "requested_at": "2026-11-18T00:00:00Z",
                        "completes_by": "2026-11-25T00:00:00Z",
                        "status": "pending",
                        "status_url": "/deletions/" + ITEM,
                        "completed_at": None,
                        "counts": {},
                        "error_code": None,
                        "purge_local_copy": True,
                        "overdue": False,
                    }
                content.setdefault(
                    "examples",
                    {
                        "synthetic": {
                            "summary": "Synthetic structural response; populated workflow examples are in docs/API_FOR_FRONTEND.md.",
                            "value": value,
                        }
                    },
                )
            if path == "/documents" and method == "post":
                responses["200"] = {
                    "description": "Existing source for this owner; no additional daily page charge.",
                    "content": {
                        "application/json": {
                            "examples": {
                                "duplicate": {
                                    "value": {"document_id": DOC, "job_id": ITEM, "duplicate": True}
                                }
                            }
                        }
                    },
                }
            if path == "/blocks/{block_id}" and method == "patch":
                conflict = problem(
                    "revision_conflict",
                    409,
                    "This passage changed while you were editing. Compare both versions before retrying.",
                )
                conflict.update(
                    current_revision=2,
                    your_base=1,
                    current_text=TEXT,
                    your_text="Your proposed authorized passage.",
                    field_hints=[
                        "Compare both versions, reconcile the text, then retry with current_revision as base_revision."
                    ],
                )
                responses["409"] = {
                    "description": "Conflict recorded; no last-writer-wins update.",
                    "content": {
                        "application/problem+json": {"examples": {"conflict": {"value": conflict}}}
                    },
                }
            if path == "/documents/{document_id}/manifest":
                responses["410"] = {
                    "description": "Owner sees deletion/purge instructions; invisible/formerly granted documents return 404.",
                    "content": {
                        "application/problem+json": {
                            "examples": {
                                "deleted": {
                                    "value": {
                                        **problem(
                                            "document_deleted",
                                            410,
                                            "This document was removed. Delete its offline copies.",
                                        ),
                                        "purge_local_copy": True,
                                    }
                                }
                            }
                        }
                    },
                }
            if path in {"/assets/{asset_id}", "/artifacts/{artifact_id}"}:
                responses["200"]["content"] = {
                    "application/octet-stream": {
                        "schema": {"type": "string", "format": "binary"},
                        "example": "Authorized binary bytes; use the actual Content-Type header.",
                    }
                }
                responses["206"] = {
                    "description": "Authorized single byte range; Content-Range and actual asset Content-Type apply.",
                    "content": {
                        "application/octet-stream": {
                            "schema": {"type": "string", "format": "binary"},
                            "example": "Requested binary byte range.",
                        }
                    },
                }
    return schema
