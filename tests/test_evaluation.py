import csv
import json
from pathlib import Path

import pytest

from eval.run import (
    EvalQuestion,
    coverage_risk,
    load_questions,
    ratio,
    run_fake,
    run_real,
    safe_csv,
    summarize,
    write_report,
)


def record(category, expected, abstain, found, gold, resolved=0, citations=0):
    return {
        "category": category,
        "expected_abstain": expected,
        "gold_found": found,
        "gold_total": gold,
        "resolved": resolved,
        "citations": citations,
        "lexical_score": 0.5,
        "answer": {"abstain": abstain, "needs_human_check": False},
    }


def test_metrics_report_raw_denominators_and_leave_human_ratings_pending():
    records = [
        record("supported", False, False, 1, 2, 1, 1),
        record("supported", False, True, 1, 1),
        record("absent", True, True, 0, 0),
        record("damaged", True, False, 0, 1, 0, 1),
    ]
    values = summarize(records)
    assert values["evidence_recall_at_5"] == ratio(2, 4)
    assert values["citation_resolution"] == ratio(1, 2)
    assert values["appropriate_abstention"] == ratio(1, 2)
    assert values["unnecessary_abstention"] == ratio(1, 2)
    assert values["supported_claims_human"] == ratio(0, 0)
    assert ratio(0, 0)["ratio"] is None
    sweep = coverage_risk(records)
    assert sweep[0]["coverage"] == ratio(2, 4)
    assert sweep[0]["expected_abstain_errors"] == ratio(1, 2)
    assert sweep[-1]["coverage"] == ratio(0, 4)


def test_invalid_question_files_do_not_echo_question_input(tmp_path):
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps({"question": "PRIVATE QUESTION INPUT"}))
    with pytest.raises(ValueError) as failure:
        load_questions(path)
    assert "PRIVATE QUESTION INPUT" not in str(failure.value)
    question = EvalQuestion(
        id="q", category="absent", question="unicorn", gold_block_ids=[], expected_abstain=True
    )
    with pytest.raises(ValueError, match="sample"):
        run_fake([question])


@pytest.mark.parametrize(
    "url",
    [
        "http://external.invalid",
        "https://user:private@example.invalid",
        "https://example.invalid/path",
        "https://example.invalid?private=q",
    ],
)
def test_real_mode_rejects_unsafe_origins_before_network(url):
    with pytest.raises(ValueError):
        run_real([], url, "document")


def test_csv_source_cells_cannot_become_formulas():
    for text in ['=HYPERLINK("unsafe")', "+1+1", "-1+1", "@SUM(1)", " \t=1"]:
        assert safe_csv(text).startswith("'")
    assert safe_csv("Ordinary source text") == "Ordinary source text"


def test_twelve_marked_samples_run_through_real_pipeline_and_private_report(tmp_path, capsys):
    questions = load_questions(Path("eval/data/sample.jsonl"))
    assert len(questions) == 12 and all(q.sample for q in questions)
    records = run_fake(questions)
    assert len(records) == 12
    assert summarize(records)["citation_resolution"]["denominator"] > 0
    assert summarize(records)["unsupported_claims_human"]["ratio"] is None
    output = write_report(records, tmp_path / "reports", "fake", "sample-sha")
    report = json.loads((output / "metrics.json").read_text())
    assert "not measured" in report["notice"] and report["questions"] == 12
    with (output / "human_ratings.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) >= 12 and all(
        r["rater1_supported"] == "" and r["adjudicated"] == "" for r in rows
    )
    printed = capsys.readouterr().out
    assert "SAMPLE / FAKE" in printed and "target >= 0.90" in printed
    assert questions[0].question not in printed
    second = write_report(records, tmp_path / "reports", "fake", "sample-sha")
    assert second != output and (output / "human_ratings.csv").exists()
