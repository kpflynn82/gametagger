from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


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
    id: str = Field(min_length=1)
    type: EvidenceType
    source: str = Field(min_length=1)
    uri: str | None = None
    sha256: str | None = None
    media_type: str | None = None
    timestamp_start: float | None = None
    timestamp_end: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: Literal["visual_fact", "metadata_quote"] = "visual_fact"
    metadata_key: str | None = None
    observer_model: str = Field(min_length=1)


class AnalysisRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    game_id: str
    game_title: str | None = None
    taxonomy_version: str = "4.0-pilot"
    observer_model: str | None = None
    decision_model: str | None = None
    prompt_version: str = "observer-v1"
    decision_prompt_version: str = "jev-v1"
    requested_decision_model: str | None = None
    sdk_versions: dict[str, str] = Field(default_factory=dict)
    stage_latency_ms: dict[str, float] = Field(default_factory=dict)
    usage: dict[str, int | None] = Field(default_factory=dict)
    offline: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms: float | None = None
    estimated_cost_usd: float | None = None


class TagDecision(BaseModel):
    tag_id: str
    state: TagState
    confidence: float | None = None
    probabilities: dict[TagState, float]
    evidence_ids: list[str] = Field(default_factory=list)
    decision_model: str
    action: PolicyAction | None = None


class GenreDecision(BaseModel):
    primary_genre: str | None
    confidence: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)
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


class DecisionBatch(BaseModel):
    tags: list[TagDecision]
    genre: GenreDecision
    model: str
    usage: dict[str, int | None] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    run: AnalysisRun
    evidence: list[EvidenceItem]
    observations: list[Observation]
    tags: list[TagDecision]
    genre: GenreDecision
