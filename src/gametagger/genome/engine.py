"""Rich Genome mode: many compact Jev questions over one attributed dossier.

Flow: dossier text -> numbered claims; screenshots -> Observer facts (quarantined on taxonomy
words, never fatal) -> per-tag evidence filtering -> four-state Jev Choice for every tag plus the
v4.1 genre hierarchy -> deterministic policy -> GenomeProfile. Reuses QuestionExecutor for strict
validation, bounded retries and attempt records, and JevDecisionEngine for genre aggregation.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, get_args

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from gametagger.decisions.execution import QuestionExecutor
from gametagger.decisions.jev import JevDecisionEngine, QuestionSpec
from gametagger.decisions.policy import DecisionPolicy
from gametagger.domain import (
    EvidenceItem,
    EvidenceType,
    ExecutionError,
    GenreDecision,
    PolicyAction,
    QuestionExecution,
    RequestAttempt,
    TagDecision,
    TagState,
)
from gametagger.evidence import prepare_evidence
from gametagger.genome.dossier import (
    Claim,
    Dossier,
    Reference,
    build_state,
    claims_from_observations,
    claims_from_source,
    source_evidence,
)
from gametagger.genome.media import (
    WINDOW_STRATEGY,
    burst_claims,
    ffmpeg_available,
    frame_bursts,
)
from gametagger.genome.vocabulary import (
    EVIDENCE_POLICY_VERSION,
    GenomeVocabulary,
    rich_allowed_evidence,
)
from gametagger.observers.base import Observer
from gametagger.observers.boundary import ObservationBoundary
from gametagger.taxonomy import TagDefinition, Taxonomy

PROMPT_VERSION = "genome-rich-v1"
GENRE_QUESTION = "genre_family"

RICH_TAG_CRITERIA = {
    "present": "Sources support it: a documented claim or an observed fact.",
    "absent": "A source explicitly rules it out. Unmentioned or unseen is never absent.",
    "insufficient_evidence": "Sources neither support it nor explicitly rule it out.",
    "conflicting_evidence": "Credible sources materially disagree about it.",
}

Tier = Literal["strong", "likely", "absent", "conflicting", "unknown", "not_evaluated", "error"]


def tag_spec(tag: TagDefinition, category_label: str) -> QuestionSpec:
    note = f" Note: {tag.instructions}" if tag.instructions else ""
    return QuestionSpec(
        type="choice",
        instructions=(
            f"Does the game have this {category_label.lower()} attribute? "
            f"{tag.label}: {tag.definition}{note} Use only the supplied sources."
        ),
        criteria=RICH_TAG_CRITERIA,
    )


@dataclass(frozen=True)
class TierThresholds:
    """Display bands over raw Jev probabilities. Uncalibrated; they are not accuracy."""

    strong_present: float = 0.85


def tier_for(state: TagState, probabilities: dict[str, float], t: TierThresholds) -> Tier:
    if state is TagState.PRESENT:
        return "strong" if probabilities["present"] >= t.strong_present else "likely"
    return {
        TagState.ABSENT: "absent",
        TagState.CONFLICTING: "conflicting",
        TagState.INSUFFICIENT: "unknown",
    }[state]


class TagCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag_id: str
    label: str
    category: str
    pilot: bool
    tier: Tier
    state: TagState | None = None
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    action: PolicyAction | None = None
    publishable: bool = False
    allowed_evidence: list[str]
    context_evidence_ids: list[str] = Field(default_factory=list)
    error: ExecutionError | None = None


class GenreCall(BaseModel):
    genre_id: str
    name: str
    probability: float


class GenomeProfile(BaseModel):
    schema_version: Literal["genome-profile-v1"] = "genome-profile-v1"
    game_id: str
    title: str | None
    offline: bool
    status: Literal["complete", "partial", "failed", "not_evaluated"]
    primary_genre: GenreCall | None
    secondary_genres: list[GenreCall]
    genre: GenreDecision | None
    genre_execution: QuestionExecution
    tags: list[TagCall]
    counts: dict[str, int]
    sources: list[EvidenceItem]
    claims: list[Claim]
    claims_dropped: dict[str, int]
    quarantined_observations: list[dict[str, str]]
    media: list[dict[str, Any]] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    warnings: list[str]
    provenance: dict[str, Any]
    attempts: list[RequestAttempt]


@dataclass
class GenomePlan:
    """Exactly what would be sent to Jev; built without any network call."""

    specs: dict[str, QuestionSpec]
    states: dict[str, str]
    contexts: dict[str, list[str]]
    batches: list[list[str]]
    skipped: dict[str, str] = field(default_factory=dict)

    def estimate(self, genre_branch_chars: int = 0) -> dict[str, Any]:
        """Rough input-token estimate (characters / 4); excludes retries and screenshots."""
        requests = []
        for batch in self.batches:
            chars = len(self.states[batch[0]]) + sum(
                len(key) + len(json.dumps(vars(self.specs[key]))) for key in batch
            )
            requests.append({"questions": len(batch), "approx_input_tokens": chars // 4})
        if GENRE_QUESTION in self.specs and genre_branch_chars:
            chars = len(self.states[GENRE_QUESTION]) + genre_branch_chars
            requests.append({"questions": "genre branches", "approx_input_tokens": chars // 4})
        return {
            "method": "characters/4 heuristic; excludes retries and screenshot observation",
            "requests": requests,
            "approx_input_tokens_total": sum(r["approx_input_tokens"] for r in requests),
        }


class GenomeEngine:
    def __init__(
        self,
        taxonomy: Taxonomy,
        vocabulary: GenomeVocabulary,
        gateway,
        *,
        categories: list[str] | None = None,
        max_attempts: int = 2,
        max_questions_per_request: int = 60,
        thresholds: TierThresholds | None = None,
    ):
        if max_questions_per_request < 1:
            raise ValueError("max_questions_per_request must be positive")
        self.taxonomy = taxonomy
        self.vocabulary = vocabulary
        self.jev = JevDecisionEngine(taxonomy, gateway)
        self.tags = vocabulary.select(categories)
        self.max_attempts = max_attempts
        self.max_questions = max_questions_per_request
        self.thresholds = thresholds or TierThresholds()

    @property
    def gateway(self):
        return self.jev.gateway

    def plan(self, claims: list[Claim], evidence: list[EvidenceItem]) -> GenomePlan:
        specs, states, contexts, skipped = {}, {}, {}, {}
        labels = {c.id: c.label for c in self.vocabulary.categories}

        def add(key: str, spec: QuestionSpec, allowed: set[str]) -> None:
            state = build_state(claims, evidence, allowed)
            if state is None:
                skipped[key] = "no_eligible_evidence"
                return
            specs[key], states[key] = spec, state
            contexts[key] = sorted({c.evidence_id for c in claims if c.evidence_type in allowed})

        add(
            GENRE_QUESTION,
            self.jev.compiler.build_specs()[GENRE_QUESTION],
            {e.type.value for e in evidence},
        )
        for tag in self.tags:
            allowed = set(rich_allowed_evidence(tag, self.vocabulary))
            add(tag.id, tag_spec(tag, labels[tag.category]), allowed)
        groups: dict[str, list[str]] = {}
        for key in specs:
            groups.setdefault(states[key], []).append(key)
        batches = [
            keys[i : i + self.max_questions]
            for keys in groups.values()
            for i in range(0, len(keys), self.max_questions)
        ]
        return GenomePlan(specs, states, contexts, batches, skipped)

    def genre_branch_chars(self, branches: int = 3) -> int:
        """Average size of a few conditional genre questions, for the estimate only."""
        specs = self.jev.compiler.build_genre_specs([f.id for f in self.taxonomy.genre_families])
        sizes = [len(k) + len(json.dumps(vars(s))) for k, s in specs.items()]
        return branches * sum(sizes) // len(sizes)

    def run(self, plan: GenomePlan):
        executor = QuestionExecutor(self.gateway, max_attempts=self.max_attempts)
        outcomes: dict[str, QuestionExecution] = {}
        for batch in plan.batches:
            outcomes.update(
                executor.execute(
                    {k: plan.specs[k] for k in batch},
                    plan.states,
                    stage="genome_tags",
                    evidence_ids=plan.contexts,
                )
            )
        for key, reason in plan.skipped.items():
            outcomes[key] = QuestionExecution(
                status="not_evaluated",
                error=ExecutionError(
                    code=reason, message="No source of an allowed evidence type; not asked"
                ),
            )
        genre, genre_execution = self.jev.resolve_genre(
            executor,
            outcomes,
            state=plan.states.get(GENRE_QUESTION),
            context_ids=plan.contexts.get(GENRE_QUESTION, []),
        )
        return outcomes, genre, genre_execution, executor

    def tag_calls(self, outcomes, genre):
        decisions, calls = [], []
        pilot = {t.id for t in self.vocabulary.pilot_tags}
        for tag in self.tags:
            outcome = outcomes[tag.id]
            base = dict(
                tag_id=tag.id,
                label=tag.label,
                category=tag.category,
                pilot=tag.id in pilot,
                allowed_evidence=list(rich_allowed_evidence(tag, self.vocabulary)),
                context_evidence_ids=outcome.context_evidence_ids,
            )
            if outcome.status != "valid":
                tier = "not_evaluated" if outcome.status == "not_evaluated" else "error"
                calls.append(TagCall(**base, tier=tier, error=outcome.error))
                continue
            answer = outcome.answer
            decisions.append(
                TagDecision(
                    tag_id=tag.id,
                    state=TagState(answer["choice"]),
                    probabilities=answer["probabilities"],
                    confidence=answer["confidence"],
                    evidence_ids=outcome.context_evidence_ids,
                    decision_model=outcome.model or "unknown",
                )
            )
            calls.append(base)
        routed, genre = DecisionPolicy().apply(decisions, genre)
        by_id = {d.tag_id: d for d in routed}
        result = []
        for call in calls:
            if isinstance(call, TagCall):
                result.append(call)
                continue
            d = by_id[call["tag_id"]]
            probabilities = {str(k): v for k, v in d.probabilities.items()}
            result.append(
                TagCall(
                    **call,
                    tier=tier_for(d.state, probabilities, self.thresholds),
                    state=d.state,
                    probabilities=probabilities,
                    confidence=d.confidence,
                    action=d.action,
                    publishable=d.publishable,
                )
            )
        return result, genre


def _normal_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _image_tokens(width: int, height: int) -> int:
    # Anthropic's documented approximation for image input: (width x height) / 750.
    return max(1, width * height // 750)


@dataclass
class Prepared:
    """Evidence and claims for one dossier, plus what the Observer did or would do."""

    evidence: list[EvidenceItem] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)
    quarantined: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    observer_requests: list[dict[str, Any]] = field(default_factory=list)
    media: list[dict[str, Any]] = field(default_factory=list)
    observer_image_sizes: list[tuple[int, int]] = field(default_factory=list)
    observer_calls: int = 0

    def observer_estimate(self) -> dict[str, Any]:
        """Rough Claude vision input tokens for describing every screenshot and burst."""
        image = sum(_image_tokens(w, h) for w, h in self.observer_image_sizes)
        overhead = 900 * self.observer_calls  # instructions, schema and labels per request
        return {
            "method": "(width x height) / 750 per image plus about 900 tokens per request",
            "requests": self.observer_calls,
            "images": len(self.observer_image_sizes),
            "approx_input_tokens_total": image + overhead,
        }


class GenomePipeline:
    def __init__(
        self,
        engine: GenomeEngine,
        observer: Observer | None = None,
        ordered_observer=None,
        *,
        bursts: int = 6,
        frames_per_burst: int = 6,
    ):
        self.engine = engine
        self.observer = observer
        self.ordered_observer = ordered_observer
        self.bursts = bursts
        self.frames_per_burst = frames_per_burst
        self.boundary = ObservationBoundary(engine.taxonomy)

    def prepare(self, dossier: Dossier, *, observe: bool = True) -> Prepared:
        """Build evidence and claims. The Observer is called only when ``observe`` is set."""
        p = Prepared(warnings=list(dossier.notes))
        for source in dossier.sources:
            kept, p.dropped[source.id] = claims_from_source(source)
            p.evidence.append(source_evidence(source))
            p.claims.extend(kept)
            if dossier.title and source.reported_title:
                a, b = _normal_title(dossier.title), _normal_title(source.reported_title)
                if a and b and a not in b and b not in a:
                    p.warnings.append(
                        f"Source '{source.id}' reports title '{source.reported_title}', not "
                        f"'{dossier.title}'. Check it is the same game before trusting results."
                    )
        for image in dossier.images:
            self._image(image, p, observe)
        if dossier.videos:
            with tempfile.TemporaryDirectory(prefix="gametagger-frames-") as frames:
                for video in dossier.videos:
                    self._video(video, Path(frames), p, observe)
        return p

    def _image(self, image, p: Prepared, observe: bool) -> None:
        item, data = prepare_evidence(
            EvidenceItem(
                id=image.id,
                type=EvidenceType.GAMEPLAY_IMAGE,
                source=image.provider,
                uri=image.path,
                sha256=image.sha256,
            )
        )
        p.evidence.append(item)
        with Image.open(io.BytesIO(data)) as decoded:
            p.observer_image_sizes.append(decoded.size)
        p.observer_calls += 1
        summary = {
            "id": image.id,
            "kind": "image",
            "role": image.role,
            "provider": image.provider,
            "uri": image.uri,
            "observed": False,
            "claims": 0,
        }
        p.media.append(summary)
        if not observe or self.observer is None:
            p.warnings.append(f"Screenshot '{image.id}' was not observed in this run.")
            return
        start = perf_counter()
        try:
            observed = self.observer.observe(item, image=data)
        except ValueError as exc:
            # A malformed answer for one screenshot loses that screenshot, not the game; the
            # request is still metered. Provider errors are not ValueErrors and still propagate.
            p.warnings.append(
                f"Screenshot '{image.id}': the Observer's answer broke the contract and was "
                f"not used ({type(exc).__name__})."
            )
            p.observer_requests.append(
                {
                    "evidence_id": item.id,
                    "latency_ms": (perf_counter() - start) * 1000,
                    "requested_model": self.observer.model,
                    "usage": getattr(self.observer, "last_usage", None),
                    "error": type(exc).__name__,
                }
            )
            return
        malformed = getattr(self.observer, "last_quarantined", None) or []
        p.quarantined.extend({"evidence_id": item.id, **r} for r in malformed)
        kept, rejected = self.boundary.partition(observed, item)
        p.quarantined.extend({"evidence_id": item.id, **r} for r in rejected)
        new = claims_from_observations(kept, item)
        p.claims.extend(new)
        summary.update(observed=True, claims=len(new))
        p.observer_requests.append(
            {
                "evidence_id": item.id,
                "latency_ms": (perf_counter() - start) * 1000,
                "requested_model": self.observer.model,
                "usage": getattr(self.observer, "last_usage", None),
            }
        )

    def _video(self, video, frames_dir: Path, p: Prepared, observe: bool) -> None:
        summary = {
            "id": video.id,
            "kind": "video",
            "role": video.role,
            "provider": video.provider,
            "title": video.title,
            "uri": video.uri,
            "bursts": 0,
            "frames": 0,
            "observed": False,
            "contexts": {},
            "excluded_statements": 0,
            "errors": 0,
            "claims": 0,
        }
        p.media.append(summary)
        if not ffmpeg_available():
            p.warnings.append(f"Video '{video.id}' skipped: install ffmpeg to sample trailers.")
            return
        try:
            bursts = frame_bursts(
                video, frames_dir, windows=self.bursts, frames=self.frames_per_burst
            )
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            p.warnings.append(f"Video '{video.id}' could not be sampled: {exc}")
            return
        if not bursts:
            p.warnings.append(f"Video '{video.id}' produced no usable frame bursts.")
            return
        p.evidence.append(
            EvidenceItem(
                id=video.id,
                type=EvidenceType.GAMEPLAY_CLIP,
                source=video.provider,
                uri=video.path,
                sha256=bursts[0][0].source_asset_sha256,
            )
        )
        summary.update(bursts=len(bursts), frames=sum(len(w.frames) for w, _ in bursts))
        for _, frames in bursts:
            for data in frames:
                with Image.open(io.BytesIO(data)) as decoded:
                    p.observer_image_sizes.append(decoded.size)
        p.observer_calls += len(bursts)
        if not observe or self.ordered_observer is None:
            p.warnings.append(f"Video '{video.id}' was sampled but not observed in this run.")
            return
        summary["observed"] = True
        for index, (window, frames) in enumerate(bursts):
            attempt = self.ordered_observer.observe_window(window, frames=frames)
            malformed = getattr(self.ordered_observer, "last_quarantined", None) or []
            p.quarantined.extend(
                {"evidence_id": f"{video.id}:burst:{index}", **r} for r in malformed
            )
            p.observer_requests.append(
                {
                    "evidence_id": video.id,
                    "burst": index,
                    "status": attempt.status,
                    "error_code": attempt.error_code,
                    "requested_model": attempt.requested_model,
                    "returned_model": attempt.returned_model,
                    "latency_ms": attempt.latency_ms,
                    "usage": attempt.usage,
                }
            )
            if attempt.status != "valid":
                summary["errors"] += 1
                continue
            context = attempt.output.context
            summary["contexts"][context] = summary["contexts"].get(context, 0) + 1
            new, rejected, excluded = burst_claims(
                video.id, index, window, attempt.output, self.boundary
            )
            p.claims.extend(new)
            p.quarantined.extend(rejected)
            summary["claims"] += len(new)
            summary["excluded_statements"] += excluded

    def analyze(self, dossier: Dossier, *, offline: bool) -> GenomeProfile:
        start = perf_counter()
        p = self.prepare(dossier)
        observed_at = perf_counter()
        plan = self.engine.plan(p.claims, p.evidence)
        outcomes, genre, genre_execution, executor = self.engine.run(plan)
        decided_at = perf_counter()
        tags, genre = self.engine.tag_calls(outcomes, genre)
        counts = {tier: 0 for tier in get_args(Tier)}
        for tag in tags:
            counts[tag.tier] += 1
        asked = [k for k in plan.specs] + [k for k in outcomes if k.startswith("genre:")]
        valid = sum(outcomes[k].status == "valid" for k in asked)
        status = (
            "complete"
            if asked and valid == len(asked) and genre is not None
            else "partial"
            if valid
            else "failed"
            if executor.attempts
            else "not_evaluated"
        )
        names = {g.id: g.display_name for g in self.engine.taxonomy.genres_by_id.values()}

        def call(genre_id: str) -> GenreCall:
            probability = genre.global_genre_probabilities[genre_id]
            return GenreCall(genre_id=genre_id, name=names[genre_id], probability=probability)

        returned = executor.pinned_model or next(
            (a.returned_model for a in reversed(executor.attempts) if a.returned_model), None
        )
        return GenomeProfile(
            game_id=dossier.game_id,
            title=dossier.title,
            offline=offline,
            status=status,
            primary_genre=call(genre.primary_genre) if genre and genre.primary_genre else None,
            secondary_genres=[call(g) for g in genre.secondary_genres] if genre else [],
            genre=genre,
            genre_execution=genre_execution,
            tags=tags,
            counts=counts,
            sources=p.evidence,
            claims=p.claims,
            claims_dropped=p.dropped,
            quarantined_observations=p.quarantined,
            media=p.media,
            references=dossier.references,
            warnings=p.warnings,
            provenance={
                "prompt_version": PROMPT_VERSION,
                "evidence_policy_version": EVIDENCE_POLICY_VERSION,
                "vocabulary_version": self.engine.vocabulary.version,
                "taxonomy_version": self.engine.taxonomy.version,
                "tier_thresholds": vars(self.engine.thresholds),
                "requested_decision_model": self.engine.gateway.model,
                "returned_decision_model": returned,
                "observer_model": getattr(self.observer, "model", None),
                "ordered_observer_model": getattr(self.ordered_observer, "model", None),
                "burst_strategy": WINDOW_STRATEGY if dossier.videos else None,
                "observer_requests": p.observer_requests,
                "questions_asked": len(asked),
                "requests": len(executor.attempts),
                "usage": executor.usage_total(),
                "latency_ms": {
                    "observe": (observed_at - start) * 1000,
                    "decide": (decided_at - observed_at) * 1000,
                    "total": (perf_counter() - start) * 1000,
                },
            },
            attempts=executor.attempts,
        )
