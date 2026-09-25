"""Conservative lexical guard, not a semantic proof of factuality.

Metadata claims must be exact attributed quotes, never promoted to visual facts.
All observer providers, including injected ones, pass through this guard.
"""

import re

from gametagger.domain import EvidenceItem, Observation
from gametagger.taxonomy import Taxonomy


class ObserverBoundaryError(ValueError):
    pass


def normalized(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.casefold()).strip()


class ObservationBoundary:
    def __init__(self, taxonomy: Taxonomy):
        self.terms = {
            normalized(term)
            for term in [
                *taxonomy.primary_genres,
                *(t.id for t in taxonomy.tags),
                *(t.label for t in taxonomy.tags),
                "parry",
                "parrying",
                "parries",
                "genre",
                "mechanic",
                "mechanics",
                "genome tag",
                "rpg",
                "fps",
                "roguelite",
                "soulslike",
                "co-op",
            ]
        }

    def partition(
        self, observations: list[Observation], evidence: EvidenceItem
    ) -> tuple[list[Observation], list[dict[str, str]]]:
        """Apply the same rules per observation, quarantining violations instead of failing.

        Used by rich mode so one taxonomy word in a description cannot erase every other fact
        from that image. Quarantined statements are returned for audit and never reach Jev.
        """
        kept, quarantined, seen = [], [], set()
        for observation in observations:
            try:
                if observation.id in seen:
                    raise ObserverBoundaryError("Duplicate observation IDs")
                self.validate([observation], evidence)
            except ObserverBoundaryError as exc:
                quarantined.append(
                    {"observation_id": observation.id, "text": observation.text, "reason": str(exc)}
                )
            else:
                kept.append(observation)
            seen.add(observation.id)
        return kept, quarantined

    def validate(self, observations: list[Observation], evidence: EvidenceItem) -> None:
        ids = [o.id for o in observations]
        if len(ids) != len(set(ids)):
            raise ObserverBoundaryError("Duplicate observation IDs")
        for observation in observations:
            if observation.evidence_id != evidence.id:
                raise ObserverBoundaryError("Observation references an unknown evidence ID")
            if observation.kind == "metadata_quote":
                source = evidence.metadata.get(observation.metadata_key)
                if not isinstance(source, str) or observation.text not in source:
                    raise ObserverBoundaryError(
                        "Metadata observations must quote their source exactly"
                    )
            else:
                if observation.metadata_key is not None:
                    raise ObserverBoundaryError("Visual facts cannot claim metadata provenance")
                if evidence.type.value != "gameplay_image":
                    raise ObserverBoundaryError("Visual facts require image evidence")
                if observation.kind == "visual_text":
                    if observation.image_region is None:
                        raise ObserverBoundaryError(
                            "Literal text requires image-region attribution"
                        )
                    # This is an attributed transcription, never a gameplay/genre assertion.
                    continue
                text = f" {normalized(observation.text)} "
                if any(f" {term} " in text for term in self.terms):
                    raise ObserverBoundaryError("Observer emitted a taxonomy conclusion")
