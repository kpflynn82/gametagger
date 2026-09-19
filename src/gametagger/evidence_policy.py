"""Versioned evidence eligibility overlay; the canonical taxonomy stays frozen."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gametagger.domain import EvidenceItem, Observation
from gametagger.identity import IdentityManifest, content_hash, validate_identity

POLICY_VERSION = "evidence-policy-v1"
DOCUMENTED_RULES = {
    "engagement_co_op": r"\b(co[ -]?op(?:erative)?|cooperative multiplayer)\b",
    "feature_multiplayer": r"\bmultiplayer\b",
    "mechanic_parry": r"\bparr(?:y|ies|ying)\b",
}
NEGATION = re.compile(r"\b(no|not|without|cannot|unsupported|unavailable)\b", re.I)


class EvidenceProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    provider: str
    modality: Literal["image", "video", "text"]
    authority: Literal["official_publisher", "third_party", "user_upload", "unknown"] = "unknown"
    content_sha256: str
    authority_reviewer: str | None = None


class ClaimAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: str
    decision: str  # tag state or stable primary genre ID; never an automatic truth annotation
    observation_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    origin: Literal["human_review", "ai_suggestion"]
    reviewer: str | None = None
    reviewed_at: str | None = None


def attributed(claim, observations):
    o = next((o for o in observations if o.id == claim.observation_id), None)
    return bool(
        o
        and claim.origin == "human_review"
        and claim.reviewer
        and claim.reviewer.strip()
        and claim.reviewed_at
        and claim.start < claim.end <= len(o.text)
        and o.text[claim.start : claim.end] == claim.quote
        and o.kind != "visual_text"
    )


def evidence_eligibility(
    taxonomy,
    evidence: list[EvidenceItem],
    observations: list[Observation],
    identity: IdentityManifest | None,
    profiles=(),
    claims=(),
):
    gate = validate_identity(identity, evidence)
    by_id = {e.id: e for e in evidence}
    sources = {s.evidence_id: s for s in identity.sources} if identity else {}
    profile_map = {p.evidence_id: p for p in profiles}
    if len(profile_map) != len(profiles):
        raise ValueError("Duplicate evidence profiles")
    decisions = {}
    for prop in ["genre", *[t.id for t in taxonomy.tags]]:
        allowed = gate.evidence_for(prop)
        usable = []
        documented = []
        exceptions = []
        for o in observations:
            if o.evidence_id not in allowed:
                continue
            e = by_id[o.evidence_id]
            profile = profile_map.get(e.id)
            profile_valid = bool(profile and profile.content_sha256 == content_hash(e))
            if profile is not None and not profile_valid:
                continue
            # Claim modality comes from the observation, never from a store/provider name.
            if o.kind in {"visual_fact", "visual_text"}:
                modality = "image"
                evidence_type = e.type.value
            else:
                modality = "text"
                evidence_type = (
                    e.type.value
                    if e.type.value not in {"gameplay_image", "gameplay_clip"}
                    else "other"
                )
            if profile_valid and profile.modality != modality:
                continue
            if prop == "genre" or evidence_type in taxonomy.tags_by_id[prop].allowed_evidence:
                usable.append(o.id)
                if modality == "text":
                    documented.append(o.id)
                continue
            # Narrow documented exception: reviewed exact claims, verified official source/release.
            source = sources.get(e.id)
            if (
                prop in DOCUMENTED_RULES
                and evidence_type == "store_metadata"
                and profile_valid
                and profile.authority == "official_publisher"
                and profile.authority_reviewer
                and source
                and source.relationship in {"verified_same_release", "approved_alias_localization"}
                and source.release_id
                and identity.subject
                and source.release_id == identity.subject.release_id
            ):
                for c in claims:
                    if (
                        c.property_id == prop
                        and c.observation_id == o.id
                        and c.decision in {"present", "absent"}
                        and attributed(c, observations)
                        and re.search(DOCUMENTED_RULES[prop], c.quote, re.I)
                        and (c.decision == "absent") == bool(NEGATION.search(c.quote))
                    ):
                        usable.append(o.id)
                        documented.append(o.id)
                        exceptions.append(o.id)
                        break
        decisions[prop] = {
            "observation_ids": list(dict.fromkeys(usable)),
            "documented_observation_ids": list(dict.fromkeys(documented)),
            "documented_exception_observation_ids": list(dict.fromkeys(exceptions)),
            "status": "eligible" if usable else "not_evaluated",
            "reason": None
            if usable
            else ("identity_not_eligible" if not allowed else "no_eligible_evidence"),
            "policy_version": POLICY_VERSION,
        }
    return decisions


def support_links(property_id, decision, eligibility, observations, claims):
    permitted = set(eligibility[property_id]["observation_ids"])
    return [
        c.model_dump(mode="json")
        for c in claims
        if c.property_id == property_id
        and c.decision == decision
        and c.observation_id in permitted
        and attributed(c, observations)
    ]
