import pytest

from gametagger.evaluation.metrics import (
    CaseMeasurement,
    Reference,
    TagMeasurement,
    genre_metrics,
    operational_metrics,
    tag_metrics,
)


def row(**changes):
    data = dict(
        case_id="synthetic",
        method="fixture",
        mode="metadata_only",
        status="complete",
        identity_eligible=True,
    )
    data.update(changes)
    return CaseMeasurement(**data)


def truth(state="present", **changes):
    return Reference(
        origin="human_review",
        reviewer="synthetic-test-only",
        reviewed_at="2026-09-19",
        supported_truth={"test": state},
        **changes,
    )


def tag(state="present", **changes):
    data = dict(
        state=state,
        execution="valid",
        action="accept",
        evidence_eligible=True,
        support_verified=True,
    )
    data.update(changes)
    return TagMeasurement(**data)


def test_recall_counts_abstentions_errors_and_missing_predictions():
    rows = [
        row(reference=truth(), tags={"test": tag()}),
        row(reference=truth(), tags={"test": tag("insufficient_evidence")}),
        row(reference=truth(), tags={"test": TagMeasurement(execution="error")}),
        row(reference=truth()),
    ]
    m = tag_metrics(rows, "test")
    assert m["accepted_only_recall"]["value"] == 1
    assert m["end_to_end_positive_recovery"] == dict(numerator=1, denominator=4, value=0.25)
    assert m["errors"] == 1 and m["not_evaluated"] == 1
    assert sum(m["new_outcomes"].values()) == 2


def test_null_genre_is_never_a_correct_emitted_primary():
    r = row(
        reference=truth(primary_genre="a"),
        genre_execution="valid",
        genre_probabilities={"a": 0.4, "b": 0.0, "insufficient_evidence": 0.6},
    )
    m = genre_metrics([r], {"a", "b"})
    assert m["forced_choice_candidate_accuracy_diagnostic"]["value"] == 1
    assert m["emitted_primary_accuracy"]["value"] is None
    assert m["primary_coverage"]["value"] == 0
    assert m["end_to_end_correct_primary"]["value"] == 0


def test_accept_action_does_not_imply_publication():
    r = row(
        reference=truth(primary_genre="a"),
        primary_genre="a",
        genre_execution="valid",
        genre_action="accept",
        genre_evidence_eligible=True,
    )
    assert genre_metrics([r], {"a"})["publication_coverage"]["value"] == 0
    r.genre_support_verified = True
    assert genre_metrics([r], {"a"})["publishable_precision"]["value"] == 1
    r.identity_eligible = False
    assert genre_metrics([r], {"a"})["publication_coverage"]["value"] == 0


def test_brier_requires_human_evidence_supported_truth_and_valid_distribution():
    p = {"present": 0.7, "absent": 0.1, "insufficient_evidence": 0.1, "conflicting_evidence": 0.1}
    good = row(reference=truth(), tags={"test": tag(probabilities=p)})
    bad = row(reference=truth(), tags={"test": tag(probabilities={**p, "present": 0.69})})
    ai = row(
        reference=Reference(origin="ai_suggestion", supported_truth={"test": "present"}),
        tags={"test": tag(probabilities=p)},
    )
    m = tag_metrics([good, bad, ai], "test")
    assert m["four_state_brier_sum_over_classes"]["denominator"] == 1
    assert m["four_state_brier_sum_over_classes"]["value"] == pytest.approx(0.12)
    assert m["errors"] == 1
    assert sum(b["count"] for b in m["calibration"]) == 1


def test_missing_legacy_keys_unknown_and_undefined_not_zero():
    m = tag_metrics([row(reference=Reference(origin="legacy_reference", game_truth={}))], "test")
    assert m["accepted_precision"]["value"] is None
    assert m["game_truth_positive_recovery"]["denominator"] == 0
    assert genre_metrics([], {"a"})["primary_coverage"]["value"] is None
    assert operational_metrics([])["completion"]["value"] is None


