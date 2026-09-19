from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


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


class ImageRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_image(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Text region must be inside the image")
        return self


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: Literal["visual_fact", "visual_text", "metadata_quote"] = "visual_fact"
    metadata_key: str | None = None
    image_region: ImageRegion | None = None
    observer_model: str = Field(min_length=1)

    @model_validator(mode="after")
    def attributed_text(self):
        if self.kind == "visual_text":
            if self.image_region is None or self.metadata_key is not None:
                raise ValueError("Literal image text requires a region and no metadata key")
        elif self.image_region is not None:
            raise ValueError("Text regions belong only to literal image text")
        return self


class AnalysisRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    game_id: str
    game_title: str | None = None
    taxonomy_version: str = "4.1"
    observer_model: str | None = None
    decision_model: str | None = None
    prompt_version: str = "observer-v1"
    decision_prompt_version: str = "jev-genre-v4.1"
    requested_decision_model: str | None = None
    sdk_versions: dict[str, str] = Field(default_factory=dict)
    stage_latency_ms: dict[str, float] = Field(default_factory=dict)
    usage: dict[str, int | None] = Field(default_factory=dict)
    usage_by_stage: dict[str, dict[str, int | None]] = Field(default_factory=dict)
    observer_requests: list[dict[str, Any]] = Field(default_factory=list)
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
    support_links: list[dict[str, Any]] = Field(default_factory=list)
    publishable: bool = False


class GenreCandidate(BaseModel):
    genre_id: str
    probability: float


class GenreDecision(BaseModel):
    schema_version: Literal["4.1"] = "4.1"
    primary_genre: str | None
    secondary_genres: list[str] = Field(default_factory=list, max_length=2)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    family_probabilities: dict[str, float]
    family_choice: str
    family_confidence: float = Field(ge=0, le=1)
    conditional_genre_probabilities: dict[str, dict[str, float]]
    conditional_choices: dict[str, str]
    conditional_confidences: dict[str, float]
    global_genre_probabilities: dict[str, float]
    evaluated_families: list[str]
    family_model: str
    conditional_models: dict[str, str]
    decision_model: str
    action: PolicyAction | None = None
    support_links: list[dict[str, Any]] = Field(default_factory=list)
    publishable: bool = False

    @computed_field
    @property
    def global_genre_ranking(self) -> list[GenreCandidate]:
        return [
            GenreCandidate(genre_id=gid, probability=p)
            for gid, p in sorted(
                (
                    (g, p)
                    for g, p in self.global_genre_probabilities.items()
                    if g != "insufficient_evidence"
                ),
                key=lambda item: (-item[1], item[0]),
            )
        ]

    @model_validator(mode="after")
    def validate_hierarchy(self) -> GenreDecision:
        unknown = "insufficient_evidence"
        distributions = [
            self.family_probabilities,
            *self.conditional_genre_probabilities.values(),
            self.global_genre_probabilities,
        ]
        for probabilities in distributions:
            if (
                unknown not in probabilities
                or any(not math.isfinite(p) or not 0 <= p <= 1 for p in probabilities.values())
                or not math.isclose(sum(probabilities.values()), 1, abs_tol=0.001)
            ):
                raise ValueError("Genre distributions must be complete, finite, and normalized")
        families = set(self.family_probabilities) - {unknown}
        evaluated = set(self.evaluated_families)
        if len(evaluated) < 2 or len(evaluated) != len(self.evaluated_families):
            raise ValueError("Evaluate at least two distinct families")
        if not evaluated <= families or any(
            self.family_probabilities[f] > 0 for f in families - evaluated
        ):
            raise ValueError("Every positive-probability family must be evaluated")
        if any(
            set(mapping) != evaluated
            for mapping in (
                self.conditional_genre_probabilities,
                self.conditional_choices,
                self.conditional_confidences,
                self.conditional_models,
            )
        ):
            raise ValueError("Conditional metadata must match the evaluated families")
        choices = [(self.family_choice, self.family_probabilities)] + [
            (self.conditional_choices[f], self.conditional_genre_probabilities[f])
            for f in self.evaluated_families
        ]
        if any(c not in p or p[c] != max(p.values()) for c, p in choices):
            raise ValueError("Raw choices must match their distributions")
        if any(
            not math.isfinite(c) or not 0 <= c <= 1 for c in self.conditional_confidences.values()
        ):
            raise ValueError("Invalid conditional confidence")
        # Validate the published global distribution against the preserved source values.
        if not math.isclose(sum(self.global_genre_probabilities.values()), 1, abs_tol=1e-9):
            raise ValueError("Global genre probabilities must be normalized")
        family_total = sum(self.family_probabilities.values())
        joint = {g: 0.0 for g in self.global_genre_probabilities}
        joint[unknown] = self.family_probabilities[unknown] / family_total
        seen = set()
        for fid, probabilities in self.conditional_genre_probabilities.items():
            weight = self.family_probabilities[fid] / family_total
            total = sum(probabilities.values())
            for gid, probability in probabilities.items():
                if gid not in joint or (gid != unknown and gid in seen):
                    raise ValueError("Conditional genres must have unique global IDs")
                joint[gid] += weight * probability / total
                if gid != unknown:
                    seen.add(gid)
        if any(
            not math.isclose(self.global_genre_probabilities[g], p, abs_tol=1e-9)
            for g, p in joint.items()
        ):
            raise ValueError(
                "Global probabilities must equal family times conditional probabilities"
            )
        ranking = self.global_genre_ranking
        if not ranking:
            raise ValueError("A genre distribution requires eligible genres")
        winner = ranking[0]
        insufficient = self.global_genre_probabilities[unknown]
        expected = winner.genre_id if winner.probability > insufficient else None
        if self.primary_genre != expected:
            raise ValueError("Primary must be the highest-supported eligible genre or insufficient")
        if (
            len(set(self.secondary_genres)) != len(self.secondary_genres)
            or any(
                g == self.primary_genre
                or g == unknown
                or g not in self.global_genre_probabilities
                or self.global_genre_probabilities[g] < 0.1
                or self.global_genre_probabilities[g] <= insufficient
                for g in self.secondary_genres
            )
            or (self.primary_genre is None and self.secondary_genres)
        ):
            raise ValueError("Secondaries must be distinct supported alternatives to the primary")
        expected_confidence = self.global_genre_probabilities[self.primary_genre or unknown]
        if not math.isclose(self.confidence, expected_confidence, abs_tol=1e-9):
            raise ValueError("Genre confidence must equal the selected global probability")
        return self


class Review(BaseModel):
    analysis_run_id: UUID
    subject_id: str
    human_decision: str
    reviewer: str
    reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionError(BaseModel):
    code: str
    message: str


class QuestionExecution(BaseModel):
    status: Literal["valid", "error", "not_evaluated"]
    error: ExecutionError | None = None
    answer: dict[str, Any] | None = None
    model: str | None = None
    selected_attempt_id: str | None = None
    context_evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def execution_is_not_semantics(self):
        if self.status != "valid" and (self.answer is not None or self.selected_attempt_id):
            raise ValueError("Failed/not-evaluated questions cannot contain semantic answers")
        if self.status == "valid" and self.error is not None:
            raise ValueError("A valid question cannot contain an execution error")
        return self


class RequestAttempt(BaseModel):
    id: str
    stage: str
    ordinal: int
    question_ids: list[str]
    evidence_hash: str
    spec_hashes: dict[str, str]
    requested_model: str
    returned_model: str | None = None
    pinning: str
    sdk_version: str = "0.7.0"
    request_id_sha256: str | None = None
    started_at: datetime
    latency_ms: float
    usage: dict[str, int | None] | None = None
    error: ExecutionError | None = None
    question_errors: dict[str, ExecutionError] = Field(default_factory=dict)
    raw_answers: dict[str, Any] | None = None
    response_sha256: str | None = None
    response_representation: str = "sdk_parsed"


class DecisionBatch(BaseModel):
    tags: list[TagDecision]
    genre: GenreDecision | None
    model: str | None
    usage: dict[str, int | None] = Field(default_factory=dict)
    usage_by_stage: dict[str, dict[str, int | None]] = Field(default_factory=dict)
    execution_status: Literal["complete", "partial", "failed", "not_evaluated"] = "complete"
    genre_execution: QuestionExecution | None = None
    questions: dict[str, QuestionExecution] = Field(default_factory=dict)
    attempts: list[RequestAttempt] = Field(default_factory=list)
    evidence_policy: dict[str, Any] = Field(default_factory=dict)
    identity_status: str = "reference_only"
    retry_policy: str = "first-valid-v1; max_attempts=2; strict-total-tolerance=0.001"


class AnalysisResult(BaseModel):
    run: AnalysisRun
    evidence: list[EvidenceItem]
    observations: list[Observation]
    tags: list[TagDecision]
    genre: GenreDecision | None
    execution: DecisionBatch | None = None
    identity_audit: dict[str, Any] | None = None
