"""Offline integrity verification and intake replay; no provider calls or snapshot edits."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gametagger.decisions.execution import validate_choice
from gametagger.decisions.jev import JevQuestionCompiler
from gametagger.domain import EvidenceItem, EvidenceType
from gametagger.identity import IdentityDecision, IdentityManifest, SourceIdentity, content_hash
from gametagger.taxonomy import load_taxonomy


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0)
    filesystem_mtime_utc: datetime


class ExperimentManifest(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: Literal["1"]
    experiment_id: str
    baseline_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    taxonomy_version: str
    taxonomy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_prompt_version: str
    model: str
    sdk_version: str
    files: list[Artifact]
    inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempts: list[dict]


def verify_snapshot(snapshot: Path, manifest: dict) -> None:
    ExperimentManifest.model_validate(manifest)
    inventory = json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(inventory).hexdigest() != manifest["inventory_sha256"]:
        raise ValueError("Experiment inventory hash mismatch")
    root = snapshot.resolve()
    seen = set()
    for entry in manifest["files"]:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root) or entry["path"] in seen:
            raise ValueError("Invalid or duplicate artifact path")
        seen.add(entry["path"])
        if (
            not path.is_file()
            or path.stat().st_size != entry["bytes"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]
        ):
            raise ValueError(f"Missing or changed immutable artifact: {entry['path']}")
    required = {
        "sample-manifest.json",
        "comparison.json",
        "summary.json",
        "input-audit.json",
        "fetch_sample.py",
        "run_evaluation.py",
        "make_report.py",
    }
    if not required <= seen:
        raise ValueError("Incomplete experiment inventory")
    sample = json.loads((root / "sample-manifest.json").read_text())
    if len(sample["sampled_ids"]) != 100 or len(set(sample["sampled_ids"])) != 100:
        raise ValueError("Original sample must retain 100 unique records")
    if not all(
        f"{kind}/{i}.json" in seen for kind in ("records", "results") for i in sample["sampled_ids"]
    ):
        raise ValueError("Missing original record/result")


def intake_record(record: dict, *, imported_at) -> tuple[IdentityManifest, list[EvidenceItem]]:
    decision = IdentityDecision(
        origin="imported",
        decided_at=imported_at,
        justification="Historical association is unverified; title similarity is not approval",
    )
    evidence, sources = [], []
    for provider, raw in (record.get("source_data") or {}).items():
        if not isinstance(raw, dict):
            continue
        eid = f"legacy-{record['id']}:{provider}"
        # Preserve failed/nontext sources in the audit too. No automatic eligibility.
        metadata = {
            k: raw[k]
            for k in ("description", "detailed_description")
            if isinstance(raw.get(k), str)
        }
        item = EvidenceItem(
            id=eid,
            type=EvidenceType.WIKIPEDIA if provider == "wikipedia" else EvidenceType.STORE_METADATA,
            source=provider,
            metadata=metadata,
        )
        evidence.append(item)
        product = raw.get("app_id") or raw.get("product_id") or raw.get("wikipedia_url")
        sources.append(
            SourceIdentity(
                evidence_id=eid,
                provider=provider,
                product_or_page_id=str(product) if product is not None else None,
                reported_title=raw.get("title"),
                publisher=raw.get("publisher") if isinstance(raw.get("publisher"), str) else None,
                developer=raw.get("developer") if isinstance(raw.get("developer"), str) else None,
                acquired_at=None,
                content_sha256=content_hash(item),
                decision=decision,
            )
        )
    manifest = IdentityManifest(
        evidence_version="legacy-original-unverified-v1",
        raw_record_id=str(record["id"]),
        raw_label=record["game_name"],
        record_kind="unresolved",
        record_decision=decision,
        subject=None,
        sources=tuple(sources),
    )
    return manifest, evidence


def replay(snapshot: Path, manifest_path: Path, output: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    verify_snapshot(snapshot, manifest)
    # Never allow generated corrections/replay output to mutate the reference snapshot.
    if output.resolve().is_relative_to(snapshot.resolve()):
        raise ValueError("Replay output must be outside the immutable snapshot")
    output.mkdir(parents=True, exist_ok=False)
    sample = json.loads((snapshot / "sample-manifest.json").read_text())
    intake = []
    for i in sample["sampled_ids"]:
        record = json.loads((snapshot / f"records/{i}.json").read_text())
        identity, evidence = intake_record(record, imported_at=manifest["preserved_at"])
        original = json.loads((snapshot / f"results/{i}.json").read_text())
        intake.append(
            dict(
                identity=identity.model_dump(mode="json"),
                evidence=[e.model_dump(mode="json") for e in evidence],
                historical_baseline={
                    "primary_genre": record.get("primary_genre"),
                    "tags": record.get("tags"),
                    "annotation_origin": "legacy_machine",
                },
                original_execution_status=original["status"],
                human_truth=None,
            )
        )
    (output / "intake.json").write_text(json.dumps(intake, indent=2, ensure_ascii=False))
    compiler = JevQuestionCompiler(load_taxonomy())
    specs = {
        **compiler.build_specs(),
        **compiler.build_genre_specs(list(compiler.taxonomy.families_by_id)),
    }
    findings = []
    for path in sorted((snapshot / "retry-raw").glob("*.json")):
        raw = json.loads(path.read_text())
        for key, answer in raw["answers"].items():
            _, error = validate_choice(answer, specs[key])
            if error:
                findings.append(
                    dict(
                        path=f"retry-raw/{path.name}",
                        question_id=key,
                        error=error.model_dump(),
                        model=raw["model"],
                    )
                )
    report = dict(
        records_retained=len(intake),
        identity_review_pending=len(intake),
        approved_corrections=0,
        paid_calls=0,
        invalid_retry_answers=findings,
        original_summary=json.loads((snapshot / "summary.json").read_text()),
        reference_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    (output / "replay-report.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(args.snapshot, args.manifest, args.output), indent=2))


if __name__ == "__main__":
    main()
