from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from genometagger_v2.domain import GenreDecision, Observation, TagDecision, TagState
from genometagger_v2.taxonomy import Taxonomy


TAG_CRITERIA = {
    "present": (
        "The supplied evidence positively establishes that this feature exists in the game."
    ),
    "absent": (
        "The supplied evidence explicitly establishes that this feature is absent. "
        "Mere failure to observe the feature is NOT evidence of absence."
    ),
    "insufficient_evidence": (
        "The supplied evidence does not establish either presence or explicit absence."
    ),
    "conflicting_evidence": (
        "Credible supplied evidence materially disagrees about whether the feature exists."
    ),
}


@dataclass(frozen=True)
class QuestionSpec:
    type: str
    instructions: str
    criteria: dict[str, str]


class JevQuestionCompiler:
    """Compile the canonical taxonomy into TypeSafe question specifications."""

    def __init__(self, taxonomy: Taxonomy):
        self.taxonomy = taxonomy

    def build_specs(self) -> dict[str, QuestionSpec]:
        specs: dict[str, QuestionSpec] = {}
        for tag in self.taxonomy.tags:
            evidence_hint = ", ".join(tag.preferred_evidence) or "available evidence"
            instructions = (
                f"Classify whether the game has '{tag.label}'. Definition: {tag.definition} "
                f"Preferred evidence: {evidence_hint}. {tag.instructions} "
                "Judge ONLY from supplied evidence. Do not use outside knowledge."
            )
            specs[tag.id] = QuestionSpec(
                type="choice",
                instructions=instructions,
                criteria=TAG_CRITERIA,
            )

        specs["primary_genre"] = QuestionSpec(
            type="choice",
            instructions=(
                "Choose the primary genre best supported by the supplied evidence. "
                "Use insufficient_evidence when the evidence cannot support a reliable genre decision. "
                "Do not use outside knowledge about the title."
            ),
            criteria={
                **{genre: genre for genre in self.taxonomy.primary_genres},
                "insufficient_evidence": "The supplied evidence is insufficient for a reliable genre choice.",
            },
        )
        return specs

    @staticmethod
    def build_state(
        *,
        game_id: str,
        game_title: str | None,
        observations: list[Observation],
        metadata: dict[str, Any] | None = None,
        blind_media: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "game_id": game_id,
            "observations": [
                {"id": o.id, "evidence_id": o.evidence_id, "text": o.text}
                for o in observations
            ],
            "metadata": metadata or {},
        }
        if not blind_media:
            payload["game_title"] = game_title
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class TypeSafeGateway:
    """Thin adapter around the official TypeSafe Python SDK.

    Importing the SDK lazily keeps offline tests independent of credentials/network access.
    """

    def __init__(self, *, model: str = "jev-latest", client: Any | None = None):
        self.model = model
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from typesafe_sdk import TypeSafeClient
            except ImportError as exc:  # pragma: no cover - environment-specific
                raise RuntimeError(
                    "typesafe-sdk is not installed. Install project dependencies first."
                ) from exc
            self._client = TypeSafeClient()
        return self._client

    def run(self, *, state: str, specs: dict[str, QuestionSpec]) -> Any:
        from typesafe_sdk import Choice

        questions = {
            key: Choice(instructions=spec.instructions, criteria=spec.criteria)
            for key, spec in specs.items()
        }
        return self.client.system_one(state=state, model=self.model, questions=questions)


class JevDecisionEngine:
    def __init__(self, taxonomy: Taxonomy, gateway: TypeSafeGateway):
        self.taxonomy = taxonomy
        self.compiler = JevQuestionCompiler(taxonomy)
        self.gateway = gateway

    def decide(
        self,
        *,
        game_id: str,
        game_title: str | None,
        observations: list[Observation],
        metadata: dict[str, Any] | None = None,
        blind_media: bool = False,
    ) -> tuple[list[TagDecision], GenreDecision]:
        specs = self.compiler.build_specs()
        state = self.compiler.build_state(
            game_id=game_id,
            game_title=game_title,
            observations=observations,
            metadata=metadata,
            blind_media=blind_media,
        )
        response = self.gateway.run(state=state, specs=specs)

        decisions: list[TagDecision] = []
        for tag in self.taxonomy.tags:
            answer = response.answers[tag.id]
            probabilities = {
                TagState(key): float(value) for key, value in answer.probabilities.items()
            }
            decisions.append(
                TagDecision(
                    tag_id=tag.id,
                    state=TagState(answer.choice),
                    probabilities=probabilities,
                    evidence_ids=[o.evidence_id for o in observations],
                    decision_model=getattr(response, "model", self.gateway.model),
                )
            )

        genre_answer = response.answers["primary_genre"]
        genre_probs = {key: float(value) for key, value in genre_answer.probabilities.items()}
        chosen = genre_answer.choice
        genre = GenreDecision(
            primary_genre=None if chosen == "insufficient_evidence" else chosen,
            probabilities=genre_probs,
            decision_model=getattr(response, "model", self.gateway.model),
        )
        return decisions, genre
