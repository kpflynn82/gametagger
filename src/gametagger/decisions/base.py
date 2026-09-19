from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from gametagger.domain import DecisionBatch, Observation


class DecisionEngine(ABC):
    @abstractmethod
    def decide(
        self,
        *,
        game_id: str,
        game_title: str | None,
        observations: list[Observation],
        metadata: dict[str, Any] | None = None,
    ) -> DecisionBatch:
        raise NotImplementedError
