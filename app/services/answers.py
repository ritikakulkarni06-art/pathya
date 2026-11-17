import hashlib
import json
import re
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pydantic import ValidationError

from app.adapters.llm import DisabledLLM, GeminiClient, LLMClient, LLMUnavailable
from app.clock import now_utc
from app.config import Settings
from app.db.connection import Database
from app.errors import Problem
from app.logging import log_event
from app.schemas.answers import GeneratedAnswer, QuestionRequest
from app.services.access import check_document
from app.services.costs import BudgetExhausted
from app.services.retrieval.chunker import words
from app.services.retrieval.eligibility import is_eligible
from app.services.retrieval.search import search_snapshot

PROMPT_VERSION = "answer_v1"
PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "answer_v1.txt"
NEGATIONS = {
    "no",
    "not",
    "never",
    "without",
    "cannot",
    "neither",
    "nor",
    "nahi",
    "\u0928\u0939\u0940\u0902",
    "\u0928",
    "\u092e\u0924",
}
UNITS = {
    "kg",
    "g",
    "mg",
    "km",
    "cm",
    "mm",
    "m",
    "s",
    "ms",
    "ml",
    "l",
    "mol",
    "hz",
    "celsius",
    "kelvin",
    "percent",
    "\u0915\u093f\u0917\u094d\u0930\u093e",
    "\u092e\u0940\u091f\u0930",
}


class EntailmentChecker(Protocol):
    def check(self, claim: str, evidence: list[str]) -> str: ...


class AnswerValidationError(Exception):
    pass


