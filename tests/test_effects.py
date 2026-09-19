import pytest

from gametagger.workspace.experiments import MethodRecord, compare


def record(**changes):
    d = dict(
        method_id="a",
        version="fixture",
        cohort="checked-fixture",
        case_ids=["g"],
        evidence_hashes={"g": "hash"},
        observation_hashes={"g": "observations"},
        taxonomy_hash="taxonomy",
        label_origin="human_review",
        label_version="synthetic-test-reference-v1",
        conditions={"cache": "cold", "concurrency": "1"},
        kind="replayed",
        correct={"g": True},
    )
    d.update(changes)
    return MethodRecord(**d)


@pytest.mark.parametrize(
    "changes",
    [
        {"cohort": "other"},
        {"evidence_hashes": {"g": "wrong"}},
        {"taxonomy_hash": "different"},
        {"conditions": {"cache": "warm"}},
        {"observation_hashes": {}},
        {"label_origin": "legacy_machine"},
        {"kind": "illustrative"},
        {"case_ids": []},
        {"correct": {}},
    ],
)
def test_no_effect_with_incompatible_cohorts(changes):
    e = compare(record(), record(**changes))
    assert e.value is None and e.status == "unavailable" and e.denominator == 0


def test_paired_effect_is_game_level_not_25_tag_samples():
    e = compare(record(correct={"g": False}), record())
    assert e.value == 100 and e.denominator == 1 and e.observation_unit == "game"


def test_experimental_direct_spec_preserves_exact_vocabulary(taxonomy):
    from gametagger.evaluation.comparators import direct_genre_spec

    spec = direct_genre_spec(taxonomy)
    assert set(spec.criteria) == set(taxonomy.genres_by_id) | {"insufficient_evidence"}
    assert len(spec.criteria) == 101
    assert "Elden Ring" not in str(spec.criteria)


def test_report_recomputes_and_requires_complete_cost_and_paired_conditions():
    from gametagger.workspace.experiments import ComparisonReport

    a = record(accepted_primary={"g": False}, complete_cost_usd={"g": 0.01})
    b = record(accepted_primary={"g": True}, complete_cost_usd={"g": 0.02})
    report = ComparisonReport(
        report_id="test-only", kind="replayed", baseline=a, candidate=b, input_hashes={}
    )
    scores = {r["metric"]: r for r in report.view()["scorecard"]}
    assert scores["Actual primary correctness"]["paired_n"] == 1
    assert scores["Useful coverage"]["change"] == 100
    assert scores["Cost per useful result"]["change"] is None
    assert scores["p95 total latency"]["change"] is None
    b.conditions = {"concurrency": "different"}
    assert all(r["change"] is None for r in report.view()["scorecard"])


def test_saved_report_api_only_exposes_validated_records(client=None):
    # Fixture labels are synthetic contract tests, not real adjudicated annotations.
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from fastapi.testclient import TestClient

    from gametagger.workspace.app import create_app
    from gametagger.workspace.experiments import ComparisonReport

    with TemporaryDirectory() as directory:
        root = Path(directory)
        reports = root / "reports"
        reports.mkdir()
        report = ComparisonReport(
            report_id="test-only",
            kind="replayed",
            baseline=record(),
            candidate=record(),
            input_hashes={},
        )
        (reports / "test.json").write_text(report.model_dump_json())
        (reports / "bad.json").write_text('{"api_key":"must-not-leak"}')
        with TestClient(create_app(root=root, local_dev=True, role="reviewer")) as c:
            output = c.get("/api/experiments").json()
            assert len(output["reports"]) == 1
            assert len(output["report_errors"]) == 1
            assert "must-not-leak" not in str(output)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1])
def test_invalid_timing_or_cost_never_enters_report(bad):
    with pytest.raises(ValueError):
        record(total_latency_ms={"g": bad})
    with pytest.raises(ValueError):
        record(complete_cost_usd={"g": bad})
