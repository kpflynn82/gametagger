from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from genometagger_v2.domain import GenreDecision, Observation, TagDecision


class DecisionEngine(ABC):
    @abstractmethod
    def decide(
        self,
        *,
        game_id: str,
        game_title: str | None,
        observations: list[Observation],
        metadata: dict[str, Any] | None = None,
    ) -> tuple[list[TagDecision], GenreDecision]:
        raise NotImplementedError