def conflicting_evidence(evidence: list[dict[str, Any]]) -> bool:
    """Conservative signal for otherwise identical sentences with changed numbers/negation."""
    seen: dict[tuple[str, ...], tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for passage in evidence:
        for sentence in re.split(r"[.!?\n]", passage["text"]):
            terms = words(sentence)
            core = tuple(w for w in terms if w not in NEGATIONS and not any(c.isdigit() for c in w))
            if len(core) < 3:
                continue
            signal = (
                tuple(re.findall(r"\d+", sentence)),
                tuple(w for w in terms if w in NEGATIONS),
            )
            if core in seen and seen[core] != signal:
                return True
            seen[core] = signal
    return False


def validate_answer(
    raw: dict[str, Any],
    allowed: dict[str, dict[str, Any]],
    revision: int,
    model_id: str,
    checker: EntailmentChecker | None = None,
) -> tuple[GeneratedAnswer, bool]:
    try:
        answer = GeneratedAnswer.model_validate(raw)
    except ValidationError:
        raise AnswerValidationError("schema") from None
    if answer.document_revision != revision or answer.model_id != model_id:
        raise AnswerValidationError("revision_or_model")
    if answer.abstain == bool(answer.claims):
        raise AnswerValidationError("claims_state")
    needs_check = False
    for claim in answer.claims:
        passages = []
        for citation in claim.evidence:
            block = allowed.get(citation.block_id)
            if block is None or citation.rev != block["rev"]:
                raise AnswerValidationError("citation")
            passages.append(block["text"])
        quotes = re.findall(
            r'"([^"\n]+)"|\u201c([^\u201d\n]+)\u201d|(?<!\w)\x27([^\x27\n]+)\x27(?!\w)', claim.text
        )
        if any(
            not any(next(part for part in quoted if part) in p for p in passages)
            for quoted in quotes
        ):
            raise AnswerValidationError("quote")
        source = "\n".join(passages)
        source_words = set(words(source))
        claim_words = set(words(claim.text))
        numbers = set(re.findall(r"\d+(?:[.,]\d+)*", claim.text))
        source_numbers = set(re.findall(r"\d+(?:[.,]\d+)*", source))
        if not numbers.issubset(source_numbers) or not (claim_words & (NEGATIONS | UNITS)).issubset(
            source_words
        ):
            needs_check = True
        if "%" in claim.text and "%" not in source:
            needs_check = True
        if checker is not None and checker.check(claim.text, passages) != "supported":
            needs_check = True
    return answer, needs_check


def _review_candidates(
    database: Database,
    document_id: str,
    user_id: str,
    query: str,
    scope: list[str] | None,
) -> list[str]:
    query_words = set(words(query)) - {"the", "is", "a", "what", "how", "of", "in", "and"}
    if not query_words:
        return []
    with database.read_conn() as connection:
        check_document(connection, document_id, user_id)
        return [
            block["id"]
            for block in connection.execute(
                "SELECT * FROM blocks WHERE document_id=? AND json_array_length(successor_ids_json)=0",
                (document_id,),
            )
            if (scope is None or block["id"] in scope)
            and (block["critical_flag"] or block["status"] in {"needs_review", "unsupported"})
            and query_words.intersection(words(block["text_current"]))
        ][:20]


def _abstain(body: dict[str, Any], reason: str, candidates: list[str] | None = None) -> None:
    body.update(
        abstain=True,
        claims=[],
        reason=reason,
        evidence_candidates=candidates or [],
        next_action="open_review"
        if reason == "source_needs_review"
        else "refresh_revision"
        if reason == "stale_revision"
        else "read_evidence"
        if body["evidence"]
        else "search_chapter",
    )


def ask(
    database: Database,
    settings: Settings,
    user_id: str,
    request: QuestionRequest,
    *,
    llm: LLMClient | None = None,
    checker: EntailmentChecker | None = None,
) -> dict[str, Any]:
    with database.read_conn() as connection:
        doc = check_document(connection, request.document_id, user_id)
    if len(request.question) > settings.question_max_chars or not request.question.strip():
        raise Problem(422, "invalid_question", "Use a shorter question with at least one word.")
    revision = doc["current_revision"]
    body: dict[str, Any] = {
        "id": str(uuid4()),
        "origin": "ai_explanation",
        "label": "AI explanation",
        "document_id": request.document_id,
        "document_revision": revision,
        "claims": [],
        "abstain": True,
        "uncertainty_notes": [],
        "evidence": [],
        "model_id": "disabled",
        "prompt_version": PROMPT_VERSION,
        "needs_human_check": False,
        "status": "current",
        "stale": False,
        "return_token": {
            "id": str(uuid4()),
            "document_id": request.document_id,
            "revision": revision,
            "block_id": None,
        },
    }
    allowed: dict[str, dict[str, Any]] = {}
    if request.revision is not None and request.revision != revision:
        _abstain(body, "stale_revision")
    else:
        snapshot = search_snapshot(
            database,
            settings,
            request.document_id,
            user_id,
            request.question,
            block_scope=request.block_scope,
        )
        revision = snapshot["document_revision"]
        body["document_revision"] = revision
        body["return_token"]["revision"] = revision
        results = snapshot["results"]
        if request.revision is not None and request.revision != revision:
            results = []
            _abstain(body, "stale_revision")
        else:
            for chunk in results:
                for evidence in chunk["evidence"]:
                    # Use the exact trusted chunk excerpt, including reviewed media metadata.
                    bid = evidence["block_id"]
                    # Exact prose slices keep full chapters out of an LLM payload.
                    slices = [o for o in chunk["offsets"] if o["block_id"] == bid]
                    text = (
                        "\n".join(evidence["text"][o["start"] : o["end"]] for o in slices)
                        if slices
                        else evidence["text"]
                    )
                    if not text.strip():
                        continue
                    entry = allowed.setdefault(
                        bid,
                        {
                            **evidence,
                            "text": "",
                            "page_refs": chunk["page_refs"],
                            "markers": chunk["markers"],
                        },
                    )
                    if text and text not in entry["text"]:
                        entry["text"] += ("\n" if entry["text"] else "") + text
            body["evidence"] = list(allowed.values())
            if allowed:
                body["return_token"]["block_id"] = next(iter(allowed))
            quality = max((r["lexical_score"] for r in results), default=0)
            if not results or quality < settings.answer_no_evidence_threshold:
                candidates = _review_candidates(
                    database, request.document_id, user_id, request.question, request.block_scope
                )
                _abstain(body, "source_needs_review" if candidates else "no_evidence", candidates)
            elif quality < settings.answer_low_support_threshold or conflicting_evidence(
                body["evidence"]
            ):
                _abstain(body, "low_support")
            else:
                client = llm or (
                    GeminiClient(settings, database, request.document_id, user_id)
                    if settings.llm_enabled
                    else DisabledLLM()
                )
                payload = {
                    "question": request.question,
                    "document_revision": revision,
                    "evidence": [
                        {"block_id": b["block_id"], "rev": b["rev"], "text": b["text"]}
                        for b in allowed.values()
                    ],
                }
                try:
                    result = client.generate_structured(
                        PROMPT.read_text(encoding="utf-8")
                        + "\nConfigured model_id: "
                        + (settings.llm_model_id if settings.llm_enabled else "fake-scripted-v1"),
                        payload,
                        GeneratedAnswer.model_json_schema(),
                        settings.llm_max_output_tokens,
                        settings.llm_timeout_seconds,
                    )
                    answer, needs_check = validate_answer(
                        result.parsed, allowed, revision, result.model_id, checker
                    )
                    body.update(answer.model_dump(), needs_human_check=needs_check)
                    if answer.abstain:
                        _abstain(body, "low_support")
                    else:
                        body.update(
                            reason=None, evidence_candidates=[], next_action="read_evidence"
                        )
                except BudgetExhausted:
                    _abstain(body, "budget_exhausted")
                except LLMUnavailable as error:
                    reason = (
                        "assistant_disabled"
                        if error.code == "assistant_disabled"
                        else "assistant_unavailable"
                    )
                    body["uncertainty_notes"] = [error.code]
                    _abstain(body, reason)
                except AnswerValidationError as error:
                    log_event(event="answer_validation_failed", category=str(error))
                    _abstain(body, "answer_failed_validation")
    return _save(database, user_id, request, body, allowed)


def _save(
    database: Database,
    user_id: str,
    request: QuestionRequest,
    body: dict[str, Any],
    allowed: dict[str, Any],
) -> dict[str, Any]:
    with database.write_tx() as connection:
        doc = check_document(connection, request.document_id, user_id)
        if doc["current_revision"] != body["document_revision"]:
            body["document_revision"] = doc["current_revision"]
            body["evidence"] = []
            body["return_token"].update(revision=doc["current_revision"], block_id=None)
            body["uncertainty_notes"] = []
            _abstain(body, "stale_revision")
        else:
            for bid, evidence in allowed.items():
                block = connection.execute(
                    "SELECT * FROM blocks WHERE id=? AND document_id=?", (bid, request.document_id)
                ).fetchone()
                if block is None or not is_eligible(block, evidence["rev"]):
                    body["evidence"] = []
                    body["uncertainty_notes"] = []
                    body["return_token"]["block_id"] = None
                    _abstain(body, "stale_revision")
                    break
        connection.execute(
            "INSERT INTO answers VALUES (?,?,?,?,?,'ai_explanation',?,?,?,'current',?,?)",
            (
                body["id"],
                request.document_id,
                body["document_revision"],
                user_id,
                hashlib.sha256(request.question.encode()).hexdigest(),
                json.dumps(body, ensure_ascii=False),
                body["model_id"],
                PROMPT_VERSION,
                int(body["abstain"]),
                now_utc(),
            ),
        )
    return body


def get_answer(database: Database, answer_id: str, user_id: str) -> dict[str, Any]:
    with database.read_conn() as connection:
        connection.execute("BEGIN")
        row = connection.execute("SELECT * FROM answers WHERE id=?", (answer_id,)).fetchone()
        if row is None:
            raise Problem(404, "answer_not_found", "This explanation is unavailable.")
        doc = check_document(connection, row["document_id"], user_id)
        if row["user_id"] != user_id and doc["owner_id"] != user_id:
            raise Problem(404, "answer_not_found", "This explanation is unavailable.")
        body: dict[str, Any] = json.loads(row["response_json"])
        stale = row["status"] == "stale" or row["document_revision"] != doc["current_revision"]
        body.update(
            status="stale" if stale else "current",
            stale=stale,
            current_document_revision=doc["current_revision"],
            warning="The chapter changed. Ask again using the current revision." if stale else None,
        )
    return body
