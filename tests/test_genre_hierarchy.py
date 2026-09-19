import json
import math
from dataclasses import replace

import pytest
from genre_helpers import classify
from pydantic import ValidationError

from gametagger.decisions.jev import JevQuestionCompiler
from gametagger.decisions.policy import DecisionPolicy
from gametagger.domain import GenreDecision, PolicyAction


@pytest.mark.parametrize(
    "title,family,genre",
    [
        ("Fortnite", "action", "battle_royale"),
        ("Destiny 2", "action", "looter_shooter"),
        ("Hades", "role_playing", "roguelite"),
        ("Hollow Knight", "action", "metroidvania"),
        ("Slay the Spire", "card_tabletop", "deck_builder"),
        ("RimWorld", "simulation_management", "colony_sim"),
        ("Factorio", "simulation_management", "factory_automation_sim"),
        ("Vampire Survivors", "action", "survivor_like"),
        ("Pokémon", "role_playing", "creature_collector"),
        ("Among Us", "party_social", "social_deduction"),
        ("Candy Crush", "puzzle", "match_3"),
        ("Mobile merge title", "puzzle", "merge"),
    ],
)
def test_requested_genre_paths(title, family, genre, taxonomy):
    definition = taxonomy.genres_by_id[genre]
    assert definition.family == family and definition.primary_eligible
    other = "role_playing" if family == "action" else "action"
    batch, gateway = classify(
        taxonomy,
        {family: 0.8, other: 0.15, "insufficient_evidence": 0.05},
        {family: {genre: 0.9, "insufficient_evidence": 0.1}},
    )
    result = batch.genre
    assert result.primary_genre == genre, title
    assert result.global_genre_probabilities[genre] == pytest.approx(0.72)
    assert len(result.evaluated_families) == 2
    assert result.family_model == "fixture-stage-1"
    assert result.conditional_models[family] == "fixture-stage-2"
    assert batch.usage == {"input_tokens": 200, "output_tokens": 100}
    assert title not in gateway.calls[0][0]  # Names are test labels, not classifier inputs.
    assert GenreDecision.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("winner", ["action_rpg", "souls_like"])
def test_elden_ring_survives_second_family_branch(taxonomy, winner):
    batch, gateway = classify(
        taxonomy,
        {"action": 0.51, "role_playing": 0.49},
        {
            "action": {
                "action_adventure": 0.4,
                "character_action": 0.3,
                "insufficient_evidence": 0.3,
            },
            "role_playing": {winner: 0.9, "insufficient_evidence": 0.1},
        },
    )
    result = batch.genre
    assert set(gateway.calls[1][1]) == {"genre:action", "genre:role_playing"}
    assert result.primary_genre == winner
    assert result.global_genre_probabilities[winner] == pytest.approx(0.49 * 0.9)
    assert result.global_genre_probabilities["action_adventure"] == pytest.approx(0.51 * 0.4)
    assert result.secondary_genres == ["action_adventure"]
    assert result.primary_genre != "action_adventure"
    assert math.isclose(sum(result.global_genre_probabilities.values()), 1.0)


def test_third_positive_branch_can_win(taxonomy):
    batch, _ = classify(
        taxonomy,
        {"action": 0.4, "role_playing": 0.35, "puzzle": 0.25},
        {
            "action": {
                "action_adventure": 0.25,
                "character_action": 0.25,
                "first_person_shooter": 0.25,
                "third_person_shooter": 0.25,
            },
            "role_playing": {"action_rpg": 0.25, "souls_like": 0.25, "jrpg": 0.25, "crpg": 0.25},
            "puzzle": {"merge": 1.0},
        },
    )
    assert len(batch.genre.evaluated_families) == 3
    assert batch.genre.primary_genre == "merge"
    assert batch.genre.global_genre_probabilities["merge"] == pytest.approx(0.25)
    assert len(batch.genre.secondary_genres) == 2
    # Review thresholds do not erase the single store-facing primary.
    assert DecisionPolicy().route_genre(batch.genre) == PolicyAction.HUMAN_REVIEW


@pytest.mark.parametrize(
    "family,conditional",
    [
        ({"insufficient_evidence": 1.0}, {}),
        ({"action": 0.6, "role_playing": 0.4}, {}),
        ({"action": 0.5, "insufficient_evidence": 0.5}, {"action": {"battle_royale": 1.0}}),
    ],
)
def test_unknown_or_tied_evidence_never_forces_fallback(taxonomy, family, conditional):
    batch, gateway = classify(taxonomy, family, conditional)
    assert len(gateway.calls[1][1]) >= 2
    assert batch.genre.primary_genre is None
    assert batch.genre.secondary_genres == []
    assert DecisionPolicy().route_genre(batch.genre) == PolicyAction.ACQUIRE_EVIDENCE


def test_secondaries_do_not_displace_primary_and_ties_are_stable(taxonomy):
    batch, _ = classify(
        taxonomy,
        {"action": 1.0},
        {
            "action": {
                "action_adventure": 0.3,
                "arcade_action": 0.3,
                "character_action": 0.2,
                "beat_em_up": 0.2,
            },
        },
    )
    assert batch.genre.primary_genre == "action_adventure"
    assert batch.genre.secondary_genres == ["arcade_action", "beat_em_up"]
    assert batch.genre.confidence == 0.3


