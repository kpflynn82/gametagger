"""Hash-bound, game-paired reports. Unknown/incompatible never means zero effect."""

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gametagger.evaluation.metrics import CaseMeasurement
from gametagger.workspace.quality import quality_comparison


class MethodRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    method_id: str
    version: str
    method_family: Literal[
        "legacy_combined", "conventional", "jev_hierarchical", "jev_direct", "other"
    ] = "other"
    criteria_hash: str | None = None
    cohort: str
    case_ids: list[str]
    evidence_hashes: dict[str, str]
    observation_hashes: dict[str, str]
    taxonomy_hash: str
    label_origin: Literal["human_review", "legacy_machine", "unavailable"]
    label_version: str = "unavailable"
    conditions: dict[str, str]
    kind: Literal["measured", "replayed", "illustrative", "unavailable"]
    correct: dict[str, bool] = Field(default_factory=dict)
    accepted_primary: dict[str, bool] = Field(default_factory=dict)
    execution_error: dict[str, bool] = Field(default_factory=dict)
    # Complete wall-clock/cost only. A final call duration or partial token bill is ineligible.
    total_latency_ms: dict[str, Annotated[float, Field(ge=0)]] = Field(default_factory=dict)
    complete_cost_usd: dict[str, Annotated[float, Field(ge=0)]] = Field(default_factory=dict)
    accounting_complete: bool = False
    case_measurements: list[CaseMeasurement] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def measured_cases_match_method(self):
        from gametagger.taxonomy import load_taxonomy

        ids = [r.case_id for r in self.case_measurements]
        if len(ids) != len(set(ids)) or not set(ids) <= set(self.case_ids):
            raise ValueError("Case measurements require unique assigned case IDs")
        if not self.case_measurements:
            return self
        import re

        hashes = [
            self.taxonomy_hash,
            *self.evidence_hashes.values(),
            *self.observation_hashes.values(),
        ]
        if self.criteria_hash is not None:
            hashes.append(self.criteria_hash)
        if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in hashes):
            raise ValueError("Detailed measurements require SHA-256 provenance hashes")
        taxonomy = load_taxonomy()
        tags = {t.id for t in taxonomy.tags}
        for row in self.case_measurements:
            if row.reference.origin == "human_review" and (
                self.label_origin != "human_review" or self.label_version == "unavailable"
            ):
                raise ValueError(
                    "Human-reviewed case labels need matching method provenance/version"
                )
            if any(
                g is not None and g not in taxonomy.genres_by_id
                for g in (row.primary_genre, row.reference.primary_genre)
            ):
                raise ValueError("Primary IDs must use the fixed canonical genre vocabulary")
            if row.method != self.method_id or row.mode != self.conditions.get("mode"):
                raise ValueError("Case method/input mode must match the declared method")
            if (
                set(row.tags) | set(row.reference.supported_truth) | set(row.reference.game_truth)
            ) - tags:
                raise ValueError("Case contains a tag outside the frozen taxonomy")
        return self


class Effect(BaseModel):
    name: str
    value: float | None = None
    numerator: float | None = None
    denominator: int = 0
    cohort: str
    observation_unit: str = "game"
    label_provenance: str
    policy: str = "eligible-assigned-cohort-v1"
    method_versions: list[str]
    status: str
    reason: str | None = None


def incompatible(baseline, candidate):
    for field in (
        "cohort",
        "case_ids",
        "evidence_hashes",
        "observation_hashes",
        "taxonomy_hash",
        "conditions",
        "label_version",
    ):
        if getattr(baseline, field) != getattr(candidate, field):
            return f"Incompatible {field}"
    ids = set(baseline.case_ids)
    if (
        not ids
        or len(ids) != len(baseline.case_ids)
        or any(
            set(m.evidence_hashes) != ids
            or set(m.observation_hashes) != ids
            or not all(m.evidence_hashes.values())
            or not all(m.observation_hashes.values())
            for m in (baseline, candidate)
        )
    ):
        return "Missing or duplicate paired evidence/observations"
    if any(m.kind in {"illustrative", "unavailable"} for m in (baseline, candidate)):
        return "Illustrative/unavailable data cannot establish an effect"
    return None


