from __future__ import annotations

from abc import ABC, abstractmethod

from genometagger_v2.domain import EvidenceItem, Observation


class Observer(ABC):
    @abstractmethod
    def observe(self, evidence: list[EvidenceItem]) -> list[Observation]:
        """Return factual observations only; do not assign VGMS tags or genre."""
        raise NotImplementedError