def test_ineligible_genre_never_enters_choice_or_ranking(taxonomy):
    action = taxonomy.families_by_id["action"]
    edited = replace(
        action,
        genres=tuple(
            replace(g, primary_eligible=False) if g.id == "battle_royale" else g
            for g in action.genres
        ),
    )
    taxonomy = replace(
        taxonomy,
        genre_families=tuple(edited if f.id == "action" else f for f in taxonomy.genre_families),
    )
    compiler = JevQuestionCompiler(taxonomy)
    assert "battle_royale" not in compiler.build_genre_specs(["action"])["genre:action"].criteria
    batch, _ = classify(taxonomy, {"action": 1.0}, {"action": {"looter_shooter": 1.0}})
    assert "battle_royale" not in batch.genre.global_genre_probabilities
    assert batch.genre.primary_genre == "looter_shooter"


def test_raw_rounding_is_preserved_while_derived_ranking_normalizes(taxonomy):
    batch, _ = classify(
        taxonomy,
        {"action": 0.6001, "role_playing": 0.4},
        {
            "action": {"battle_royale": 1.0000},
            "role_playing": {"souls_like": 0.8, "insufficient_evidence": 0.2001},
        },
    )
    assert batch.genre.family_probabilities["action"] == 0.6001
    assert (
        batch.genre.conditional_genre_probabilities["role_playing"]["insufficient_evidence"]
        == 0.2001
    )
    assert sum(batch.genre.global_genre_probabilities.values()) == pytest.approx(1.0)
    assert batch.genre.global_genre_probabilities["battle_royale"] == pytest.approx(0.6001 / 1.0001)


def test_taxonomy_examples_never_sent_to_jev(taxonomy):
    sentinel = "EXAMPLE_ONLY_NEVER_CLASSIFY_FROM_THIS"
    taxonomy = replace(
        taxonomy,
        genre_families=tuple(
            replace(f, genres=tuple(replace(g, example_games=(sentinel,)) for g in f.genres))
            for f in taxonomy.genre_families
        ),
    )
    compiler = JevQuestionCompiler(taxonomy)
    specs = {**compiler.build_specs(), **compiler.build_genre_specs(list(taxonomy.families_by_id))}
    serialized = json.dumps(
        {k: {"instructions": v.instructions, "criteria": v.criteria} for k, v in specs.items()}
    )
    assert sentinel not in serialized
    for family in taxonomy.genre_families:
        for genre in family.eligible_genres:
            criteria = specs[f"genre:{family.id}"].criteria[genre.id]
            assert genre.definition in criteria
            assert all(c in criteria for c in genre.inclusion_criteria + genre.exclusion_notes)


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_primary",
        "multiple_primary",
        "duplicate_secondary",
        "unknown_secondary",
        "bad_sum",
        "nan",
        "omitted_family",
        "inconsistent_joint",
    ],
)
def test_invalid_result_contract_rejected(taxonomy, mutation):
    batch, _ = classify(
        taxonomy,
        {"action": 0.8, "role_playing": 0.2},
        {"action": {"battle_royale": 1.0}, "role_playing": {"souls_like": 1.0}},
    )
    raw = batch.genre.model_dump()
    if mutation == "wrong_primary":
        raw["primary_genre"] = "souls_like"
    elif mutation == "multiple_primary":
        raw["primary_genre"] = ["battle_royale", "souls_like"]
    elif mutation == "duplicate_secondary":
        raw["secondary_genres"] = ["souls_like", "souls_like"]
    elif mutation == "unknown_secondary":
        raw["secondary_genres"] = ["not_a_genre"]
    elif mutation == "bad_sum":
        raw["global_genre_probabilities"]["battle_royale"] = 0.1
    elif mutation == "nan":
        raw["global_genre_probabilities"]["battle_royale"] = float("nan")
    elif mutation == "omitted_family":
        raw["evaluated_families"] = ["action"]
    elif mutation == "inconsistent_joint":
        raw["global_genre_probabilities"]["battle_royale"] = 0.7
        raw["global_genre_probabilities"]["souls_like"] = 0.3
        raw["confidence"] = 0.7
    with pytest.raises(ValidationError):
        GenreDecision.model_validate(raw)


def test_all_positive_families_are_retained(taxonomy):
    family = {f.id: 1 / 14 for f in taxonomy.genre_families}
    batch, gateway = classify(taxonomy, family, {})
    assert len(gateway.calls) == 2
    assert len(gateway.calls[1][1]) == 14
    assert len(batch.genre.conditional_genre_probabilities) == 14
    assert batch.genre.primary_genre is None
    assert batch.genre.global_genre_probabilities["insufficient_evidence"] == pytest.approx(1)


@pytest.mark.parametrize("failure", ["missing_family", "cross_family_option"])
def test_invalid_stage_b_fails_instead_of_producing_partial_genre(taxonomy, failure):
    from genre_helpers import ScriptedGenreGateway
    from typesafe_sdk import SystemOneResponse

    from gametagger.decisions.jev import JevContractError, JevDecisionEngine

    class BrokenGateway(ScriptedGenreGateway):
        def run(self, *, state, specs):
            result = super().run(state=state, specs=specs)
            if "genre_family" in specs:
                return result
            raw = result.model_dump()
            key = next(iter(raw["answers"]))
            if failure == "missing_family":
                del raw["answers"][key]
            else:
                raw["answers"][key]["probabilities"]["another_family_genre"] = 0.0
            return SystemOneResponse.model_validate(raw)

    with pytest.raises(JevContractError):
        JevDecisionEngine(taxonomy, BrokenGateway({"action": 1.0}, {})).decide(
            game_id="fixture", game_title=None, observations=[]
        )
