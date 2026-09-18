from abc import ABC, abstractmethod

from gametagger.domain import EvidenceItem, Observation


class Observer(ABC):
    model: str
    prompt_version = "observer-v1"

    @abstractmethod
    def observe(self, evidence: EvidenceItem, *, image: bytes | None = None) -> list[Observation]:
        """Describe one evidence item; image bytes are the exact bytes hashed by the pipeline."""
        raise NotImplementedError
