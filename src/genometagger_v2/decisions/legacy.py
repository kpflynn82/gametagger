"""Legacy adapter placeholder.

PR 3 will wrap the frozen v1 classifier so the evaluation harness can compare
legacy_v1 against observer->Jev using identical benchmark cases.
"""

from typing import Any

from genometagger_v2.decisions.base import DecisionEngine
from genometagger_v2.domain import GenreDecision, Observation, TagDecision


class LegacyDecisionEngine(DecisionEngine):
    def decide(
        self,
        *,
        game_id: str,
        game_title: str | None,
        observations: list[Observation],
        metadata: dict[str, Any] | None = None,
    ) -> tuple[list[TagDecision], GenreDecision]:
        raise NotImplementedError("Legacy v1 adapter lands in PR 3; do not reimplement it here.")
