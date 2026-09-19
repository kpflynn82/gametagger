"""Synthetic mathematical regression cases; never genuine reviewed game labels."""

from copy import deepcopy

import pytest

from gametagger.evaluation.metrics import CaseMeasurement, Reference, TagMeasurement
from gametagger.workspace.experiments import ComparisonReport, MethodRecord

TAG = "mechanic_parry"


def case(i, *, accepted=False, state="insufficient_evidence", execution="valid", eligible=True):
    states = ("present", "absent", "insufficient_evidence", "conflicting_evidence")
    return CaseMeasurement(
        case_id=str(i),
        method="method",
        mode="media_only",
        platform="pc",
        status="partial",
        identity_eligible=eligible,
        genre_execution="not_evaluated",
        reference=Reference(
            origin="human_review",
            reviewer="synthetic-test-reference",
            reviewed_at="2026-09-19T00:00:00Z",
            primary_genre="puzzle",
            supported_truth={TAG: "present"},
            game_truth={TAG: True},
        ),
        tags={
            TAG: TagMeasurement(
                state=state if execution == "valid" else None,
                execution=execution,
                action="accept" if accepted else "acquire_evidence",
                evidence_eligible=True,
                support_verified=accepted,
                probabilities={s: float(s == state) for s in states}
                if execution == "valid"
                else None,
            )
        },
    )


def method(rows):
    return MethodRecord(
        method_id="method",
        version="fixture-only-v1",
        cohort="synthetic-regression",
        case_ids=[r.case_id for r in rows],
        evidence_hashes={r.case_id: "e" * 64 for r in rows},
        observation_hashes={r.case_id: "d" * 64 for r in rows},
        taxonomy_hash="f" * 64,
        label_origin="human_review",
        label_version="synthetic-only",
        conditions={"mode": "media_only"},
        kind="replayed",
        case_measurements=rows,
        correct={r.case_id: True for r in rows},
        accepted_primary={r.case_id: True for r in rows},
    )


def report(a, b):
    return ComparisonReport(
        report_id="synthetic-regression",
        kind="replayed",
        baseline=method(a),
        candidate=method(b),
        input_hashes={},
    )


def scores(view):
    return {m["metric"]: m for m in view["scorecard"]}


def test_one_accepted_and_99_deferred_positive_claims_is_one_percent_recall():
    a = [case(i) for i in range(100)]
    b = deepcopy(a)
    b[0] = case(0, accepted=True, state="present")
    view = report(a, b).view()
    s = scores(view)
    # No accepted baseline claim: undefined precision, not 0% or 100% uplift.
    assert s["Accepted attribute precision"]["change"] is None
    assert s["Accepted attribute precision"]["candidate"] == 100
    assert s["Accepted attribute precision"]["baseline"] is None
    assert s["End-to-end recall"]["baseline"] == 0
    assert s["End-to-end recall"]["candidate"] == 1
    assert s["End-to-end recall"]["candidate_denominator"] == 100
    assert s["End-to-end recall"]["paired_n"] == 100  # games, not 2,500 tags
    # Summary booleans must not override actual emitted results when case ledger exists.
    assert s["Actual primary correctness"]["candidate"] == 0
    assert s["Useful coverage"]["candidate"] == 0
    from gametagger.workspace.experiments import compare

    direct = compare(method(a), method(b))
    assert direct.value == 0 and direct.denominator == 100
    tag = next(t for t in view["quality"]["tags"] if t["id"] == TAG)
    assert tag["candidate"]["accepted_precision"]["value"] == 1
    assert tag["candidate"]["accepted_only_recall"]["value"] == 1
    assert tag["candidate"]["end_to_end_positive_recovery"]["value"] == 0.01
    assert tag["baseline"]["new_outcomes"]["insufficient_evidence"] == 100
    assert "case_measurements" not in view["methods"][0]  # no raw private reference payload


def test_invalid_distribution_is_error_and_never_enters_probability_score():
    a = [
        case(0, state="present", accepted=True),
        case(1, execution="error"),
        case(2, eligible=False),
    ]
    a[0].tags[TAG].probabilities["present"] = 0.99
    view = report(a, deepcopy(a)).view()
    tag = next(t for t in view["quality"]["tags"] if t["id"] == TAG)["baseline"]
    assert tag["errors"] == 2
    assert scores(view)["Execution error rate"]["baseline"] == pytest.approx(200 / 3)
    assert tag["four_state_brier_sum_over_classes"]["denominator"] == 0
    assert tag["end_to_end_positive_recovery"]["denominator"] == 2
    assert view["quality"]["identity_excluded_games"] == 1
    assert a[0].tags[TAG].probabilities["present"] == 0.99


