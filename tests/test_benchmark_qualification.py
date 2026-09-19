"""Synthetic contracts/approvals only; no game labels, real media or provider calls."""

import json
import shutil

import pytest
from PIL import Image
from test_benchmark import save
from test_identity import approved, manifest, quote, text

from gametagger.domain import EvidenceItem, EvidenceType, Observation
from gametagger.evaluation.benchmark import (
    MODES,
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
from gametagger.identity import SubjectIdentity
from gametagger.taxonomy import default_taxonomy_path, load_taxonomy


@pytest.fixture(scope="module")
def complete_pilot(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic-clean30")
    taxonomy = load_taxonomy()
    taxonomy_hash = sha256(default_taxonomy_path().read_bytes())
    methods = ["jev_hierarchical", "non_jev"]
    cases = []
    for i in range(30):
        cid = f"synthetic-{i}"
        name = f"{cid}.png"
        Image.new("RGB", (4, 4), (i, 40, 80)).save(root / name)
        asset = Artifact(path=name, sha256=sha256((root / name).read_bytes()))
        image = EvidenceItem(
            id=f"{cid}:image",
            type=EvidenceType.GAMEPLAY_IMAGE,
            source="synthetic test fixture",
            sha256=asset.sha256,
        )
        doc = text(f"{cid}:text", "A square is shown on a plain background.")
        visual = Observation(
            id=f"{cid}:visible",
            evidence_id=image.id,
            text="A square is shown on a plain background.",
            observer_model="synthetic",
        )
        case = BenchmarkCase(
            id=cid,
            split="development" if i < 6 else "holdout",
            canonical_game_id=f"synthetic:{i}",
            platform="mobile" if i < 10 else "pc",
            mobile_first=i < 10,
        )
        for mode in MODES:
            evidence = (
                [doc]
                if mode == "metadata_only"
                else [image]
                if mode == "media_only"
                else [doc, image]
            )
            observations = (
                [quote(doc)]
                if mode == "metadata_only"
                else [visual]
                if mode == "media_only"
                else [quote(doc), visual]
            )
            identity = manifest(
                evidence,
                subject=SubjectIdentity(canonical_game_id=case.canonical_game_id),
                raw_record_id=cid,
            )
            bundle = ObservationBundle(
                evidence_version="v1",
                evidence=evidence,
                observations=observations,
                identity=identity,
                observer_model="synthetic",
                observer_prompt_version="fixture-v1",
                observer_input="media_blind"
                if mode == "media_only"
                else "metadata"
                if mode == "metadata_only"
                else "combined",
                media_rights="permitted",
                assets={image.id: asset} if mode != "metadata_only" else {},
            )
            ref = save(root, f"{cid}-{mode}.json", bundle)
            case.observations[mode] = ref
            case.references_by_mode[mode] = Reference(
                origin="human_review",
                reviewer="SYNTHETIC TEST ONLY",
                reviewed_at="2026-09-19",
                primary_genre="puzzle",
                game_truth={t.id: False for t in taxonomy.tags},
                supported_truth={t.id: "insufficient_evidence" for t in taxonomy.tags},
            )
            context, _, _ = context_for(bundle, mode, taxonomy)
            for method in methods:
                prediction = SavedPrediction(
                    case_id=cid,
                    method=method,
                    mode=mode,
                    evidence_version="v1",
                    observation_sha256=ref.sha256,
                    context_sha256=sha256(context.encode()),
                    taxonomy_sha256=taxonomy_hash,
                    model_version="synthetic",
                    prompt_version="synthetic",
                    code_version="synthetic",
                    measurement=CaseMeasurement(
                        case_id=cid,
                        method=method,
                        mode=mode,
                        status="complete",
                        genre_execution="valid",
                        primary_genre="puzzle",
                        tags={
                            t.id: TagMeasurement(execution="valid", state="insufficient_evidence")
                            for t in taxonomy.tags
                        },
                    ),
                )
                case.results.setdefault(method, {})[mode] = save(
                    root, f"{cid}-{mode}-{method}.json", prediction
                )
        cases.append(case)
    save(
        root,
        "manifest.json",
        BenchmarkManifest(
            experiment_id="synthetic-qualification",
            taxonomy_sha256=taxonomy_hash,
            code_version="synthetic",
            methods=methods,
            modes=list(MODES),
            cases=cases,
        ),
    )
    return root


@pytest.fixture
def pilot(complete_pilot, tmp_path):
    shutil.copytree(complete_pilot, tmp_path, dirs_exist_ok=True)
    return BenchmarkManifest.model_validate_json((tmp_path / "manifest.json").read_bytes())


def replay(tmp_path, pilot):
    save(tmp_path, "manifest.json", pilot)
    return replay_manifest(tmp_path / "manifest.json", tmp_path / "output")


def codes(report):
    assert report["benchmark_qualified"] == report["availability"]["benchmark_qualified"]
    return {f["code"] for f in report["qualification_failure_reasons"]}


def test_complete_mode_specific_human_references_qualify(tmp_path, pilot):
    assert all(c.reference.origin == "unavailable" for c in pilot.cases)
    report = replay(tmp_path, pilot)
    a = report["availability"]
    assert report["benchmark_qualified"] is True
    assert not codes(report)
    assert a["human_reviewed_references"] == 30
    assert a["cases_with_human_review_all_modes"] == 30
    assert a["human_reviewed_references_by_mode"] == dict.fromkeys(MODES, 30)
    assert a["human_reviewed_reference_cells"] == 90  # Not 180 method×mode cells.
    assert a["recorded_prediction_cells"] == a["required_prediction_cells"] == 180
    assert a["paid_calls"] == 0


@pytest.mark.parametrize(
    "change,expected",
    [
        ("29_cases", "target_cohort_size"),
        ("nine_mobile", "minimum_mobile_first"),
        ("wrong_split", "development_holdout_split"),
        ("missing_reference", "human_references_incomplete"),
        ("missing_observation", "observation_bundles_unavailable"),
        ("missing_prediction", "prediction_cells_unavailable"),
        ("lowered_plan", "qualification_plan_mismatch"),
        ("missing_mode", "required_evidence_modes"),
    ],
)
def test_partial_readiness_is_not_qualification(tmp_path, pilot, change, expected):
    if change == "29_cases":
        pilot.cases.pop()
    elif change == "nine_mobile":
        pilot.cases[9].mobile_first = False
    elif change == "wrong_split":
        pilot.cases[5].split = "holdout"
    elif change == "missing_reference":
        pilot.cases[0].references_by_mode.pop("media_only")
    elif change == "missing_observation":
        pilot.cases[0].observations.pop("combined")
    elif change == "missing_prediction":
        pilot.cases[0].results["non_jev"].pop("combined")
    elif change == "lowered_plan":
        pilot.target_cases = 29
    else:
        pilot.modes.remove("combined")
        for case in pilot.cases:
            case.observations.pop("combined")
            case.references_by_mode.pop("combined")
            for result in case.results.values():
                result.pop("combined")
    report = replay(tmp_path, pilot)
    assert not report["benchmark_qualified"]
    assert expected in codes(report)
    assert report["availability"]["ready_prediction_cells"] > 0
    if change == "missing_prediction":
        assert report["availability"]["recorded_prediction_cells"] == 179
        failure = next(f for f in report["qualification_failure_reasons"] if f["code"] == expected)
        assert failure["missing"] == [
            {"case_id": "synthetic-0", "method": "non_jev", "mode": "combined"}
        ]
    if change == "missing_reference":
        assert report["availability"]["human_reviewed_references_by_mode"]["media_only"] == 29
        assert report["availability"]["human_reviewed_references"] == 30
        assert report["availability"]["cases_with_human_review_all_modes"] == 29


@pytest.mark.parametrize(
    "change,expected",
    [
        ("rights", "media_rights_not_permitted"),
        ("asset", "permitted_media_assets_unavailable"),
        ("missing_bytes", "permitted_media_assets_unavailable"),
        ("identity", "identity_not_approved"),
        ("empty_observations", "mode_evidence_unavailable"),
    ],
)
def test_required_source_gates_fail_independently(tmp_path, pilot, change, expected):
    case = pilot.cases[0]
    artifact = case.observations["media_only"]
    bundle = ObservationBundle.model_validate_json(artifact.read(tmp_path))
    if change == "rights":
        bundle.media_rights = "pending"
    elif change == "asset":
        bundle.assets = {}
    elif change == "missing_bytes":
        (tmp_path / next(iter(bundle.assets.values())).path).unlink()
    elif change == "identity":
        bundle.identity = bundle.identity.model_copy(
            update={"record_decision": approved(origin="automated_suggestion")}
        )
    else:
        bundle.observations = []
    case.observations["media_only"] = save(tmp_path, artifact.path, bundle)
    report = replay(tmp_path, pilot)
    assert not report["benchmark_qualified"]
    assert expected in codes(report)
    assert report["availability"]["ready_prediction_cells"] > 0
    if change in {"asset", "missing_bytes"}:
        assert report["availability"]["readiness_counts"]["identity_approved"]["ready"] == 90


def test_reviewed_empty_truth_and_cross_mode_fallback_do_not_qualify(tmp_path, pilot):
    case = pilot.cases[0]
    case.reference = case.references_by_mode.pop("media_only")
    case.references_by_mode["combined"].supported_truth = {}
    report = replay(tmp_path, pilot)
    assert report["availability"]["human_reviewed_references"] == 30
    assert report["availability"]["complete_human_references_by_mode"]["media_only"] == 29
    assert not report["benchmark_qualified"]
    assert "human_references_incomplete" in codes(report)


def test_one_mode_review_stays_visible_without_qualifying_other_modes(tmp_path, pilot):
    pilot.cases = pilot.cases[:1]
    pilot.cases[0].references_by_mode = {
        "media_only": pilot.cases[0].references_by_mode["media_only"]
    }
    report = replay(tmp_path, pilot)
    a = report["availability"]
    assert a["human_reviewed_references"] == 1
    assert a["human_reviewed_reference_cells"] == 1
    assert a["human_reviewed_references_by_mode"] == {
        "metadata_only": 0,
        "media_only": 1,
        "combined": 0,
    }
    assert a["cases_with_human_review_all_modes"] == 0
    assert "human_references_incomplete" in codes(report)
    assert not report["benchmark_qualified"]


def test_explicit_reviewed_primary_boundary_remains_unresolved(tmp_path, pilot):
    ref = pilot.cases[0].references_by_mode["media_only"]
    ref.primary_genre = None
    ref.boundary_note = "Synthetic reviewed boundary; no agreed primary."
    report = replay(tmp_path, pilot)
    assert report["benchmark_qualified"] is True
    assert report["metrics"]["non_jev"]["media_only"]["genre"]["human_label_count"] == 29


@pytest.mark.parametrize("change", ["pending", "hash"])
def test_unattempted_or_corrupt_prediction_is_not_a_recorded_cell(tmp_path, pilot, change):
    ref = pilot.cases[0].results["jev_hierarchical"]["combined"]
    prediction = SavedPrediction.model_validate_json(ref.read(tmp_path))
    if change == "hash":
        (tmp_path / ref.path).write_text("{}")
    else:
        prediction.measurement.status = "pending"
        pilot.cases[0].results["jev_hierarchical"]["combined"] = save(
            tmp_path, ref.path, prediction
        )
    report = replay(tmp_path, pilot)
    assert not report["benchmark_qualified"]
    assert "prediction_cells_unavailable" in codes(report)
    assert report["availability"]["recorded_prediction_cells"] == 179
    assert report["availability"]["readiness_counts"]["identity_approved"]["ready"] == 90


def test_failed_provider_attempt_counts_without_becoming_success(tmp_path, pilot):
    ref = pilot.cases[0].results["jev_hierarchical"]["combined"]
    prediction = SavedPrediction.model_validate_json(ref.read(tmp_path))
    prediction.measurement.status = "error"
    prediction.measurement.primary_genre = None
    prediction.measurement.genre_execution = "error"
    prediction.measurement.tags = {}
    prediction.errors = [{"code": "synthetic_provider_failure"}]
    pilot.cases[0].results["jev_hierarchical"]["combined"] = save(tmp_path, ref.path, prediction)
    report = replay(tmp_path, pilot)
    assert report["benchmark_qualified"] is True
    assert report["availability"]["recorded_prediction_cells"] == 180
    assert report["availability"]["error_result_cells"] == 1
    assert report["availability"]["ready_prediction_cells"] == 179
    rows = [json.loads(line) for line in (tmp_path / "output/cases.jsonl").read_text().splitlines()]
    assert len(rows) == 180
    assert rows[4]["measurement"]["primary_genre"] is None
