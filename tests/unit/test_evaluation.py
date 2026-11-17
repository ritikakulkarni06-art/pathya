"""Evaluation-metric tests: each metric must detect the error it is meant to measure."""

from __future__ import annotations

import pytest

from pathya_document_ai.evaluation import (
    PageScore,
    cer,
    detection_scores,
    edit_distance,
    reading_order_accuracy,
    summarize,
    table_cell_accuracy,
    to_json,
    wer,
)


def test_edit_distance_and_error_rates() -> None:
    assert edit_distance("kitten", "sitting") == 3
    assert cer("hello world", "hello world") == 0.0
    assert cer("hello", "hallo") == pytest.approx(0.2)
    assert wer("the quick fox", "the fox") == pytest.approx(1 / 3)
    assert cer("", "anything") is None  # no reference: undefined, not zero


def test_hindi_error_rates_use_nfc() -> None:
    decomposed, composed = "पढ़ना", "पढ़ना"
    assert cer(composed, decomposed) == 0.0
    assert cer("प्रकाश", "परकाश") > 0  # a dropped virama is an error


def test_reading_order_detects_swaps_and_missing_segments() -> None:
    gold = ["alpha one", "beta two", "gamma three"]
    assert reading_order_accuracy(gold, ["alpha one", "beta two", "gamma three"])["pairwise_accuracy"] == 1.0
    swapped = reading_order_accuracy(gold, ["gamma three", "beta two", "alpha one"])
    assert swapped["pairwise_accuracy"] == 0.0
    missing = reading_order_accuracy(gold, ["alpha one", "gamma three"])
    assert missing["unmatched_segments"] == 1 and missing["pairwise_accuracy"] == 1.0


def test_reading_order_matches_repeated_paragraphs_one_to_one() -> None:
    gold = ["same paragraph text", "other text here", "same paragraph text"]
    assert reading_order_accuracy(gold, ["same paragraph text", "other text here", "same paragraph text"])[
        "pairwise_accuracy"] == 1.0
    result = reading_order_accuracy(gold, ["same paragraph text", "same paragraph text", "other text here"])
    assert result["pairwise_accuracy"] < 1.0


def test_detection_scores_require_overlap_and_type() -> None:
    gold = [{"type": "heading", "bbox": [0.1, 0.1, 0.5, 0.15]}, {"type": "paragraph", "bbox": [0.1, 0.2, 0.9, 0.4]}]
    perfect = detection_scores(gold, gold)
    assert perfect["f1"] == 1.0
    wrong_type = detection_scores(gold, [{"type": "paragraph", "bbox": g["bbox"]} for g in gold])
    assert wrong_type["matched"] == 1
    shifted = detection_scores(gold, [{"type": g["type"], "bbox": [0.6, 0.6, 0.7, 0.7]} for g in gold])
    assert shifted["matched"] == 0 and shifted["f1"] is None


def test_table_accuracy_reports_missing_structure() -> None:
    gold = [["h1", "h2"], ["a", "b"]]
    assert table_cell_accuracy(gold, gold)["cell_accuracy"] == 1.0
    assert table_cell_accuracy(gold, [["h1", "h2"], ["a", "x"]])["cell_accuracy"] == 0.75
    missing = table_cell_accuracy(gold, None)
    assert missing["structure"] == "missing" and missing["cell_accuracy"] == 0.0


def test_summary_counts_failed_pages_and_labels_synthetic_results() -> None:
    def page(status: str, categories: list[str]) -> PageScore:
        return PageScore("doc", 0, categories, status, 0.1, 0.2, {"pairwise_accuracy": 1.0}, {})

    scores = [page("ok", ["hindi"]), page("needs_ocr", ["hindi", "scanned"]), page("failed", ["english"])]
    summary = summarize(scores)
    assert summary["all"]["failure_rate"] == pytest.approx(2 / 3)
    assert summary["hindi"]["pages"] == 2 and summary["scanned"]["failure_rate"] == 1.0
    report = to_json(scores, dataset="x", synthetic=True)
    assert report["synthetic"] and "NOT textbook accuracy" in report["warning"]