def test_missing_labels_remain_unknown_and_empty_denominators_remain_null():
    a = [case(0)]
    a[0].reference = Reference()
    q = report(a, deepcopy(a)).view()["quality"]
    assert q["pending_reference_games"] == 1
    for tag in q["tags"]:
        assert tag["baseline"]["accepted_precision"]["value"] is None
        assert tag["baseline"]["four_state_brier_sum_over_classes"]["value"] is None
    assert q["headline"]["Actual primary correctness"][0]["denominator"] == 0


@pytest.mark.parametrize(
    "change", ["label", "identity", "platform", "mode", "missing", "observations", "illustrative"]
)
def test_incompatible_tag_pairs_never_compute_effect(change):
    r = report([case(0)], [case(0)])
    b = r.candidate
    if change == "label":
        b.case_measurements[0].reference.supported_truth[TAG] = "absent"
    elif change == "identity":
        b.case_measurements[0].identity_eligible = False
    elif change == "platform":
        b.case_measurements[0].platform = "mobile"
    elif change == "mode":
        b.case_measurements[0].mode = "combined"
    elif change == "missing":
        b.case_measurements = []
    elif change == "observations":
        b.observation_hashes = {"0": "different"}
    else:
        b.kind = "illustrative"
    view = r.view()
    assert not view["quality"]["available"]
    assert scores(view)["Accepted attribute precision"]["change"] is None
    assert scores(view)["Actual primary correctness"]["change"] is None


def test_brier_targets_four_states_not_gamewide_binary_feature():
    a = [case(0, state="present", accepted=True)]
    a[0].reference.supported_truth[TAG] = "absent"
    a[0].reference.game_truth[TAG] = True  # Different target, deliberately.
    p = {"present": 0.7, "absent": 0.1, "insufficient_evidence": 0.1, "conflicting_evidence": 0.1}
    a[0].tags[TAG].probabilities = p
    q = report(a, deepcopy(a)).view()["quality"]
    t = next(t for t in q["tags"] if t["id"] == TAG)["baseline"]
    assert t["four_state_brier_sum_over_classes"]["value"] == pytest.approx(1.32)
    assert t["accepted_precision"]["value"] == 0
    assert t["game_truth_positive_recovery"]["value"] == 1
    bucket = next(b for b in t["calibration"] if b["count"])
    assert bucket["count"] == 1
    assert bucket["mean_selected_probability"]["value"] == 0.7
    assert bucket["empirical_correctness"]["value"] == 0


def test_v2_requires_case_method_and_fixed_tag_ids():
    r = case(0)
    r.method = "different"
    with pytest.raises(ValueError, match="method"):
        method([r])
    r = case(0)
    r.tags["invented_new_genre"] = TagMeasurement()
    with pytest.raises(ValueError, match="frozen taxonomy"):
        method([r])
    with pytest.raises(ValueError, match="v2"):
        ComparisonReport(
            schema_version="paired-report-v1",
            report_id="x",
            kind="replayed",
            baseline=method([case(0)]),
            candidate=method([case(0)]),
            input_hashes={},
        )


def test_jev_increment_requires_declared_roles_and_identical_criteria():
    r = report([case(0)], [case(0)])
    r.comparison_question = "classifier_increment"
    assert not r.view()["quality"]["available"]
    r.baseline.method_family = "conventional"
    r.candidate.method_family = "jev_hierarchical"
    r.baseline.criteria_hash = r.candidate.criteria_hash = "c" * 64
    assert r.view()["quality"]["available"]
    r.candidate.criteria_hash = "changed"
    assert all(s["change"] is None for s in r.view()["scorecard"])


def test_operational_coverage_without_labels_does_not_become_accuracy():
    r = report([case(0)], [case(0)])
    for method_record in (r.baseline, r.candidate):
        method_record.case_measurements[0].reference = Reference()
        method_record.label_origin = method_record.label_version = "unavailable"
    s = scores(r.view())
    assert s["Actual primary correctness"]["baseline"] is None
    assert s["Accepted attribute precision"]["baseline"] is None
    assert s["Partial-output rate"]["baseline"] == 100
    assert s["Useful coverage"]["baseline"] == 0


def test_cost_per_useful_result_cannot_use_conflicting_summary_approval_flags():
    r = report([case(0)], [case(0)])
    for m in (r.baseline, r.candidate):
        m.accounting_complete = True
        m.complete_cost_usd = {"0": 0.01}
        m.accepted_primary = {"0": True}  # Contradicts detailed null-primary result.
    s = scores(r.view())
    assert s["Cost per useful result"]["baseline"] is None
    assert s["Cost per useful result"]["change"] is None