def test_game_truth_is_distinct_from_supported_truth():
    r = row(
        reference=truth("insufficient_evidence", game_truth={"test": True}),
        tags={"test": tag("insufficient_evidence")},
    )
    m = tag_metrics([r], "test")
    assert m["four_state_accuracy"]["value"] == 1
    assert m["end_to_end_positive_recovery"]["value"] is None
    assert m["game_truth_positive_recovery"]["value"] == 0


def test_selected_option_must_match_valid_probabilities():
    r = row(
        reference=truth(),
        tags={
            "test": tag(
                probabilities={
                    "present": 0.1,
                    "absent": 0.9,
                    "insufficient_evidence": 0.0,
                    "conflicting_evidence": 0.0,
                }
            )
        },
    )
    assert tag_metrics([r], "test")["four_state_brier_sum_over_classes"]["denominator"] == 0


def test_operational_denominators_do_not_hide_errors():
    m = operational_metrics(
        [
            row(first_attempt_success=True, evidence_available=True),
            row(
                status="error",
                first_attempt_success=False,
                retried=True,
                retry_recovered=False,
                evidence_available=False,
            ),
            row(status="partial"),
        ]
    )
    assert m["completion"]["denominator"] == 3
    assert m["first_attempt_success"]["denominator"] == 2
    assert m["terminal_errors"]["numerator"] == 1
    assert m["partial_results"]["numerator"] == 1
    assert m["evidence_availability_unknown"] == 1


def test_unsupported_accepted_positive_counts_against_precision():
    r = row(reference=truth("insufficient_evidence"), tags={"test": tag("present")})
    m = tag_metrics([r], "test")
    assert m["accepted_precision"] == dict(numerator=0, denominator=1, value=0)
    assert m["accepted_false_positive_rate"]["value"] is None


def test_preserved_audit_totals_and_taxonomy_hash():
    import hashlib
    import json
    from pathlib import Path

    from gametagger.taxonomy import default_taxonomy_path

    audit = json.loads(Path("experiments/legacy100/pr_b_audit.json").read_text())
    assert (
        audit["taxonomy_sha256"] == hashlib.sha256(default_taxonomy_path().read_bytes()).hexdigest()
    )
    assert len(audit["per_tag"]) == 25
    assert sum(sum(t["new_outcomes"].values()) for t in audit["per_tag"].values()) == 2425
    assert sum(t["comparable_legacy_booleans_completed"] for t in audit["per_tag"].values()) == 498
    assert sum(t["execution_errors"] for t in audit["per_tag"].values()) == 75
    assert len(audit["text_bearing_abstentions"]) == 8
    assert audit["genre_measurement"]["emitted_primary_accuracy"]["value"] is None
    assert audit["operational"]["completion"]["denominator"] == 100


def test_ninety_percent_unknown_and_ten_percent_correct_candidate_is_not_accuracy():
    r = row(
        reference=truth(primary_genre="a"),
        identity_eligible=True,
        genre_execution="valid",
        genre_probabilities={"a": 0.1, "insufficient_evidence": 0.9},
    )
    m = genre_metrics([r], {"a"})
    assert m["forced_choice_candidate_accuracy_diagnostic"]["value"] == 1
    assert m["actual_primary_correctness"]["value"] == 0
    r.identity_eligible = False
    m = genre_metrics([r], {"a"})
    assert m["actual_primary_correctness"]["value"] is None
    assert m["identity_excluded_human_labels"] == 1


def test_one_accepted_and_99_deferred_positive_cases():
    rows = [row(reference=truth(), tags={"test": tag()})]
    rows += [row(reference=truth(), tags={"test": TagMeasurement()}) for _ in range(99)]
    m = tag_metrics(rows, "test")
    assert m["accepted_precision"]["value"] == 1
    assert m["end_to_end_positive_recovery"]["value"] == 0.01


def test_unapproved_identity_kept_operational_but_excluded_from_tag_quality():
    r = row(identity_eligible=False, reference=truth(), tags={"test": tag()})
    m = tag_metrics([r], "test")
    assert m["records"] == 1 and m["new_outcomes"]["present"] == 1
    assert m["accepted_precision"]["value"] is None
    assert m["end_to_end_positive_recovery"]["value"] is None
