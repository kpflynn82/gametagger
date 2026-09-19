"""Read-only measurement of the preserved intake suite; no identity or truth adjudication."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from gametagger.evaluation.benchmark import sha256, validate_measurement
from gametagger.evaluation.metrics import (
    CaseMeasurement,
    Reference,
    TagMeasurement,
    summarize,
)
from gametagger.evaluation.replay import verify_snapshot
from gametagger.taxonomy import load_taxonomy

# Historical key aliases are comparisons only, never truth or implied negatives.
TAG_ALIASES = {
    "feature_multiplayer": ["multiplayer"],
    "world_open_world": ["open_world"],
    "world_procedural": ["procedural"],
    "narrative_story_driven": ["story_driven"],
    "engagement_co_op": ["mechanic_co_op"],
}


def audit(snapshot: Path, manifest_path: Path, output: Path):
    manifest = json.loads(manifest_path.read_text())
    verify_snapshot(snapshot, manifest)
    if output.resolve().is_relative_to(snapshot.resolve()):
        raise ValueError("Output must be outside immutable inputs")
    if output.exists():
        raise ValueError("Use a new output directory")
    taxonomy = load_taxonomy()
    comparison = json.loads((snapshot / "comparison.json").read_text())
    ids = json.loads((snapshot / "sample-manifest.json").read_text())["sampled_ids"]
    rows, reports, abstentions = [], [], []
    tag_audit = {
        t.id: {
            "allowed_types": list(t.allowed_evidence),
            "available_source_types": {},
            "available_modalities": {},
            "type_eligible_records_before_identity": 0,
            "identity_and_type_eligible_records": 0,
            "comparable_legacy_booleans_completed": 0,
            "missing_or_ambiguous_legacy_completed": 0,
            "reviewed_positive_claims": None,
            "reviewed_negative_claims": None,
            "claim_review_status": "pending; no human source-span adjudication",
        }
        for t in taxonomy.tags
    }
    type_counts, modalities = Counter(), Counter()
    for case_id in ids:
        raw_path = snapshot / f"results/{case_id}.json"
        raw = json.loads(raw_path.read_text())
        record = json.loads((snapshot / f"records/{case_id}.json").read_text())
        retry = (snapshot / f"first-attempt-errors/{case_id}.json").exists()
        done = raw["status"] == "completed"
        row = CaseMeasurement(
            case_id=str(case_id),
            method="historical_jev",
            mode="metadata_only",
            status="complete" if done else "error",
            genre_execution="valid" if done else "error",
            evidence_available=raw["evidence_available"],
            first_attempt_success=not retry,
            retried=retry,
            retry_recovered=done if retry else None,
            reference=Reference(origin="legacy_reference"),
        )
        evidence = {e["id"]: e for e in raw.get("evidence", [])}
        usable_types = {
            evidence[o["evidence_id"]]["type"]
            for o in raw.get("observations", [])
            if o["kind"] == "metadata_quote" and o["evidence_id"] in evidence
        }
        type_counts.update(usable_types)
        if raw.get("observations"):
            modalities["text"] += 1
        errors = []
        if done:
            batch = raw["result"]
            g = batch["genre"]
            row.genre_execution = "valid"
            row.primary_genre = g["primary_genre"]
            row.genre_probabilities = g["global_genre_probabilities"]
            row.genre_action = g["action"]
            for tag in batch["tags"]:
                row.tags[tag["tag_id"]] = TagMeasurement(
                    state=tag["state"],
                    execution="valid",
                    probabilities=tag["probabilities"],
                    action=tag["action"],
                )
            errors = validate_measurement(row, taxonomy)
            if raw["evidence_available"] and g["primary_genre"] is None:
                family = g["family_probabilities"]
                total = sum(family.values())
                weighted = {
                    fid: family[fid] / total * p["insufficient_evidence"] / sum(p.values())
                    for fid, p in g["conditional_genre_probabilities"].items()
                }
                abstentions.append(
                    {
                        "case_id": str(case_id),
                        "result_sha256": sha256(raw_path.read_bytes()),
                        "family_unknown_mass": family["insufficient_evidence"] / total,
                        "weighted_conditional_unknown_mass": weighted,
                        "global_unknown": g["global_genre_probabilities"]["insufficient_evidence"],
                        "top_nonnull": sorted(
                            (
                                (k, v)
                                for k, v in g["global_genre_probabilities"].items()
                                if k != "insufficient_evidence"
                            ),
                            key=lambda x: (-x[1], x[0]),
                        )[0],
                        "semantic_cause": "unresolved; identity and evidence review needed",
                        "conditional_unknown_meaning": "no eligible genre supported in that family",
                    }
                )
        for t in taxonomy.tags:
            a = tag_audit[t.id]
            a["type_eligible_records_before_identity"] += bool(
                usable_types & set(t.allowed_evidence)
            )
            if done:
                old = record.get("tags") or {}
                values = [
                    old[k] for k in [t.id, *TAG_ALIASES.get(t.id, [])] if type(old.get(k)) is bool
                ]
                comparable = bool(values) and len(set(values)) == 1
                a["comparable_legacy_booleans_completed"] += comparable
                a["missing_or_ambiguous_legacy_completed"] += not comparable
        attempts = [a for a in manifest["attempts"] if a["record_id"] == case_id]
        reports.append(
            {
                "case_id": str(case_id),
                "measurement": row.model_dump(mode="json"),
                "provenance": {
                    "result_sha256": sha256(raw_path.read_bytes()),
                    "attempts": attempts,
                    "reference_manifest_sha256": sha256(manifest_path.read_bytes()),
                    "source_snapshot_dates": [
                        a.get("snapshot_record_created_at") for a in attempts
                    ],
                    "source_acquired_at": None,
                    "code_version": manifest["baseline_commit"],
                    "model_version": manifest["model"],
                    "prompt_version": manifest["decision_prompt_version"],
                    "taxonomy_sha256": manifest["taxonomy_sha256"],
                },
                "errors": errors
                or (
                    [
                        {
                            "code": "historical_terminal_error",
                            "detail_location": f"results/{case_id}.json",
                        }
                    ]
                    if not done
                    else []
                ),
                "usage": raw.get("result", {}).get("usage"),
                "usage_scope": "final requests only; retries/failures incomplete; not billing",
                "observer_usage": None,
                "observer_kind": "stored-description exact quotes; no vision request",
                "final_call_latency_ms": raw.get("latency_ms"),
                "end_to_end_latency_ms": None,
                "historical_baseline": {
                    "genre": raw.get("legacy_primary_genre"),
                    "tags": record.get("tags"),
                    "origin": "legacy_machine; not human truth",
                },
                "source_identity_status": "unverified",
                "type_eligible_before_identity": {
                    t.id: bool(usable_types & set(t.allowed_evidence)) for t in taxonomy.tags
                },
            }
        )
        rows.append(row)
    metrics = summarize(rows, taxonomy)
    for tid, a in tag_audit.items():
        a.update(
            available_source_types=dict(type_counts),
            available_modalities=dict(modalities),
            new_outcomes=metrics["tags"][tid]["new_outcomes"],
            execution_errors=metrics["tags"][tid]["errors"],
            not_evaluated=metrics["tags"][tid]["not_evaluated"],
        )
    # Original terminal failures have no saved component answers: every question failed/unavailable.
    for r in rows:
        if r.status == "error":
            r.tags = {t.id: TagMeasurement(execution="error") for t in taxonomy.tags}
    metrics = summarize(rows, taxonomy)
    for tid, a in tag_audit.items():
        a["execution_errors"] = metrics["tags"][tid]["errors"]
        a["not_evaluated"] = metrics["tags"][tid]["not_evaluated"]
    result = {
        "schema_version": "legacy-measurement-audit-v1",
        "audit_code_sha256": sha256(Path(__file__).read_bytes()),
        "measurement_version": "measurement-v2",
        "paid_calls": 0,
        "reference_manifest_sha256": sha256(manifest_path.read_bytes()),
        "records": len(rows),
        "taxonomy_sha256": manifest["taxonomy_sha256"],
        "new_outcomes_all_tags": dict(
            Counter(t.state for r in rows for t in r.tags.values() if t.execution == "valid")
        ),
        "source_title_review_flags": sum(bool(r["source_title_review"]) for r in comparison),
        "source_title_review_note": "not a verified mismatch rate",
        "identity_review_pending": len(rows),
        "human_reviewed_truth": 0,
        "end_to_end_latency_ms": None,
        "per_tag": tag_audit,
        "text_bearing_abstentions": abstentions,
        "metrics": metrics,
        "limitations": [
            "Original sample is an intake stress suite, not 100 verified games.",
            "Historical agreement is not accuracy; labels are not human truth.",
            "Type-only diagnostics precede identity gating. No new identity approvals.",
            "No actual media was used; this is not a vision evaluation.",
            "Explicit positive/negative source-span review pending; never infer from absence.",
            "Original usage and final-call latency do not describe a bill or end-to-end pipeline.",
            "Legacy labels lack matching saved observations; unpaired baseline only.",
        ],
    }
    # Update saved rows after assigning terminal component statuses.
    for report, row in zip(reports, rows, strict=True):
        report["measurement"] = row.model_dump(mode="json")
    output.mkdir(parents=True, exist_ok=False)
    (output / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in reports))
    (output / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.snapshot, args.manifest, args.output)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "records",
                    "paid_calls",
                    "new_outcomes_all_tags",
                    "identity_review_pending",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
