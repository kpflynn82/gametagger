from gametagger.domain import EvidenceItem, Observation
from gametagger.observers.base import Observer


class MockObserver(Observer):
    """Return explicit fixture facts; never infer facts from an arbitrary image."""

    model = "mock-observer-v1"

    def __init__(self, facts: dict[str, list[str]] | None = None):
        self.facts = facts or {}

    def observe(self, evidence: EvidenceItem, *, image: bytes | None = None) -> list[Observation]:
        observations = [
            Observation(
                id=f"{evidence.id}:visual:{i}",
                evidence_id=evidence.id,
                text=text,
                observer_model=self.model,
                kind="visual_fact",
            )
            for i, text in enumerate(self.facts.get(evidence.id, []))
        ]
        for key, value in evidence.metadata.items():
            if isinstance(value, str) and value.strip():
                observations.append(
                    Observation(
                        id=f"{evidence.id}:metadata:{key}",
                        evidence_id=evidence.id,
                        text=value,
                        observer_model=self.model,
                        kind="metadata_quote",
                        metadata_key=key,
                    )
                )
        return observations
