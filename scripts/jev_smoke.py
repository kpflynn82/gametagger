"""Run all pilot questions through the live SDK and print the complete decision batch."""

import os
from time import perf_counter

from gametagger.decisions.jev import JevDecisionEngine, TypeSafeGateway
from gametagger.decisions.policy import DecisionPolicy
from gametagger.domain import EvidenceItem, EvidenceType, Observation
from gametagger.taxonomy import load_taxonomy


def main() -> None:
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is not set; live Jev smoke test cannot run.")
    taxonomy = load_taxonomy()
    engine = JevDecisionEngine(taxonomy, TypeSafeGateway(model="jev-latest"))
    start = perf_counter()
    batch = engine.decide(
        require_identity=False,
        game_id="blind-smoke-001",
        game_title=None,
        blind_media=True,
        evidence=[
            EvidenceItem(
                id="clip-001", type=EvidenceType.GAMEPLAY_CLIP, source="manual-smoke-fixture"
            )
        ],
        observations=[
            Observation(
                id="obs-1",
                evidence_id="clip-001",
                observer_model="manual-smoke-fixture",
                text=(
                    "Gameplay is viewed from the player's eyes. A firearm is visible at the bottom "
                    "of the screen. The player aims at an enemy and fires multiple shots."
                ),
            )
        ],
    )
    batch.tags, batch.genre = DecisionPolicy().apply(batch.tags, batch.genre)
    import json

    print(
        json.dumps(
            {"latency_ms": (perf_counter() - start) * 1000, **batch.model_dump(mode="json")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
