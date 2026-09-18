import json

from genometagger_v2.decisions.jev import JevQuestionCompiler
from genometagger_v2.domain import Observation
from genometagger_v2.taxonomy import load_taxonomy


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
