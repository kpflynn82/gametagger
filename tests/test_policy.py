from genometagger_v2.decisions.policy import DecisionPolicy
from genometagger_v2.domain import GenreDecision, PolicyAction, TagDecision, TagState


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


def test_genre_requires_probability_and_margin():
    policy = DecisionPolicy()
    good = GenreDecision(
        primary_genre="Action RPG",
        probabilities={"Action RPG": 0.78, "Souls-like": 0.10, "insufficient_evidence": 0.04},
        decision_model="jev-test",
    )
    close = GenreDecision(
        primary_genre="Action RPG",
        probabilities={"Action RPG": 0.51, "Souls-like": 0.44, "insufficient_evidence": 0.01},
        decision_model="jev-test",
    )
    assert policy.route_genre(good) is PolicyAction.ACCEPT
    assert policy.route_genre(close) is PolicyAction.HUMAN_REVIEW
