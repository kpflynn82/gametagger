import pytest

from genometagger_v2.evaluation.metrics import binary_tag_metrics, top1_accuracy


def test_binary_metrics_count_abstention_separately():
    metrics = binary_tag_metrics(
        truth=[True, True, False, False],
        predicted_present_probability=[0.95, 0.70, 0.90, 0.10],
        actions=["accept", "deep_review", "accept", "accept"],
    )
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.false_positive_rate == pytest.approx(0.5)
    assert metrics.abstention_rate == pytest.approx(0.25)
    assert metrics.n == 4


def test_top1_accuracy_ignores_insufficient_as_genre_candidate():
    accuracy = top1_accuracy(
        truth=["Action RPG", "Puzzle"],
        probability_rows=[
            {"Action RPG": 0.6, "Puzzle": 0.1, "insufficient_evidence": 0.3},
            {"Action RPG": 0.2, "Puzzle": 0.7, "insufficient_evidence": 0.1},
        ],
    )
    assert accuracy == 1.0
