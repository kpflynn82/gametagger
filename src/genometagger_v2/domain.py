from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EvidenceType(StrEnum):
    GAMEPLAY_IMAGE = "gameplay_image"
    GAMEPLAY_CLIP = "gameplay_clip"
    STORE_METADATA = "store_metadata"
    DEVELOPER_DOCUMENTATION = "developer_documentation"
    WIKIPEDIA = "wikipedia"
    TRANSCRIPT = "transcript"
    OTHER = "other"


class TagState(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    INSUFFICIENT = "insufficient_evidence"
    CONFLICTING = "conflicting_evidence"


class PolicyAction(StrEnum):
    ACCEPT = "accept"
    ACQUIRE_EVIDENCE = "acquire_evidence"
    DEEP_REVIEW = "deep_review"
    HUMAN_REVIEW = "human_review"


class EvidenceItem(BaseModel):
    id: str
    type: EvidenceType
    source: str
    uri: str | None = None
    sha256: str | None = None
    timestamp_start: float | None = None
    timestamp_end: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    id: str
    evidence_id: str
    text: str
    observer_model: str


class AnalysisRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    game_id: str
    game_title: str | None = None
    taxonomy_version: str = "4.0-pilot"
    observer_model: str | None = None
    decision_model: str | None = None
    prompt_version: str = "observer-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float | None = None
    estimated_cost_usd: float | None = None


class TagDecision(BaseModel):
    tag_id: str
    state: TagState
    probabilities: dict[TagState, float]
    evidence_ids: list[str] = Field(default_factory=list)
    decision_model: str
    action: PolicyAction | None = None


class GenreDecision(BaseModel):
    primary_genre: str | None
    probabilities: dict[str, float]
    decision_model: str
    action: PolicyAction | None = None


class Review(BaseModel):
    analysis_run_id: UUID
    subject_id: str
    human_decision: str
    reviewer: str
    reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
