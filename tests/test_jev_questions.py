import json

from gametagger.decisions.jev import JevQuestionCompiler
from gametagger.domain import Observation
from gametagger.taxonomy import load_taxonomy


def test_compiler_builds_one_question_per_tag_plus_genre():
    taxonomy = load_taxonomy()
    specs = JevQuestionCompiler(taxonomy).build_specs()
    assert len(specs) == len(taxonomy.tags) + 1
    assert "primary_genre" in specs
    assert len(specs["primary_genre"].criteria) == 60


def test_tag_choice_supports_unknown_and_conflict():
    taxonomy = load_taxonomy()
    specs = JevQuestionCompiler(taxonomy).build_specs()
    criteria = specs["mechanic_parry"].criteria
    assert set(criteria) == {
        "present",
        "absent",
        "insufficient_evidence",
        "conflicting_evidence",
    }
    assert "Mere failure to observe" in criteria["absent"]


def test_blind_state_omits_title():
    state = JevQuestionCompiler.build_state(
        game_id="g-1",
        game_title="Famous Game",
        observations=[
            Observation(
                id="o1",
                evidence_id="clip-1",
                text="Player fires a rifle from first-person view.",
                observer_model="fixture",
            )
        ],
        blind_media=True,
    )
    payload = json.loads(state)
    assert "game_title" not in payload
    assert payload["observations"][0]["evidence_id"] == "clip-1"


def test_single_view_never_establishes_game_wide_absence():
    specs = JevQuestionCompiler(load_taxonomy()).build_specs()
    spec = specs["visual_third_person"]
    assert "explicit negative source evidence" in spec.criteria["absent"]
    assert "not mutually exclusive" in spec.instructions
    assert JevQuestionCompiler.prompt_version == "jev-v2"
