"""All identity approvals/labels/media in this module are synthetic test fixtures only."""

import json
from pathlib import Path

import pytest
from test_identity import manifest, quote, text

from gametagger.evaluation.benchmark import (
    Artifact,
    BenchmarkCase,
    BenchmarkManifest,
    ObservationBundle,
    SavedPrediction,
    context_for,
    replay_manifest,
    sha256,
)
from gametagger.evaluation.metrics import CaseMeasurement, Reference, TagMeasurement
from gametagger.taxonomy import default_taxonomy_path


def save(root, name, value):
    data = (
        value.model_dump_json().encode()
        if hasattr(value, "model_dump_json")
        else json.dumps(value).encode()
    )
    (root / name).write_bytes(data)
    return Artifact(path=name, sha256=sha256(data))


def setup_pack(tmp_path, taxonomy):
    e = text("source", "Pieces fall into a rectangular grid.")
    m = manifest([e])
    bundle = ObservationBundle(
        evidence_version=m.evidence_version,
        evidence=[e],
        observations=[quote(e)],
        identity=m,
        observer_model="synthetic",
        observer_prompt_version="exact-quote-fixture",
        observer_input="metadata",
    )
    ref = save(tmp_path, "observations.json", bundle)
    context, _, _ = context_for(bundle, "metadata_only", taxonomy)
    prediction = SavedPrediction(
        case_id="synthetic",
        method="non_jev",
        mode="metadata_only",
        evidence_version=m.evidence_version,
        observation_sha256=ref.sha256,
        context_sha256=sha256(context.encode()),
        taxonomy_sha256=sha256(default_taxonomy_path().read_bytes()),
        model_version="categorical-fixture-v1",
        prompt_version="none",
        code_version="fixture",
        measurement=CaseMeasurement(
            case_id="synthetic",
            method="non_jev",
            mode="metadata_only",
            status="complete",
            primary_genre="puzzle",
            genre_execution="valid",
            genre_action="accept",
            genre_support_verified=True,
            genre_evidence_eligible=True,
            identity_eligible=True,
            tags={"mechanic_parry": TagMeasurement(state="absent", execution="valid")},
        ),
    )
    pred_ref = save(tmp_path, "prediction.json", prediction)
    case = BenchmarkCase(
        id="synthetic",
        split="development",
        canonical_game_id="catalog:subject",
        platform="mobile",
        mobile_first=True,
        observations={"metadata_only": ref},
        results={"non_jev": {"metadata_only": pred_ref}},
        reference=Reference(origin="legacy_reference", primary_genre="puzzle"),
    )
    plan = BenchmarkManifest(
        experiment_id="synthetic",
        taxonomy_sha256=prediction.taxonomy_sha256,
        code_version="fixture",
        methods=["non_jev", "jev_hierarchical"],
        modes=["metadata_only", "media_only", "combined"],
        cases=[case],
    )
    save(tmp_path, "manifest.json", plan)
    return plan, bundle, prediction


def results(tmp_path):
    return [json.loads(line) for line in (tmp_path / "out/cases.jsonl").read_text().splitlines()]


def test_saved_categorical_non_jev_and_all_missing_cells_retained(tmp_path, taxonomy):
    setup_pack(tmp_path, taxonomy)
    report = replay_manifest(tmp_path / "manifest.json", tmp_path / "out")
    assert report["availability"]["paid_calls"] == 0
    assert report["availability"]["pending_result_cells"] == 5
    rows = results(tmp_path)
    assert len(rows) == 6
    r = rows[0]
    assert r["measurement"]["primary_genre"] == "puzzle"
    assert r["measurement"]["genre_probabilities"] is None  # never make up distributions
    assert not r["measurement"]["genre_support_verified"]  # prediction cannot self-certify
    assert r["measurement"]["status"] == "partial"  # missing questions count
    m = report["metrics"]["non_jev"]["metadata_only"]
    assert m["genre"]["emitted_primary_accuracy"]["value"] is None  # legacy != truth
    assert r["end_to_end_latency_ms"] is None
    with pytest.raises(ValueError, match="already exists"):
        replay_manifest(tmp_path / "manifest.json", tmp_path / "out")


@pytest.mark.parametrize("corruption", ["hash", "mode", "context", "taxonomy"])
def test_corrupted_artifact_is_explicit_case_error(tmp_path, taxonomy, corruption):
    plan, _, p = setup_pack(tmp_path, taxonomy)
    if corruption == "hash":
        (tmp_path / "prediction.json").write_text("{}")
    else:
        if corruption == "mode":
            p.mode = "combined"
        if corruption == "context":
            p.context_sha256 = "0" * 64
        if corruption == "taxonomy":
            p.taxonomy_sha256 = "0" * 64
        plan.cases[0].results["non_jev"]["metadata_only"] = save(tmp_path, "prediction.json", p)
        save(tmp_path, "manifest.json", plan)
    replay_manifest(tmp_path / "manifest.json", tmp_path / "out")
    r = results(tmp_path)[0]
    assert r["measurement"]["status"] == "error"
    assert r["errors"][0]["code"] == "artifact_or_contract_error"


