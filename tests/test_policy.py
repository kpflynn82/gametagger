from gametagger.decisions.policy import DecisionPolicy
from gametagger.domain import PolicyAction, TagDecision, TagState


def tag_decision(state: TagState, **probs: float) -> TagDecision:
    base = {s: 0.0 for s in TagState}
    base.update({TagState(k): v for k, v in probs.items()})
    return TagDecision(
        tag_id="mechanic_parry",
        state=state,
        probabilities=base,
        decision_model="jev-test",
    )


def test_high_present_is_accepted():
    policy = DecisionPolicy()
    decision = tag_decision(TagState.PRESENT, present=0.97, insufficient_evidence=0.01)
    assert policy.route_tag(decision) is PolicyAction.ACCEPT


def test_insufficient_evidence_requests_more_evidence():
    policy = DecisionPolicy()
    decision = tag_decision(
        TagState.INSUFFICIENT,
        present=0.22,
        absent=0.08,
        insufficient_evidence=0.68,
        conflicting_evidence=0.02,
    )
    assert policy.route_tag(decision) is PolicyAction.ACQUIRE_EVIDENCE


def test_conflict_goes_to_human_review():
    policy = DecisionPolicy()
    decision = tag_decision(
        TagState.CONFLICTING,
        present=0.35,
        absent=0.18,
        insufficient_evidence=0.10,
        conflicting_evidence=0.37,
    )
    assert policy.route_tag(decision) is PolicyAction.HUMAN_REVIEW


def test_genre_requires_probability_and_margin(taxonomy):
    from genre_helpers import classify

    policy = DecisionPolicy()
    good, _ = classify(
        taxonomy,
        {"role_playing": 1.0},
        {
            "role_playing": {
                "action_rpg": 0.78,
                "souls_like": 0.10,
                "jrpg": 0.08,
                "insufficient_evidence": 0.04,
            }
        },
    )
    close, _ = classify(
        taxonomy,
        {"role_playing": 1.0},
        {
            "role_playing": {
                "action_rpg": 0.51,
                "souls_like": 0.44,
                "jrpg": 0.04,
                "insufficient_evidence": 0.01,
            }
        },
    )
    assert policy.route_genre(good.genre) is PolicyAction.ACCEPT
    assert policy.route_genre(close.genre) is PolicyAction.HUMAN_REVIEW
    assert good.genre.primary_genre == close.genre.primary_genre == "action_rpg"
