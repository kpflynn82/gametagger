"""Offline saved-result benchmark. This module never instantiates a model client."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gametagger.decisions.jev import JevQuestionCompiler
from gametagger.domain import EvidenceItem, Observation
from gametagger.evaluation.metrics import (
    STATES,
    CaseMeasurement,
    Reference,
    summarize,
    valid_distribution,
)
from gametagger.evidence_policy import (
    ClaimAttribution,
    EvidenceProfile,
    evidence_eligibility,
    support_links,
)
from gametagger.identity import IdentityManifest, validate_identity
from gametagger.observers.boundary import ObservationBoundary
from gametagger.taxonomy import default_taxonomy_path, load_taxonomy

MODES = ("metadata_only", "media_only", "combined")
QUALIFICATION_POLICY = "clean30-qualification-v1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Artifact(Contract):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def read(self, root: Path) -> bytes:
        target = (root / self.path).resolve()
        if Path(self.path).is_absolute() or not target.is_relative_to(root.resolve()):
            raise ValueError("Artifact must remain inside the manifest directory")
        data = target.read_bytes()
        if sha256(data) != self.sha256:
            raise ValueError("Artifact hash mismatch")
        return data


class RequestRecord(Contract):
    attempt_id: str
    component: Literal["observer", "jev", "non_jev"]
    model_version: str
    latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    usage: dict[str, int | None] | None = None
    error: dict | None = None
    evidence_sha256: str | None = None
    is_retry: bool | None = None


class ObservationBundle(Contract):
    schema_version: Literal["observation-bundle-v1"] = "observation-bundle-v1"
    evidence_version: str
    evidence: list[EvidenceItem]
    observations: list[Observation]
    identity: IdentityManifest
    profiles: list[EvidenceProfile] = Field(default_factory=list)
    claims: list[ClaimAttribution] = Field(default_factory=list)
    observer_model: str
    observer_prompt_version: str
    # The pack declares whether metadata was hidden BEFORE observation.
    observer_input: Literal["media_blind", "metadata", "combined"]
    residual_visible_identity_cues: list[str] = Field(default_factory=list)
    media_rights: Literal["permitted", "pending", "unavailable"] = "pending"
    # Actual assets stay private and must be available/hash-verified for media readiness.
    assets: dict[str, Artifact] = Field(default_factory=dict)
    observer_requests: list[RequestRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent(self):
        if self.evidence_version != self.identity.evidence_version:
            raise ValueError("Observation and identity evidence versions differ")
        for values in (self.evidence, self.observations):
            if len({v.id for v in values}) != len(values):
                raise ValueError("Duplicate evidence/observation IDs")
        if any(o.evidence_id not in {e.id for e in self.evidence} for o in self.observations):
            raise ValueError("Unbound observation")
        return self


class SavedPrediction(Contract):
    schema_version: Literal["saved-prediction-v1"] = "saved-prediction-v1"
    case_id: str
    method: str
    mode: Literal["metadata_only", "media_only", "combined"]
    evidence_version: str
    observation_sha256: str
    context_sha256: str
    taxonomy_sha256: str
    model_version: str
    prompt_version: str
    code_version: str
    measurement: CaseMeasurement
    # Raw or partial model answers remain in a separate hash-bound private artifact.
    raw_response: Artifact | None = None
    requests: list[RequestRecord] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    end_to_end_latency_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    latency_scope: str = "unknown"


class BenchmarkCase(Contract):
    id: str
    split: Literal["development", "holdout"]
    canonical_game_id: str | None = None
    franchise_group: str | None = None
    asset_groups: list[str] = Field(default_factory=list)
    platform: Literal["pc", "console", "mobile", "unknown"]
    mobile_first: bool | None = None
    # One frozen observation artifact per mode; every method must reuse that same artifact.
    observations: dict[str, Artifact] = Field(default_factory=dict)
    results: dict[str, dict[str, Artifact]] = Field(default_factory=dict)
    reference: Reference = Field(default_factory=Reference)
    references_by_mode: dict[str, Reference] = Field(default_factory=dict)
    pending_reasons: list[str] = Field(default_factory=list)


class BenchmarkManifest(Contract):
    schema_version: Literal["benchmark-v1"] = "benchmark-v1"
    experiment_id: str
    taxonomy_sha256: str
    code_version: str
    methods: list[str] = Field(min_length=1)
    modes: list[Literal["metadata_only", "media_only", "combined"]] = Field(min_length=1)
    target_cases: int = Field(default=30, ge=0)
    minimum_mobile_first: int = Field(default=10, ge=0)
    planned_development_cases: int = Field(default=6, ge=0)
    cases: list[BenchmarkCase] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_and_no_leakage(self):
        for values in ([c.id for c in self.cases], self.methods, self.modes):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate case, method, or mode")
        groups = {}
        for case in self.cases:
            if set(case.references_by_mode) - set(self.modes):
                raise ValueError("Undeclared reference mode")
            if set(case.observations) - set(self.modes) or set(case.results) - set(self.methods):
                raise ValueError("Undeclared mode/method")
            if any(set(v) - set(self.modes) for v in case.results.values()):
                raise ValueError("Undeclared result mode")
            keys = [("canonical", case.canonical_game_id), ("franchise", case.franchise_group)]
            keys += [("asset", k) for k in case.asset_groups]
            keys += [("observation", v.sha256) for v in case.observations.values()]
            for kind, key in keys:
                if key is None:
                    continue
                group = (kind, key)
                if group in groups and groups[group] != case.split:
                    raise ValueError("Canonical/franchise/asset/observation group crosses splits")
                groups[group] = case.split
        return self


def reference_for(case, mode):
    # Game-wide truth may be shared; evidence-supported truth never crosses modes.
    return case.references_by_mode.get(
        mode, case.reference.model_copy(update={"supported_truth": {}})
    )


def benchmark_readiness(manifest, reports, taxonomy):
    """Qualification is a conjunction, never a synonym for partial readiness or accuracy."""
    failures = []

    def require(code, actual, expected, *, missing=None):
        if actual != expected:
            failure = {"code": code, "actual": actual, "expected": expected}
            if missing is not None:
                failure["missing"] = missing
            failures.append(failure)

    # This is the declared clean diagnostic pilot, not a tunable pass threshold.
    require("target_cohort_size", len(manifest.cases), 30)
    mobile = sum(c.mobile_first is True for c in manifest.cases)
    if mobile < 10:
        failures.append({"code": "minimum_mobile_first", "actual": mobile, "minimum": 10})
    split = {
        name: sum(c.split == name for c in manifest.cases) for name in ("development", "holdout")
    }
    require("development_holdout_split", split, {"development": 6, "holdout": 24})
    require(
        "qualification_plan_mismatch",
        [manifest.target_cases, manifest.minimum_mobile_first, manifest.planned_development_cases],
        [30, 10, 6],
    )
    require("required_evidence_modes", sorted(manifest.modes), sorted(MODES))

    by_mode = {mode: 0 for mode in MODES}
    complete_by_mode = dict(by_mode)
    references_missing = []
    tags = set(taxonomy.tags_by_id)
    reviewed_cases = 0
    for case in manifest.cases:
        reviewed_all = True
        for mode in MODES:
            ref = reference_for(case, mode)
            reviewed = ref.origin == "human_review"
            by_mode[mode] += reviewed
            reviewed_all = reviewed_all and reviewed
            missing = []
            if not reviewed:
                missing.append("human_review")
            if ref.primary_genre not in taxonomy.genres_by_id and not (
                ref.primary_genre is None and ref.boundary_note and ref.boundary_note.strip()
            ):
                missing.append("primary_or_unresolved_boundary")
            if tags - {k for k, v in ref.supported_truth.items() if v in STATES}:
                missing.append("mode_supported_tag_labels")
            if tags - {k for k, v in ref.game_truth.items() if type(v) is bool}:
                missing.append("game_truth_tag_labels")
            if missing:
                references_missing.append({"case_id": case.id, "mode": mode, "fields": missing})
            else:
                complete_by_mode[mode] += 1
        reviewed_cases += reviewed_all
    required_case_modes = len(manifest.cases) * len(MODES)
    require(
        "human_references_incomplete",
        sum(complete_by_mode.values()),
        required_case_modes,
        missing=references_missing,
    )

    groups = {}
    for report in reports:
        groups.setdefault((report["case_id"], report["mode"]), []).append(report)
    checks = (
        ("observation_bundles_unavailable", "observation_bundle_valid", False),
        ("mode_evidence_unavailable", "mode_evidence_available", False),
        ("identity_not_approved", "identity_approved", False),
        ("media_rights_not_permitted", "media_rights_permitted", True),
        ("permitted_media_assets_unavailable", "media_assets_verified", True),
    )
    readiness_counts = {}
    for code, field, media_only in checks:
        relevant = [
            (c.id, mode)
            for c in manifest.cases
            for mode in MODES
            if not media_only or mode != "metadata_only"
        ]
        missing = [
            {"case_id": cid, "mode": mode}
            for cid, mode in relevant
            if not groups.get((cid, mode))
            or not all(r["readiness"][field] for r in groups[(cid, mode)])
        ]
        ready = len(relevant) - len(missing)
        readiness_counts[field] = {"ready": ready, "required": len(relevant)}
        require(code, ready, len(relevant), missing=missing)
    recorded = {
        (r["case_id"], r["method"], r["mode"])
        for r in reports
        if r["readiness"]["prediction_cell_recorded"]
    }
    missing_cells = [
        {"case_id": c.id, "method": method, "mode": mode}
        for c in manifest.cases
        for method in manifest.methods
        for mode in MODES
        if (c.id, method, mode) not in recorded
    ]
    required_cells = required_case_modes * len(manifest.methods)
    require("prediction_cells_unavailable", len(recorded), required_cells, missing=missing_cells)
    pending = [
        {"case_id": c.id, "reasons": c.pending_reasons} for c in manifest.cases if c.pending_reasons
    ]
    require("case_readiness_pending", len(pending), 0, missing=pending)
    return {
        "benchmark_qualified": not failures,
        "qualification_policy": QUALIFICATION_POLICY,
        "qualification_failure_reasons": failures,
        "actual_cases": len(manifest.cases),
        "cases_not_yet_assembled": max(0, 30 - len(manifest.cases)),
        "target_cases": 30,
        "mobile_first_cases": mobile,
        "minimum_mobile_first": 10,
        "split_counts": split,
        "required_methods": manifest.methods,
        "required_modes": list(MODES),
        "declared_modes": manifest.modes,
        "required_prediction_cells": required_cells,
        "target_prediction_cells": 30 * len(manifest.methods) * len(MODES),
        "recorded_prediction_cells": len(recorded),
        "ready_prediction_cells": sum(
            r["measurement"]["status"] in {"complete", "partial"} for r in reports
        ),
        # Count case×mode references once, independently of the number of methods.
        "human_reviewed_references": reviewed_cases,
        "human_reviewed_references_by_mode": by_mode,
        "human_reviewed_reference_cells": sum(by_mode.values()),
        "complete_human_references_by_mode": complete_by_mode,
        "required_reference_cells": required_case_modes,
        "readiness_counts": readiness_counts,
        "pending_result_cells": sum(r["measurement"]["status"] == "pending" for r in reports),
        "error_result_cells": sum(r["measurement"]["status"] == "error" for r in reports),
        "paid_calls": 0,
        "limitations": manifest.limitations,
    }


def context_for(bundle, mode, taxonomy):
    if mode == "media_only" and bundle.observer_input != "media_blind":
        raise ValueError("Blind media requires observations made without metadata")
    observations = [
        o
        for o in bundle.observations
        if mode == "combined" or (o.kind == "metadata_quote") == (mode == "metadata_only")
    ]
    boundary = ObservationBoundary(taxonomy)
    for evidence in bundle.evidence:
        boundary.validate([o for o in observations if o.evidence_id == evidence.id], evidence)
    gate = validate_identity(bundle.identity, bundle.evidence)
    allowed = {s.evidence_id for s in gate.sources if s.eligible}
    observations = [o for o in observations if o.evidence_id in allowed]
    used = {o.evidence_id for o in observations}
    evidence = [e for e in bundle.evidence if e.id in used]
    context = JevQuestionCompiler.build_state(
        game_id=bundle.identity.subject.canonical_game_id
        if bundle.identity.subject
        else "unresolved",
        game_title=None,
        observations=observations,
        evidence=evidence,
        blind_media=mode == "media_only",
    )
    return context, observations, gate


def validate_measurement(row, taxonomy):
    """Isolate invalid questions while keeping valid independent categorical answers."""
    errors = []
    if set(row.tags) - set(taxonomy.tags_by_id):
        raise ValueError("Unknown taxonomy tag IDs")
    for tag_id, tag in row.tags.items():
        if tag.execution == "valid":
            valid = tag.state in STATES and (
                tag.probabilities is None
                or (
                    valid_distribution(tag.probabilities, STATES)
                    and tag.probabilities[tag.state] == max(tag.probabilities.values())
                )
            )
        else:
            valid = tag.state is None and tag.probabilities is None
        if not valid:
            errors.append(
                {
                    "question": tag_id,
                    "code": "invalid_saved_answer",
                    "raw": tag.model_dump(mode="json"),
                }
            )
            tag.execution, tag.state, tag.probabilities = "error", None, None
    if row.genre_execution == "valid":
        ids = set(taxonomy.genres_by_id)
        p = row.genre_probabilities
        valid = row.primary_genre is None or row.primary_genre in ids
        if p is not None:
            valid = valid and valid_distribution(p, ids | {"insufficient_evidence"})
            if valid and row.primary_genre is not None:
                valid = (
                    p[row.primary_genre] == max(p.values())
                    and p[row.primary_genre] > p["insufficient_evidence"]
                )
    else:
        valid = row.primary_genre is None and row.genre_probabilities is None
    if not valid:
        errors.append(
            {
                "question": "genre",
                "code": "invalid_saved_answer",
                "raw_probabilities": row.genre_probabilities,
                "raw_primary": row.primary_genre,
            }
        )
        row.genre_execution, row.primary_genre, row.genre_probabilities = "error", None, None
    if row.status == "complete" and (
        len(row.tags) != len(taxonomy.tags)
        or row.genre_execution != "valid"
        or any(t.execution != "valid" for t in row.tags.values())
    ):
        row.status = "partial"
    if errors:
        row.status = (
            "partial"
            if row.genre_execution == "valid"
            or any(t.execution == "valid" for t in row.tags.values())
            else "error"
        )
    return errors


def replay_manifest(manifest_path: Path, output: Path) -> dict:
    started = perf_counter()
    raw_manifest = manifest_path.read_bytes()
    manifest = BenchmarkManifest.model_validate_json(raw_manifest)
    taxonomy = load_taxonomy()
    taxonomy_hash = sha256(default_taxonomy_path().read_bytes())
    if manifest.taxonomy_sha256 != taxonomy_hash:
        raise ValueError("Frozen taxonomy hash mismatch")
    root = manifest_path.parent
    if output.exists():
        raise ValueError("Output already exists; use a new run directory")
    # Do not let output overlap any frozen input artifact/directory.
    artifact_paths = [root / a.path for c in manifest.cases for a in c.observations.values()]
    artifact_paths += [
        root / a.path for c in manifest.cases for v in c.results.values() for a in v.values()
    ]
    if any(p.resolve().is_relative_to(output.resolve()) for p in [manifest_path, *artifact_paths]):
        raise ValueError("Output overlaps frozen inputs")
    reports, rows = [], []
    for case in manifest.cases:
        for mode in manifest.modes:
            for method in manifest.methods:
                reference = reference_for(case, mode)
                row = CaseMeasurement(
                    case_id=case.id,
                    method=method,
                    mode=mode,
                    platform=case.platform,
                    status="pending",
                    reference=reference,
                )
                report = {
                    "case_id": case.id,
                    "method": method,
                    "mode": mode,
                    "split": case.split,
                    "errors": [],
                    "pending_reasons": list(case.pending_reasons),
                    "provenance": {
                        "manifest_sha256": sha256(raw_manifest),
                        "taxonomy_sha256": taxonomy_hash,
                    },
                    "requests": [],
                    "observer_requests": [],
                    "end_to_end_latency_ms": None,
                    "usage_status": "unknown",
                    "latency_scope": "unknown",
                    "readiness": {
                        "observation_bundle_valid": False,
                        "mode_evidence_available": False,
                        "identity_approved": False,
                        "media_rights_permitted": False,
                        "media_assets_verified": False,
                        "prediction_cell_recorded": False,
                    },
                }
                try:
                    obs_ref = case.observations.get(mode)
                    if obs_ref is None:
                        report["pending_reasons"].append("missing_observation_bundle")
                    else:
                        bundle = ObservationBundle.model_validate_json(obs_ref.read(root))
                        context, observations, gate = context_for(bundle, mode, taxonomy)
                        report["provenance"].update(
                            observation_sha256=obs_ref.sha256,
                            evidence_version=bundle.evidence_version,
                            context_sha256=sha256(context.encode()),
                            observer_model=bundle.observer_model,
                            observer_prompt_version=bundle.observer_prompt_version,
                            residual_visible_identity_cues=bundle.residual_visible_identity_cues,
                        )
                        if case.canonical_game_id and (
                            bundle.identity.subject is None
                            or case.canonical_game_id != bundle.identity.subject.canonical_game_id
                        ):
                            raise ValueError("Case and evidence subject identities differ")
                        readiness = report["readiness"]
                        readiness["observation_bundle_valid"] = True
                        readiness["identity_approved"] = bool(case.canonical_game_id) and (
                            gate.status == "eligible"
                        )
                        has_text = any(o.kind == "metadata_quote" for o in observations)
                        has_media = any(o.kind != "metadata_quote" for o in observations)
                        readiness["mode_evidence_available"] = (
                            has_text
                            if mode == "metadata_only"
                            else has_media
                            if mode == "media_only"
                            else has_text and has_media
                        )
                        report["observer_requests"] = [
                            r.model_dump(mode="json") for r in bundle.observer_requests
                        ]
                        row.identity_eligible = gate.status == "eligible"
                        row.evidence_available = bool(observations)
                        if mode != "metadata_only":
                            used = {o.evidence_id for o in observations}
                            media = [
                                e
                                for e in bundle.evidence
                                if e.type.value in {"gameplay_image", "gameplay_clip"}
                                and e.id in used
                            ]
                            readiness["media_rights_permitted"] = bundle.media_rights == "permitted"
                            if bundle.media_rights != "permitted" or not media:
                                report["pending_reasons"].append("permitted_media_unavailable")
                            for e in media:
                                asset = bundle.assets.get(e.id)
                                if asset is None:
                                    report["pending_reasons"].append("media_asset_unavailable")
                                elif sha256(asset.read(root)) != e.sha256:
                                    raise ValueError("Evidence media hash mismatch")
                            readiness["media_assets_verified"] = bool(media) and all(
                                e.id in bundle.assets for e in media
                            )
                        result_ref = case.results.get(method, {}).get(mode)
                        if result_ref is None:
                            report["pending_reasons"].append("missing_saved_prediction")
                        elif not report["pending_reasons"]:
                            prediction = SavedPrediction.model_validate_json(result_ref.read(root))
                            expected = (
                                case.id,
                                method,
                                mode,
                                bundle.evidence_version,
                                obs_ref.sha256,
                                sha256(context.encode()),
                                taxonomy_hash,
                            )
                            actual = (
                                prediction.case_id,
                                prediction.method,
                                prediction.mode,
                                prediction.evidence_version,
                                prediction.observation_sha256,
                                prediction.context_sha256,
                                prediction.taxonomy_sha256,
                            )
                            if actual != expected:
                                raise ValueError(
                                    "Prediction does not match frozen case/context/method/mode"
                                )
                            if prediction.raw_response:
                                prediction.raw_response.read(root)
                            row = prediction.measurement.model_copy(deep=True)
                            # Truth and eligibility never come from a prediction adapter.
                            row.case_id, row.method, row.mode = case.id, method, mode
                            row.platform, row.reference = case.platform, reference
                            row.identity_eligible, row.evidence_available = (
                                gate.status == "eligible",
                                bool(observations),
                            )
                            policy = evidence_eligibility(
                                taxonomy,
                                bundle.evidence,
                                observations,
                                bundle.identity,
                                bundle.profiles,
                                bundle.claims,
                            )
                            row.genre_evidence_eligible = bool(policy["genre"]["observation_ids"])
                            row.genre_support_verified = bool(
                                support_links(
                                    "genre", row.primary_genre, policy, observations, bundle.claims
                                )
                            )
                            for tid, t in row.tags.items():
                                if tid in policy:
                                    t.evidence_eligible = bool(policy[tid]["observation_ids"])
                                    t.support_verified = bool(
                                        support_links(
                                            tid, t.state, policy, observations, bundle.claims
                                        )
                                    )
                            report["errors"] += prediction.errors + validate_measurement(
                                row, taxonomy
                            )
                            report.update(
                                requests=[r.model_dump(mode="json") for r in prediction.requests],
                                end_to_end_latency_ms=prediction.end_to_end_latency_ms,
                                latency_scope=prediction.latency_scope,
                            )
                            report["provenance"].update(
                                result_sha256=result_ref.sha256,
                                model_version=prediction.model_version,
                                prompt_version=prediction.prompt_version,
                                code_version=prediction.code_version,
                            )
                            report["evidence_policy"] = policy
                            # Failed/partial attempts belong in the benchmark denominator too.
                            readiness["prediction_cell_recorded"] = row.status in {
                                "complete",
                                "partial",
                                "error",
                            }
                except (ValueError, OSError, KeyError) as exc:
                    row = CaseMeasurement(
                        case_id=case.id,
                        method=method,
                        mode=mode,
                        platform=case.platform,
                        status="error",
                        reference=reference,
                    )
                    # Do not echo validation/source contents into public logs.
                    report["errors"].append(
                        {"code": "artifact_or_contract_error", "type": type(exc).__name__}
                    )
                requests = report["requests"] + report["observer_requests"]
                report["usage_status"] = (
                    "reported_per_request"
                    if requests and all(r.get("usage") is not None for r in requests)
                    else "unknown_or_partial"
                )
                report["measurement"] = row.model_dump(mode="json")
                reports.append(report)
                rows.append(row)
    # Only within-method/mode metrics; never pool repeated cases into an apparent larger dataset.
    split_metrics = {
        split: {
            method: {
                mode: summarize(
                    [
                        r
                        for r, report in zip(rows, reports, strict=True)
                        if report["split"] == split and r.method == method and r.mode == mode
                    ],
                    taxonomy,
                )
                for mode in manifest.modes
            }
            for method in manifest.methods
        }
        for split in ("development", "holdout")
    }
    metrics = {
        method: {
            mode: summarize([r for r in rows if r.method == method and r.mode == mode], taxonomy)
            for mode in manifest.modes
        }
        for method in manifest.methods
    }
    availability = benchmark_readiness(manifest, reports, taxonomy)
    output.mkdir(parents=True, exist_ok=False)
    (output / "cases.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in reports)
    )
    result = {
        "manifest_sha256": sha256(raw_manifest),
        "benchmark_qualified": availability["benchmark_qualified"],
        "qualification_failure_reasons": availability["qualification_failure_reasons"],
        "availability": availability,
        "metrics": metrics,
        "metrics_by_split": split_metrics,
        "replay_latency_ms": (perf_counter() - started) * 1000,
        "replay_latency_scope": "local replay and reporting; not inference latency",
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    (output / "manifest.json").write_bytes(raw_manifest)
    return result
