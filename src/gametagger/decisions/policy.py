from __future__ import annotations

from dataclasses import dataclass

from gametagger.domain import GenreDecision, PolicyAction, TagDecision, TagState


@dataclass(frozen=True)
class TagThresholds:
    accept_present: float = 0.95
    accept_absent: float = 0.98
    acquire_if_insufficient: float = 0.35
    review_if_conflicting: float = 0.20


@dataclass(frozen=True)
class GenreThresholds:
    accept_top_probability: float = 0.70
    accept_margin: float = 0.15
    acquire_if_insufficient: float = 0.30


class DecisionPolicy:
    """Operational policy. Thresholds are hypotheses until benchmark calibration."""

    def __init__(
        self,
        tag_thresholds: TagThresholds | None = None,
        genre_thresholds: GenreThresholds | None = None,
    ):
        self.tag_thresholds = tag_thresholds or TagThresholds()
        self.genre_thresholds = genre_thresholds or GenreThresholds()

    def route_tag(self, decision: TagDecision) -> PolicyAction:
        p = decision.probabilities
        t = self.tag_thresholds

        if p.get(TagState.CONFLICTING, 0.0) >= t.review_if_conflicting:
            return PolicyAction.HUMAN_REVIEW
        if p.get(TagState.INSUFFICIENT, 0.0) >= t.acquire_if_insufficient:
            return PolicyAction.ACQUIRE_EVIDENCE
        if decision.state is TagState.PRESENT and p.get(TagState.PRESENT, 0.0) >= t.accept_present:
            return PolicyAction.ACCEPT
        if decision.state is TagState.ABSENT and p.get(TagState.ABSENT, 0.0) >= t.accept_absent:
            return PolicyAction.ACCEPT
        return PolicyAction.DEEP_REVIEW

    def route_genre(self, decision: GenreDecision) -> PolicyAction:
        t = self.genre_thresholds
        insufficient = decision.global_genre_probabilities.get("insufficient_evidence", 0.0)
        if decision.primary_genre is None or insufficient >= t.acquire_if_insufficient:
            return PolicyAction.ACQUIRE_EVIDENCE

        candidates = sorted(
            (
                (g, p)
                for g, p in decision.global_genre_probabilities.items()
                if g != "insufficient_evidence"
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        if not candidates:
            return PolicyAction.ACQUIRE_EVIDENCE

        top_prob = candidates[0][1]
        runner_up = candidates[1][1] if len(candidates) > 1 else 0.0
        if top_prob >= t.accept_top_probability and (top_prob - runner_up) >= t.accept_margin:
            return PolicyAction.ACCEPT
        return PolicyAction.HUMAN_REVIEW

    def apply(
        self, tags: list[TagDecision], genre: GenreDecision
    ) -> tuple[list[TagDecision], GenreDecision]:
        routed_tags = [d.model_copy(update={"action": self.route_tag(d)}) for d in tags]
        routed_genre = genre.model_copy(update={"action": self.route_genre(genre)})
        return routed_tags, routed_genre