def test_invalid_tag_does_not_erase_saved_genre(tmp_path, taxonomy):
    plan, _, p = setup_pack(tmp_path, taxonomy)
    p.measurement.tags["mechanic_parry"].probabilities = {
        "present": 0.0,
        "absent": 0.99,
        "conflicting_evidence": 0.0,
        "insufficient_evidence": 0.0,
    }
    plan.cases[0].results["non_jev"]["metadata_only"] = save(tmp_path, "prediction.json", p)
    save(tmp_path, "manifest.json", plan)
    replay_manifest(tmp_path / "manifest.json", tmp_path / "out")
    r = results(tmp_path)[0]
    assert r["measurement"]["genre_execution"] == "valid"
    assert r["measurement"]["tags"]["mechanic_parry"]["execution"] == "error"
    assert r["errors"][0]["raw"]["probabilities"]["absent"] == 0.99


def test_blind_media_rejects_observations_made_with_metadata(tmp_path, taxonomy):
    _, bundle, _ = setup_pack(tmp_path, taxonomy)
    with pytest.raises(ValueError, match="without metadata"):
        context_for(bundle, "media_only", taxonomy)


@pytest.mark.parametrize("group", ["canonical", "franchise", "asset", "observation"])
def test_duplicate_groups_cannot_cross_holdout(tmp_path, taxonomy, group):
    plan, _, _ = setup_pack(tmp_path, taxonomy)
    first = plan.cases[0]
    second = BenchmarkCase(id="other", split="holdout", platform="pc")
    if group == "canonical":
        second.canonical_game_id = first.canonical_game_id
    if group == "franchise":
        first.franchise_group = second.franchise_group = "shared"
    if group == "asset":
        first.asset_groups = second.asset_groups = ["shared"]
    if group == "observation":
        second.observations = first.observations
    with pytest.raises(ValueError, match="crosses splits"):
        BenchmarkManifest.model_validate({**plan.model_dump(), "cases": [first, second]})


def test_artifact_cannot_escape_manifest_directory(tmp_path):
    a = Artifact(path="../outside.json", sha256="0" * 64)
    with pytest.raises(ValueError, match="inside"):
        a.read(tmp_path)


def test_real_benchmark_readiness_does_not_claim_checked_cases(tmp_path):
    report = replay_manifest(Path("experiments/clean30/manifest.json"), tmp_path / "out")
    assert report["availability"]["actual_cases"] == 0
    assert report["availability"]["human_reviewed_references"] == 0
    assert report["availability"]["target_cases"] == 30


def test_usage_retry_and_latency_preserved_without_inventing_totals(tmp_path, taxonomy):
    from gametagger.evaluation.benchmark import RequestRecord

    plan, _, p = setup_pack(tmp_path, taxonomy)
    p.requests = [
        RequestRecord(
            attempt_id="first",
            component="non_jev",
            model_version="fixture",
            latency_ms=12.0,
            usage=None,
            is_retry=False,
        ),
        RequestRecord(
            attempt_id="retry",
            component="non_jev",
            model_version="fixture",
            latency_ms=8.0,
            usage={"input_tokens": 20, "output_tokens": None},
            is_retry=True,
        ),
    ]
    p.end_to_end_latency_ms = 31.0
    p.latency_scope = "fixture full execution"
    plan.cases[0].results["non_jev"]["metadata_only"] = save(tmp_path, "prediction.json", p)
    save(tmp_path, "manifest.json", plan)
    replay_manifest(tmp_path / "manifest.json", tmp_path / "out")
    r = results(tmp_path)[0]
    assert r["requests"][0]["usage"] is None
    assert r["requests"][1]["is_retry"]
    assert r["end_to_end_latency_ms"] == 31.0
    assert r["usage_status"] == "unknown_or_partial"


def test_evidence_supported_truth_is_mode_specific(tmp_path, taxonomy):
    plan, _, _ = setup_pack(tmp_path, taxonomy)
    plan.cases[0].reference = Reference(
        origin="human_review",
        reviewer="synthetic",
        reviewed_at="2026-09-19",
        primary_genre="puzzle",
        supported_truth={"mechanic_parry": "present"},
    )
    save(tmp_path, "manifest.json", plan)
    replay_manifest(tmp_path / "manifest.json", tmp_path / "out")
    assert results(tmp_path)[0]["measurement"]["reference"]["supported_truth"] == {}


def test_subject_mismatch_is_error_not_a_scored_primary(tmp_path, taxonomy):
    plan, _, _ = setup_pack(tmp_path, taxonomy)
    plan.cases[0].canonical_game_id = "wrong-game"
    save(tmp_path, "manifest.json", plan)
    report = replay_manifest(tmp_path / "manifest.json", tmp_path / "out")
    r = results(tmp_path)[0]
    assert r["measurement"]["status"] == "error"
    assert r["measurement"]["primary_genre"] is None
    assert report["metrics"]["non_jev"]["metadata_only"]["genre"]["primary_coverage"]["value"] == 0
