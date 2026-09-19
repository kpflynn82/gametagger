"""Authenticated contract test; never replaced by a fixture when a key is present."""

import os

import pytest

from gametagger.decisions.jev import JevDecisionEngine, TypeSafeGateway
from gametagger.domain import Observation


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("GAMETAGGER_RUN_LIVE") != "1" or not os.environ.get("TYPESAFE_API_KEY"),
    reason="GAMETAGGER_RUN_LIVE=1 and TYPESAFE_API_KEY are required",
)
def test_live_jev_all_pilot_questions(taxonomy):
    batch = JevDecisionEngine(taxonomy, TypeSafeGateway(model="jev-latest")).decide(
        require_identity=False,
        game_id="live-contract-001",
        game_title=None,
        blind_media=True,
        observations=[
            Observation(
                id="obs-1",
                evidence_id="frame-1",
                observer_model="manual-fixture",
                text="A hand holds a metal firearm at the bottom of the image.",
            )
        ],
    )
    assert len(batch.tags) == 25
    assert len(batch.genre.global_genre_probabilities) == 101
    assert batch.model
    assert all(len(tag.probabilities) == 4 for tag in batch.tags)
    # No hard-coded semantic answer: this verifies live transport/schema, not model accuracy.
    print(f"Live model: {batch.model}; usage: {batch.usage}")