def compare(baseline: MethodRecord, candidate: MethodRecord):
    reason = incompatible(baseline, candidate)
    if baseline.case_measurements or candidate.case_measurements:
        quality = quality_comparison(baseline, candidate, reason)
        metrics = quality["headline"].get("Actual primary correctness")
        available = metrics and all(m["value"] is not None for m in metrics)
        return Effect(
            name="Actual primary correctness uplift (percentage points)",
            cohort=baseline.cohort,
            label_provenance=baseline.label_origin,
            method_versions=[baseline.version, candidate.version],
            status=("measured" if baseline.kind == candidate.kind == "measured" else "replayed")
            if available
            else "unavailable",
            reason=None
            if available
            else quality["reason"] or "Human-reviewed paired outcomes unavailable",
            value=100 * (metrics[1]["value"] - metrics[0]["value"]) if available else None,
            numerator=metrics[1]["numerator"] - metrics[0]["numerator"] if available else None,
            denominator=metrics[0]["denominator"] if available else 0,
        )
    ids = set(baseline.case_ids)
    if any(
        m.label_origin != "human_review"
        or m.label_version == "unavailable"
        or set(m.correct) != ids
        for m in (baseline, candidate)
    ):
        reason = reason or "Human-reviewed paired outcomes unavailable"
    effect = Effect(
        name="Actual primary correctness uplift (percentage points)",
        cohort=baseline.cohort,
        label_provenance=baseline.label_origin,
        method_versions=[baseline.version, candidate.version],
        status="unavailable"
        if reason
        else ("measured" if baseline.kind == candidate.kind == "measured" else "replayed"),
        reason=reason,
    )
    if not reason:
        difference = sum(candidate.correct[i] - baseline.correct[i] for i in ids)
        effect.value = 100 * difference / len(ids)
        effect.numerator, effect.denominator = difference, len(ids)
    return effect


class ScoreRow(BaseModel):
    metric: str
    baseline: float | None = None
    candidate: float | None = None
    change: float | None = None
    unit: str
    paired_n: int = 0
    baseline_numerator: float | None = None
    candidate_numerator: float | None = None
    baseline_denominator: int = 0
    candidate_denominator: int = 0
    status: str = "Not measured"
    reason: str | None = None


class ComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    schema_version: Literal["paired-report-v1", "paired-report-v2"] = "paired-report-v2"
    report_id: str
    comparison_question: Literal[
        "unassigned",
        "source_repair",
        "observer_separation",
        "classifier_increment",
        "end_to_end",
        "jev_method",
    ] = "unassigned"
    kind: Literal["measured", "replayed", "illustrative", "unavailable"]
    baseline: MethodRecord
    candidate: MethodRecord
    input_hashes: dict[str, str]
    # Values are always recomputed on read. A submitted scorecard is never trusted.

    @model_validator(mode="after")
    def provenance_kind(self):
        if self.schema_version == "paired-report-v1" and (
            self.baseline.case_measurements or self.candidate.case_measurements
        ):
            raise ValueError("Detailed case measurements require paired-report-v2")
        kinds = {self.baseline.kind, self.candidate.kind}
        expected = (
            "illustrative"
            if "illustrative" in kinds
            else "unavailable"
            if "unavailable" in kinds
            else "measured"
            if kinds == {"measured"}
            else "replayed"
        )
        if self.kind != expected:
            raise ValueError("Report kind must match underlying method provenance")
        return self

    def view(self):
        a, b = self.baseline, self.candidate
        reason = incompatible(a, b)
        if self.comparison_question == "classifier_increment" and (
            a.method_family != "conventional"
            or b.method_family not in {"jev_hierarchical", "jev_direct"}
            or not a.criteria_hash
            or a.criteria_hash != b.criteria_hash
        ):
            reason = (
                reason
                or "Jev increment requires conventional→Jev roles and identical declared criteria"
            )
        correctness = compare(a, b)
        quality = quality_comparison(a, b, reason)
        n = len(a.case_ids)
        rows = []
        for name, unit in (
            ("Actual primary correctness", "% / percentage-point change"),
            ("Accepted-primary precision", "% / percentage-point change"),
            ("Accepted attribute precision", "%"),
            ("End-to-end recall", "%"),
            ("Useful coverage", "% / percentage-point change"),
            ("Median total latency", "ms / ms change"),
            ("p95 total latency", "ms / ms change"),
            ("Cost per useful result", "USD / USD change"),
            ("Execution error rate", "% / percentage-point change"),
            ("Partial-output rate", "% / percentage-point change"),
        ):
            row = ScoreRow(metric=name, unit=unit, reason=reason)
            values = []
            if name in quality["headline"]:
                ma, mb = quality["headline"][name]
                row.baseline = 100 * ma["value"] if ma["value"] is not None else None
                row.candidate = 100 * mb["value"] if mb["value"] is not None else None
                row.baseline_numerator, row.baseline_denominator = (
                    ma["numerator"],
                    ma["denominator"],
                )
                row.candidate_numerator, row.candidate_denominator = (
                    mb["numerator"],
                    mb["denominator"],
                )
                row.paired_n = (
                    n
                    if name in {"Useful coverage", "Execution error rate", "Partial-output rate"}
                    else quality["paired_games"]
                )
                if row.baseline is not None and row.candidate is not None:
                    row.change = row.candidate - row.baseline
                row.status = (
                    self.kind
                    if row.baseline is not None or row.candidate is not None
                    else "Not measured"
                )
                row.reason = (
                    "Undefined denominators remain null; tag KPIs use supported human labels"
                )
                rows.append(row.model_dump())
                continue
            for m in (a, b):
                ids = set(m.case_ids)
                if reason:
                    break
                if (a.case_measurements or b.case_measurements) and name in {
                    "Actual primary correctness",
                    "Accepted-primary precision",
                    "Accepted attribute precision",
                    "End-to-end recall",
                    "Useful coverage",
                }:
                    # A missing/invalid detailed pair cannot fall back to summary booleans.
                    pass
                elif name == "Actual primary correctness" and correctness.value is not None:
                    values.append((100 * sum(m.correct.values()) / n, sum(m.correct.values()), n))
                elif name in {"Useful coverage", "Execution error rate"}:
                    data = m.accepted_primary if name == "Useful coverage" else m.execution_error
                    if set(data) == ids:
                        values.append((100 * sum(data.values()) / n, sum(data.values()), n))
                elif name in {"Median total latency", "p95 total latency"}:
                    v = sorted(m.total_latency_ms.values())
                    if set(m.total_latency_ms) == ids and all(0 <= x < float("inf") for x in v):
                        # p95 from very sparse samples would be misleading; require >=20 cases.
                        if name == "Median total latency" and n >= 2:
                            values.append((median(v), None, n))
                        elif name == "p95 total latency" and n >= 20:
                            import math

                            values.append((v[math.ceil(0.95 * n) - 1], None, n))
                elif name == "Cost per useful result":
                    cost = m.complete_cost_usd
                    accepted = sum(m.accepted_primary.values())
                    if a.case_measurements or b.case_measurements:
                        measures = quality["headline"].get("Useful coverage")
                        accepted = int(measures[0 if m is a else 1]["numerator"]) if measures else 0
                    if (
                        m.accounting_complete
                        and set(cost) == ids
                        and (bool(m.case_measurements) or set(m.accepted_primary) == ids)
                        and accepted
                        and all(0 <= x < float("inf") for x in cost.values())
                    ):
                        values.append((sum(cost.values()) / accepted, sum(cost.values()), accepted))
            if len(values) == 2:
                row.baseline, row.baseline_numerator, row.baseline_denominator = values[0]
                row.candidate, row.candidate_numerator, row.candidate_denominator = values[1]
                row.change = row.candidate - row.baseline
                row.paired_n = quality["paired_games"] if name in quality["headline"] else n
                row.status = self.kind
            else:
                row.reason = reason or "Complete paired measurements/labels unavailable"
            rows.append(row.model_dump())
        return {
            "id": self.report_id,
            "comparison_question": self.comparison_question,
            "kind": self.kind,
            "scorecard": rows,
            "quality": quality,
            "recommendation": "Inconclusive",
            "reason": "Descriptive matched results; no automatic promotion or causal claim.",
            "comparison_eligibility": reason or "Matched input contract; label eligibility per KPI",
            "cohort": a.cohort,
            "sample_size": n,
            "observation_unit": "game",
            "useful_contract": "approved-primary-v1; tag-decision coverage not inferred",
            "label_provenance": a.label_origin,
            "label_version": a.label_version,
            "methods": [m.model_dump(exclude={"case_measurements"}) for m in (a, b)],
            "input_hashes": self.input_hashes,
            "uncertainty": "Not estimated; no claim of statistically reliable uplift",
        }


def main():
    parser = argparse.ArgumentParser(
        description="Build a private saved paired report; no model calls"
    )
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--question",
        default="unassigned",
        choices=[
            "unassigned",
            "source_repair",
            "observer_separation",
            "classifier_increment",
            "end_to_end",
            "jev_method",
        ],
    )
    args = parser.parse_args()
    raw = [p.read_bytes() for p in (args.baseline, args.candidate)]
    a, b = [MethodRecord.model_validate_json(v) for v in raw]
    digest = hashlib.sha256(b"\n".join(raw)).hexdigest()
    report = ComparisonReport(
        report_id=digest,
        comparison_question=args.question,
        kind=(
            "illustrative"
            if "illustrative" in {a.kind, b.kind}
            else "unavailable"
            if "unavailable" in {a.kind, b.kind}
            else "measured"
            if a.kind == b.kind == "measured"
            else "replayed"
        ),
        baseline=a,
        candidate=b,
        input_hashes={
            k: hashlib.sha256(v).hexdigest()
            for k, v in zip(("baseline", "candidate"), raw, strict=True)
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        handle.write(report.model_dump_json(indent=2))
    args.output.chmod(0o600)
    print(json.dumps(report.view()["comparison_eligibility"]))


if __name__ == "__main__":
    main()
