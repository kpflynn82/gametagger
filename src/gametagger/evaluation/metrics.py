"""Explicit denominators. Supported-state calibration is not game-wide existence calibration."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

STATES = {"present", "absent", "insufficient_evidence", "conflicting_evidence"}


@dataclass(frozen=True)
class Measure:
    numerator: float
    denominator: int
    value: float | None


def measure(numerator, denominator):
    return asdict(Measure(numerator, denominator, numerator / denominator if denominator else None))


def valid_distribution(p, keys):
    return (
        isinstance(p, dict)
        and set(p) == set(keys)
        and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in p.values())
        and math.isclose(math.fsum(p.values()), 1, abs_tol=0.001, rel_tol=0)
    )


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    origin: Literal["human_review", "ai_suggestion", "legacy_reference", "unavailable"] = (
        "unavailable"
    )
    reviewer: str | None = None
    reviewed_at: str | None = None
    primary_genre: str | None = None
    boundary_note: str | None = None
    game_truth: dict[str, bool | None] = Field(default_factory=dict)
    supported_truth: dict[
        str, Literal["present", "absent", "insufficient_evidence", "conflicting_evidence"] | None
    ] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reviewed(self):
        if self.origin == "human_review" and not (
            self.reviewer and self.reviewer.strip() and self.reviewed_at
        ):
            raise ValueError("Human review requires a named reviewer and review date")
        return self


class TagMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    state: str | None = None
    execution: Literal["valid", "error", "not_evaluated"] = "not_evaluated"
    probabilities: dict[str, float] | None = None
    action: str | None = None
    evidence_eligible: bool = False
    support_verified: bool = False


class CaseMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str
    method: str
    mode: str
    platform: str = "unknown"
    status: Literal["complete", "partial", "error", "not_evaluated", "pending"]
    identity_eligible: bool = False
    evidence_available: bool | None = None
    first_attempt_success: bool | None = None
    retried: bool | None = None
    retry_recovered: bool | None = None
    primary_genre: str | None = None
    genre_execution: Literal["valid", "error", "not_evaluated"] = "not_evaluated"
    genre_probabilities: dict[str, float] | None = None
    genre_action: str | None = None
    genre_evidence_eligible: bool = False
    genre_support_verified: bool = False
    tags: dict[str, TagMeasurement] = Field(default_factory=dict)
    reference: Reference = Field(default_factory=Reference)


def operational_metrics(rows):
    n = len(rows)
    known_first = [r for r in rows if r.first_attempt_success is not None]
    retries = [r for r in rows if r.retried]
    known_retries = [r for r in retries if r.retry_recovered is not None]
    available = [r for r in rows if r.evidence_available is not None]
    return {
        "records": n,
        "completion": measure(sum(r.status == "complete" for r in rows), n),
        "first_attempt_success": measure(
            sum(r.first_attempt_success for r in known_first), len(known_first)
        ),
        "first_attempt_unknown": n - len(known_first),
        "retry_recovery": measure(
            sum(r.retry_recovered is True for r in known_retries), len(known_retries)
        ),
        "retry_recovery_unknown": sum(r.retry_recovered is None for r in retries),
        "terminal_errors": measure(sum(r.status == "error" for r in rows), n),
        "partial_results": measure(sum(r.status == "partial" for r in rows), n),
        "not_evaluated": measure(sum(r.status in {"not_evaluated", "pending"} for r in rows), n),
        "identity_eligibility": measure(sum(r.identity_eligible for r in rows), n),
        "no_evidence": measure(sum(not r.evidence_available for r in available), len(available)),
        "evidence_availability_unknown": n - len(available),
    }


def genre_metrics(rows, genre_ids):
    keys = set(genre_ids) | {"insufficient_evidence"}
    labelled = [
        r
        for r in rows
        if r.reference.origin == "human_review" and r.reference.primary_genre in genre_ids
    ]

    def valid(r):
        return r.genre_execution == "valid" and (
            r.genre_probabilities is None or valid_distribution(r.genre_probabilities, keys)
        )

    def emitted(r):
        return (
            valid(r)
            and r.primary_genre in genre_ids
            and (
                r.genre_probabilities is None
                or (
                    r.genre_probabilities[r.primary_genre] == max(r.genre_probabilities.values())
                    and r.genre_probabilities[r.primary_genre]
                    > r.genre_probabilities["insufficient_evidence"]
                )
            )
        )

    def published(r):
        return (
            emitted(r)
            and r.identity_eligible
            and r.genre_evidence_eligible
            and r.genre_support_verified
            and r.genre_action == "accept"
        )

    diagnostic = [
        r for r in labelled if valid(r) and valid_distribution(r.genre_probabilities, keys)
    ]

    def candidate(r):
        return sorted(genre_ids, key=lambda k: (-r.genre_probabilities[k], k))[0]

    e = [r for r in labelled if emitted(r)]
    p = [r for r in labelled if published(r)]
    confusion = Counter(
        (r.reference.primary_genre, r.primary_genre if emitted(r) else "<no emitted primary>")
        for r in labelled
    )
    eligible_labelled = [r for r in labelled if r.identity_eligible]
    return {
        "actual_primary_correctness": measure(
            sum(
                emitted(r) and r.primary_genre == r.reference.primary_genre
                for r in eligible_labelled
            ),
            len(eligible_labelled),
        ),
        "identity_excluded_human_labels": len(labelled) - len(eligible_labelled),
        "human_label_count": len(labelled),
        "execution_errors": sum(r.genre_execution == "error" for r in rows),
        "not_evaluated": sum(r.genre_execution == "not_evaluated" for r in rows),
        "forced_choice_candidate_accuracy_diagnostic": measure(
            sum(candidate(r) == r.reference.primary_genre for r in diagnostic), len(diagnostic)
        ),
        "emitted_primary_accuracy": measure(
            sum(r.primary_genre == r.reference.primary_genre for r in e), len(e)
        ),
        "primary_coverage": measure(sum(emitted(r) for r in rows), len(rows)),
        "labelled_primary_coverage": measure(len(e), len(labelled)),
        "end_to_end_correct_primary": measure(
            sum(r.primary_genre == r.reference.primary_genre for r in e), len(labelled)
        ),
        "publishable_precision": measure(
            sum(r.primary_genre == r.reference.primary_genre for r in p), len(p)
        ),
        "publication_coverage": measure(sum(published(r) for r in rows), len(rows)),
        "published_without_human_truth": sum(published(r) for r in rows) - len(p),
        "invalid_distributions": sum(
            r.genre_probabilities is not None
            and not valid_distribution(r.genre_probabilities, keys)
            for r in rows
        ),
        "confusion_counts": [
            {"truth": a, "prediction": b, "count": n} for (a, b), n in sorted(confusion.items())
        ],
    }


def tag_metrics(rows, tag_id):
    def tag(r):
        return r.tags.get(tag_id, TagMeasurement())

    def good(r):
        t = tag(r)
        return (
            t.execution == "valid"
            and t.state in STATES
            and (
                t.probabilities is None
                or (
                    valid_distribution(t.probabilities, STATES)
                    and t.probabilities[t.state] == max(t.probabilities.values())
                )
            )
        )

    def accepted(r):
        t = tag(r)
        return (
            good(r)
            and t.state in {"present", "absent"}
            and t.action == "accept"
            and r.identity_eligible
            and t.evidence_eligible
            and t.support_verified
        )

    labelled = [
        r
        for r in rows
        if r.identity_eligible
        and r.reference.origin == "human_review"
        and r.reference.supported_truth.get(tag_id) in STATES
    ]

    def truth(r):
        return r.reference.supported_truth[tag_id]

    binary = [r for r in labelled if truth(r) in {"present", "absent"}]
    acc = [r for r in labelled if accepted(r)]
    positives = [r for r in binary if truth(r) == "present"]
    negatives = [r for r in binary if truth(r) == "absent"]
    tp = sum(truth(r) == "present" and tag(r).state == "present" for r in acc)
    fp = sum(truth(r) != "present" and tag(r).state == "present" for r in acc)
    binary_fp = sum(truth(r) == "absent" and tag(r).state == "present" for r in acc)
    fn = sum(truth(r) == "present" and tag(r).state == "absent" for r in acc)
    tn = sum(truth(r) == "absent" and tag(r).state == "absent" for r in acc)
    scored = [r for r in labelled if good(r) and valid_distribution(tag(r).probabilities, STATES)]
    brier = sum(
        sum((tag(r).probabilities[k] - float(truth(r) == k)) ** 2 for k in STATES) for r in scored
    )
    valid_labels = [r for r in labelled if good(r)]
    calibration = []
    for low in range(10):
        bucket = [r for r in scored if min(int(tag(r).probabilities[tag(r).state] * 10), 9) == low]
        calibration.append(
            {
                "lower": low / 10,
                "upper": (low + 1) / 10,
                "count": len(bucket),
                "mean_selected_probability": measure(
                    sum(tag(r).probabilities[tag(r).state] for r in bucket), len(bucket)
                ),
                "empirical_correctness": measure(
                    sum(tag(r).state == truth(r) for r in bucket), len(bucket)
                ),
            }
        )
    game_positive = [
        r
        for r in rows
        if r.identity_eligible
        and r.reference.origin == "human_review"
        and r.reference.game_truth.get(tag_id) is True
    ]
    outcomes = Counter(tag(r).state for r in rows if good(r))
    conf = Counter(
        (truth(r), tag(r).state if good(r) else "<execution incomplete>") for r in labelled
    )
    return {
        "records": len(rows),
        "human_supported_labels": len(labelled),
        "new_outcomes": {k: outcomes[k] for k in sorted(STATES)},
        "errors": sum(
            tag(r).execution == "error"
            or (tag(r).execution == "valid" and not good(r))
            or (
                tag(r).probabilities is not None
                and not valid_distribution(tag(r).probabilities, STATES)
            )
            for r in rows
        ),
        "not_evaluated": sum(tag(r).execution == "not_evaluated" for r in rows),
        "accepted_precision": measure(tp, tp + fp),
        "accepted_only_recall": measure(tp, tp + fn),
        "end_to_end_positive_recovery": measure(tp, len(positives)),
        "accepted_false_positive_rate": measure(binary_fp, binary_fp + tn),
        "positive_coverage": measure(sum(accepted(r) for r in positives), len(positives)),
        "negative_coverage": measure(sum(accepted(r) for r in negatives), len(negatives)),
        "semantic_abstention": measure(
            outcomes["insufficient_evidence"] + outcomes["conflicting_evidence"], len(rows)
        ),
        "four_state_accuracy": measure(
            sum(tag(r).state == truth(r) for r in valid_labels), len(valid_labels)
        ),
        "four_state_brier_sum_over_classes": measure(brier, len(scored)),
        "game_truth_positive_recovery": measure(
            sum(accepted(r) and tag(r).state == "present" for r in game_positive),
            len(game_positive),
        ),
        "calibration": calibration,
        "confusion_counts": [
            {"truth": a, "prediction": b, "count": n} for (a, b), n in sorted(conf.items())
        ],
    }


def summarize(rows, taxonomy):
    ids = set(taxonomy.genres_by_id)
    overall = {
        "operational": operational_metrics(rows),
        "genre": genre_metrics(rows, ids),
        "tags": {t.id: tag_metrics(rows, t.id) for t in taxonomy.tags},
    }
    overall["slice_counts"] = {}
    for dimension in ("platform", "mode", "family"):
        groups = {}
        for r in rows:
            key = (
                (
                    taxonomy.genres_by_id[r.reference.primary_genre].family
                    if r.reference.origin == "human_review" and r.reference.primary_genre in ids
                    else "unlabelled"
                )
                if dimension == "family"
                else getattr(r, dimension)
            )
            groups.setdefault(key, []).append(r)
        overall["slice_counts"][dimension] = {
            k: {
                "records": len(v),
                "genre": genre_metrics(v, ids),
                "tag_confusion": {
                    t.id: tag_metrics(v, t.id)["confusion_counts"] for t in taxonomy.tags
                },
            }
            for k, v in groups.items()
        }
    # Intentionally no per-genre accuracy from one/zero examples.
    return overall
