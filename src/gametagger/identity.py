"""Source association is an auditable approval, never a title-similarity inference."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gametagger.domain import EvidenceItem


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def content_hash(evidence: EvidenceItem) -> str:
    """Bind both media bytes and accompanying claims; a media hash alone misses metadata edits."""
    return digest(
        {"type": evidence.type.value, "sha256": evidence.sha256, "metadata": evidence.metadata}
    )


class AuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IdentityDecision(AuditModel):
    origin: Literal["human_review", "publisher_declaration", "automated_suggestion", "imported"]
    reviewer: str | None = None
    justification: str = Field(min_length=1)
    decided_at: datetime

    @property
    def approved(self) -> bool:
        return self.origin in {"human_review", "publisher_declaration"} and bool(
            self.reviewer and self.reviewer.strip()
        )


class SubjectIdentity(AuditModel):
    canonical_game_id: str = Field(min_length=1)
    namespace: Literal["catalog", "publisher_project"] = "catalog"
    release_id: str | None = None
    platform_id: str | None = None
    edition_id: str | None = None


class SourceIdentity(AuditModel):
    evidence_id: str
    provider: str
    acquisition: Literal["retrieved", "upload"] = "retrieved"
    product_or_page_id: str | None = None
    reported_title: str | None = None
    publisher: str | None = None
    developer: str | None = None
    year: int | None = None
    platform: str | None = None
    release_id: str | None = None
    edition_id: str | None = None
    acquired_at: datetime | None = None
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship: Literal[
        "verified_same_release",
        "approved_cross_release_scope",
        "approved_alias_localization",
        "related_different_product",
        "mismatch",
        "ambiguous",
        "unverified",
    ] = "unverified"
    decision: IdentityDecision
    # Explicit, reviewed aliases preserve original scripts; no normalization or stripping.
    approved_aliases: tuple[str, ...] = ()
    transferable_properties: tuple[str, ...] = ()


class Correction(AuditModel):
    previous_version_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    created_at: datetime


class IdentityManifest(AuditModel):
    schema_version: Literal["identity-v1"] = "identity-v1"
    evidence_version: str = Field(min_length=1)
    raw_record_id: str
    raw_label: str
    record_kind: Literal[
        "game_candidate",
        "release_edition",
        "dlc",
        "mode",
        "clip_chapter",
        "location_encounter",
        "other",
        "unresolved",
    ]
    record_decision: IdentityDecision
    subject: SubjectIdentity | None = None
    sources: tuple[SourceIdentity, ...] = ()
    corrections: tuple[Correction, ...] = ()

    @model_validator(mode="after")
    def unique_sources(self):
        if len({s.evidence_id for s in self.sources}) != len(self.sources):
            raise ValueError("Duplicate identity source")
        return self

    @property
    def version_hash(self) -> str:
        return digest(self.model_dump(mode="json"))

    def corrected(self, *, reason: str, reviewer: str, **changes) -> IdentityManifest:
        if {"raw_record_id", "raw_label"} & changes.keys():
            raise ValueError("Original imported record identity is immutable")
        if changes.get("evidence_version", self.evidence_version) == self.evidence_version:
            raise ValueError("Corrections require a new evidence version")
        if "corrections" in changes:
            raise ValueError("Correction history is append-only")
        data = self.model_dump()
        data.update(changes)
        data["corrections"] = (
            *self.corrections,
            Correction(
                previous_version_hash=self.version_hash,
                reason=reason,
                reviewer=reviewer,
                created_at=datetime.now(timezone.utc),
            ),
        )
        return IdentityManifest.model_validate(data)


class SourceEligibility(AuditModel):
    evidence_id: str
    eligible: bool
    reason: str
    properties: tuple[str, ...] = ()


class IdentityEligibility(AuditModel):
    status: Literal["eligible", "identity_unresolved", "invalid_record", "no_eligible_sources"]
    manifest_hash: str | None
    sources: tuple[SourceEligibility, ...] = ()
    reason: str

    def evidence_for(self, property_id: str) -> set[str]:
        return {
            s.evidence_id
            for s in self.sources
            if s.eligible and ("*" in s.properties or property_id in s.properties)
        }


def validate_identity(
    manifest: IdentityManifest | None, evidence: list[EvidenceItem]
) -> IdentityEligibility:
    if manifest is None:
        return IdentityEligibility(
            status="identity_unresolved",
            manifest_hash=None,
            reason="An explicit source association is required",
        )
    base = {"manifest_hash": manifest.version_hash}
    if not manifest.record_decision.approved or manifest.subject is None:
        return IdentityEligibility(
            **base,
            status="identity_unresolved",
            reason="Record kind and intended subject need approval",
        )
    if manifest.record_kind not in {"game_candidate", "release_edition"}:
        return IdentityEligibility(
            **base,
            status="invalid_record",
            reason="Preserved nongame record; no approved game-level subject",
        )
    decisions = []
    supplied = {e.id: e for e in evidence}
    if len(supplied) != len(evidence):
        raise ValueError("Duplicate evidence ID")
    sources = {s.evidence_id: s for s in manifest.sources}
    for eid in sorted(set(supplied) | set(sources)):
        s, item = sources.get(eid), supplied.get(eid)
        reason, properties = "Source has no verified association", ()
        if s is None or item is None:
            reason = "Source or content missing from evidence version"
        elif s.content_sha256 != content_hash(item):
            reason = "Content changed since identity review"
        elif not s.decision.approved:
            reason = "Imported or automated suggestions are not approval"
        elif s.decision.origin == "publisher_declaration" and not (
            s.acquisition == "upload" and manifest.subject.namespace == "publisher_project"
        ):
            reason = "Publisher declaration only associates its own project upload"
        elif not s.product_or_page_id:
            reason = "Missing actual source product/page or upload asset ID"
        elif s.relationship == "approved_cross_release_scope":
            properties = tuple(p for p in s.transferable_properties if p != "*")
            reason = (
                "Explicit cross-release property scope" if properties else "Empty transfer scope"
            )
        elif s.relationship in {"verified_same_release", "approved_alias_localization"}:
            mismatch = any(
                a is not None and a != b
                for a, b in [
                    (manifest.subject.release_id, s.release_id),
                    (manifest.subject.edition_id, s.edition_id),
                    (manifest.subject.platform_id, s.platform),
                ]
            )
            if mismatch:
                reason = "Release/platform/edition mismatch needs explicit transfer approval"
            elif s.relationship == "approved_alias_localization" and not s.approved_aliases:
                reason = "Localization requires an explicit approved alias"
            else:
                properties, reason = ("*",), "Reviewed source mapping"
        decisions.append(
            SourceEligibility(
                evidence_id=eid, eligible=bool(properties), properties=properties, reason=reason
            )
        )
    return IdentityEligibility(
        **base,
        status="eligible" if any(d.eligible for d in decisions) else "no_eligible_sources",
        sources=tuple(decisions),
        reason="Only explicitly approved, unchanged sources can contribute",
    )


def project_upload_manifest(evidence: list[EvidenceItem], project_id: str) -> IdentityManifest:
    """Caller explicitly associates uploads with its own opaque project, never retrieved sources."""
    decision = IdentityDecision(
        origin="publisher_declaration",
        reviewer="uploading-user",
        justification="User supplied these assets for this opaque project",
        decided_at=datetime.now(timezone.utc),
    )
    return IdentityManifest(
        evidence_version="upload-v1",
        raw_record_id=project_id,
        raw_label=project_id,
        record_kind="game_candidate",
        record_decision=decision,
        subject=SubjectIdentity(canonical_game_id=project_id, namespace="publisher_project"),
        sources=tuple(
            SourceIdentity(
                evidence_id=e.id,
                provider="user-upload",
                acquisition="upload",
                product_or_page_id=e.sha256 or content_hash(e),
                content_sha256=content_hash(e),
                acquired_at=decision.decided_at,
                relationship="verified_same_release",
                decision=decision,
            )
            for e in evidence
        ),
    )
