"""Make one live Jev call against a tiny blind-media fixture.

Usage:
    TYPESAFE_API_KEY=... python scripts/jev_smoke.py
"""
from __future__ import annotations

import json

from genometagger_v2.decisions.jev import JevDecisionEngine, TypeSafeGateway
from genometagger_v2.decisions.policy import DecisionPolicy
from genometagger_v2.domain import Observation
from genometagger_v2.taxonomy import load_taxonomy


def main() -> None:
    taxonomy = load_taxonomy()
    engine = JevDecisionEngine(taxonomy, TypeSafeGateway(model="jev-latest"))
    observations = [
        Observation(
            id="obs-1",
            evidence_id="clip-001",
            observer_model="manual-smoke-fixture",
            text=(
                "Gameplay is viewed from the player's eyes. A firearm is visible at the bottom "
                "of the screen. The player aims at an enemy and fires multiple shots."
            ),
        )
    ]
    tags, genre = engine.decide(
        game_id="blind-smoke-001",
        game_title=None,
        observations=observations,
        blind_media=True,
    )
    tags, genre = DecisionPolicy().apply(tags, genre)

    interesting = {
        d.tag_id: {
            "state": d.state.value,
            "probabilities": {k.value: v for k, v in d.probabilities.items()},
            "action": d.action.value if d.action else None,
        }
        for d in tags
        if d.tag_id in {"visual_first_person", "gameplay_shooter", "mechanic_ranged_combat"}
    }
    print(json.dumps({"tags": interesting, "genre": genre.model_dump(mode="json")}, indent=2))


if __name__ == "__main__":
    main()
