from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BinaryMetrics:
    precision: float
    recall: float
    false_positive_rate: float
    abstention_rate: float
    brier_score: float
    n: int


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def binary_tag_metrics(
    truth: list[bool],
    predicted_present_probability: list[float],
    actions: list[str],
    *,
    decision_threshold: float = 0.5,
) -> BinaryMetrics:
    if not (len(truth) == len(predicted_present_probability) == len(actions)):
        raise ValueError("truth, probability, and actions must have equal length")

    non_abstained = [a == "accept" for a in actions]
    tp = fp = tn = fn = 0
    for y, p, accepted in zip(truth, predicted_present_probability, non_abstained, strict=True):
        if not accepted:
            continue
        pred = p >= decision_threshold
        if y and pred:
            tp += 1
        elif not y and pred:
            fp += 1
        elif not y and not pred:
            tn += 1
        else:
            fn += 1

    brier = (
        sum((float(y) - p) ** 2 for y, p in zip(truth, predicted_present_probability, strict=True))
        / len(truth)
        if truth
        else 0.0
    )
    abstained = sum(1 for accepted in non_abstained if not accepted)
    return BinaryMetrics(
        precision=_safe_div(tp, tp + fp),
        recall=_safe_div(tp, tp + fn),
        false_positive_rate=_safe_div(fp, fp + tn),
        abstention_rate=_safe_div(abstained, len(actions)),
        brier_score=brier,
        n=len(truth),
    )


def top1_accuracy(truth: list[str], probability_rows: list[dict[str, float]]) -> float:
    if len(truth) != len(probability_rows):
        raise ValueError("truth and probability_rows must have equal length")
    if not truth:
        return 0.0
    correct = 0
    for expected, probs in zip(truth, probability_rows, strict=True):
        candidates = {k: v for k, v in probs.items() if k != "insufficient_evidence"}
        predicted = max(candidates, key=candidates.get) if candidates else None
        correct += int(predicted == expected)
    return correct / len(truth)
