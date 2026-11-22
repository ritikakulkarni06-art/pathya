"""Offline sample plumbing or authenticated API evaluation; never a human-support judge."""

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.adapters.embeddings import FakeEmbeddingProvider
from app.adapters.llm import FakeLLM
from app.main import create_app
from app.services.retrieval.index import build_index
from scripts.seed_demo import demo_settings, seed_demo


class EvalQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=128)
    category: Literal["supported", "absent", "misleading_premise", "damaged"]
    question: str = Field(min_length=1, max_length=2000)
    gold_block_ids: list[str] = Field(max_length=100)
    expected_abstain: bool
    sample: bool = False

    @field_validator("gold_block_ids")
    @classmethod
    def safe_ids(cls, ids: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) for value in ids):
            raise ValueError("Use opaque block identifiers.")
        return ids


def load_questions(path: Path) -> list[EvalQuestion]:
    try:
        questions = [
            EvalQuestion.model_validate(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not questions or len({q.id for q in questions}) != len(questions):
            raise ValueError("empty_or_duplicate")
        return questions
    except (ValueError, TypeError, ValidationError):
        raise ValueError(
            "The question file is invalid. Check its fields, IDs and duplicate records."
        ) from None


def ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "ratio": numerator / denominator if denominator else None,
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    should_abstain = [r for r in records if r["expected_abstain"]]
    supported = [r for r in records if r["category"] == "supported" and not r["expected_abstain"]]
    return {
        "evidence_recall_at_5": ratio(
            sum(r["gold_found"] for r in records), sum(r["gold_total"] for r in records)
        ),
        "citation_resolution": ratio(
            sum(r["resolved"] for r in records), sum(r["citations"] for r in records)
        ),
        "appropriate_abstention": ratio(
            sum(r["answer"]["abstain"] for r in should_abstain), len(should_abstain)
        ),
        "unnecessary_abstention": ratio(
            sum(r["answer"]["abstain"] for r in supported), len(supported)
        ),
        "supported_claims_human": ratio(0, 0),
        "unsupported_claims_human": ratio(0, 0),
        "needs_human_check_count": sum(bool(r["answer"].get("needs_human_check")) for r in records),
    }


def coverage_risk(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for threshold in [0.0, 0.1, 0.25, 0.5, 1.0]:
        answered = [
            r for r in records if not r["answer"]["abstain"] and r["lexical_score"] >= threshold
        ]
        rows.append(
            {
                "threshold": threshold,
                "coverage": ratio(len(answered), len(records)),
                "expected_abstain_errors": ratio(
                    sum(r["expected_abstain"] for r in answered), len(answered)
                ),
                "flagged_count": sum(bool(r["answer"].get("needs_human_check")) for r in answered),
                "human_unsupported_claims": ratio(0, 0),
            }
        )
    return rows


def safe_csv(value: Any) -> str:
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def _ok(response: httpx.Response) -> dict[str, Any]:
    if response.status_code != 200:
        raise RuntimeError(
            "An evaluation request failed with HTTP " + str(response.status_code) + "."
        )
    value = response.json()
    if not isinstance(value, dict):
        raise RuntimeError("The evaluation API returned an unsupported response.")
    return value


def _request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> httpx.Response:
    try:
        return client.request(method, path, **kwargs)
    except httpx.HTTPError:
        raise RuntimeError(
            "The evaluation API is unavailable. No automatic retry was made."
        ) from None


def execute(
    client: httpx.Client, document_id: str, questions: list[EvalQuestion], *, fake: bool = False
) -> list[dict[str, Any]]:
    records = []
    for question in questions:
        search = _ok(
            _request(
                client,
                "GET",
                "/documents/" + document_id + "/search",
                params={"q": question.question, "k": 5},
            )
        )
        results = search["results"]
        retrieved = {bid for chunk in results[:5] for bid in chunk["block_ids"]}
        gold = set(question.gold_block_ids)
        if fake:
            assert isinstance(client, TestClient)
            evidence = [e for chunk in results for e in chunk["evidence"] if e["text"].strip()]
            selected = next(
                (e for e in evidence if e["block_id"] in gold), evidence[0] if evidence else None
            )
            claims = (
                []
                if question.expected_abstain or selected is None
                else [
                    {
                        "text": json.dumps(selected["text"], ensure_ascii=False),
                        "evidence": [{"block_id": selected["block_id"], "rev": selected["rev"]}],
                    }
                ]
            )
            client.app.state.llm_client = FakeLLM(
                [
                    {
                        "origin": "ai_explanation",
                        "document_revision": search["document_revision"],
                        "claims": claims,
                        "abstain": not bool(claims),
                        "uncertainty_notes": ["Scripted sample outcome; not a quality measurement."]
                        if not claims
                        else [],
                        "model_id": "fake-scripted-v1",
                    }
                ]
            )
        answer = _ok(
            _request(
                client,
                "POST",
                "/questions",
                json={
                    "document_id": document_id,
                    "revision": search["document_revision"],
                    "question": question.question,
                },
            )
        )
        resolved = citations = 0
        for claim in answer["claims"]:
            for cite in claim["evidence"]:
                citations += 1
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", cite["block_id"]):
                    continue
                block_response = _request(client, "GET", "/blocks/" + cite["block_id"])
                if block_response.status_code == 200:
                    block = block_response.json()
                    resolved += (
                        block["revision"] == cite["rev"]
                        and block["document_revision"] == answer["document_revision"]
                    )
        records.append(
            {
                "id": question.id,
                "question": question.question,
                "category": question.category,
                "expected_abstain": question.expected_abstain,
                "sample": question.sample,
                "gold_found": len(gold & retrieved),
                "gold_total": len(gold),
                "resolved": resolved,
                "citations": citations,
                "lexical_score": max((r["lexical_score"] for r in results), default=0),
                "answer": answer,
            }
        )
    return records


def run_fake(questions: list[EvalQuestion]) -> list[dict[str, Any]]:
    if not all(q.sample for q in questions):
        raise ValueError(
            "Fake fixture mode accepts explicitly marked sample questions only. Use real mode for your reviewed corpus."
        )
    with tempfile.TemporaryDirectory(prefix="pathya-eval-") as temporary:
        directory = Path(temporary) / "demo"
        info = seed_demo(directory)
        settings = demo_settings(directory)
        with TestClient(create_app(settings)) as client:
            with client.app.state.database.read_conn() as c:
                mapping = {
                    r["external_id"]: r["internal_id"]
                    for r in c.execute(
                        "SELECT * FROM extraction_identifiers WHERE document_id=?",
                        (info["document_id"],),
                    )
                }
            if any(bid not in mapping for q in questions for bid in q.gold_block_ids):
                raise ValueError("Sample gold block IDs do not match the fixture chapter.")
            mapped = [
                q.model_copy(update={"gold_block_ids": [mapping[b] for b in q.gold_block_ids]})
                for q in questions
            ]
            embedder = FakeEmbeddingProvider()
            build_index(client.app.state.database, settings, info["document_id"], embedder=embedder)
            client.app.state.embedding_provider = embedder
            return execute(client, info["document_id"], mapped, fake=True)


def run_real(questions: list[EvalQuestion], url: str, document_id: str) -> list[dict[str, Any]]:
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Use an API origin URL without credentials, path, query or fragment.")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Evaluation of a remote API requires HTTPS.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", document_id):
        raise ValueError("Supply the selected document's opaque ID.")
    session, csrf = (
        os.environ.get("PATHYA_EVAL_SESSION", ""),
        os.environ.get("PATHYA_EVAL_CSRF", ""),
    )
    cookies: dict[str, str] = {}
    headers: dict[str, str] = {}
    if session:
        if (
            parsed.scheme != "https"
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", session)
            or not re.fullmatch(r"[0-9a-f]{64}", csrf)
        ):
            raise ValueError(
                "Session evaluation requires HTTPS and valid session/CSRF environment values."
            )
        cookies = {"pathya_session": session, "pathya_csrf": csrf}
        headers = {"X-CSRF-Token": csrf}
    with httpx.Client(
        base_url=url,
        cookies=cookies,
        headers=headers,
        timeout=60,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        return execute(client, document_id, questions)


TARGETS = {
    "evidence_recall_at_5": ">= 0.90",
    "citation_resolution": ">= 0.95",
    "appropriate_abstention": ">= 0.90",
    "unnecessary_abstention": "<= 0.20",
    "supported_claims_human": ">= 0.90",
    "unsupported_claims_human": "<= 0.05",
}


def write_report(records: list[dict[str, Any]], output: Path, mode: str, input_sha256: str) -> Path:
    destination = output / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    destination.mkdir(parents=True)
    notice = (
        "SAMPLE / FAKE: fixture plumbing only, not measured model or human evaluation accuracy."
        if mode == "fake"
        else "Automated diagnostics only. Citation resolution does not prove support; human ratings remain pending."
    )
    summary = {
        "mode": mode,
        "notice": notice,
        "input_sha256": input_sha256,
        "questions": len(records),
        "sample_input": any(r.get("sample", False) for r in records),
        "models": sorted({r["answer"].get("model_id", "unknown") for r in records}),
        "prompt_versions": sorted({r["answer"].get("prompt_version", "unknown") for r in records}),
        "document_revisions": sorted({r["answer"].get("document_revision", 0) for r in records}),
        "measured": summarize(records),
        "targets": TARGETS,
        "coverage_risk": coverage_risk(records),
        "sweep_limit": "Post-hoc additional abstention only; lower thresholds cannot recover already-abstained answers.",
    }
    (destination / "metrics.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    columns = [
        "id",
        "category",
        "question",
        "claim_index",
        "answer_claims",
        "cited_passages",
        "abstain",
        "reason",
        "rater1_supported",
        "rater2_supported",
        "adjudicated",
    ]
    with (destination / "human_ratings.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            answer = record["answer"]
            cards = {e["block_id"]: e for e in answer["evidence"]}
            for index, claim in enumerate(answer["claims"] or [{"text": "", "evidence": []}], 1):
                row = {
                    "id": record["id"],
                    "category": record["category"],
                    "question": record["question"],
                    "claim_index": index,
                    "answer_claims": claim["text"],
                    "cited_passages": json.dumps(
                        [cards[c["block_id"]] for c in claim["evidence"] if c["block_id"] in cards],
                        ensure_ascii=False,
                    ),
                    "abstain": answer["abstain"],
                    "reason": answer["reason"],
                    "rater1_supported": "",
                    "rater2_supported": "",
                    "adjudicated": "",
                }
                writer.writerow({key: safe_csv(value) for key, value in row.items()})
    print(notice)
    for name, target in TARGETS.items():
        value = summary["measured"][name]
        measured = "pending" if value["ratio"] is None else f"{value['ratio']:.3f}"
        print(f"{name}: {value['numerator']}/{value['denominator']} = {measured}; target {target}")
    print("needs_human_check_count: " + str(summary["measured"]["needs_human_check_count"]))
    print(
        "threshold | coverage numerator/denominator | expected-abstain errors/answered | human support"
    )
    for row in summary["coverage_risk"]:
        coverage, risk = row["coverage"], row["expected_abstain_errors"]
        print(
            f"{row['threshold']:.2f} | {coverage['numerator']}/{coverage['denominator']} | {risk['numerator']}/{risk['denominator']} | pending"
        )
    print("Private rating files: " + str(destination))
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run sample-only offline fixtures or an authorized existing API evaluation."
    )
    parser.add_argument("--questions", type=Path, default=Path("eval/data/sample.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("eval/out"))
    parser.add_argument("--mode", choices=["fake", "real"], default="fake")
    parser.add_argument("--url", default="")
    parser.add_argument("--document-id", default="")
    args = parser.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    questions = load_questions(args.questions)
    records = (
        run_fake(questions)
        if args.mode == "fake"
        else run_real(questions, args.url, args.document_id)
    )
    write_report(
        records, args.out, args.mode, hashlib.sha256(args.questions.read_bytes()).hexdigest()
    )


if __name__ == "__main__":
    main()
