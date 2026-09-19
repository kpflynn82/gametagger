from unittest.mock import Mock

from test_identity import manifest, quote, source, text

from gametagger.decisions.jev import JevDecisionEngine
from gametagger.decisions.mock import MockJevGateway
from gametagger.evidence_policy import ClaimAttribution, EvidenceProfile, evidence_eligibility
from gametagger.identity import SubjectIdentity, content_hash


def test_verified_store_text_does_not_become_visual_or_temporal_evidence(taxonomy):
    e = text("s", "Engage in combat.")
    p = evidence_eligibility(taxonomy, [e], [quote(e)], manifest([e]))
    assert p["mechanic_parry"]["reason"] == "no_eligible_evidence"
    gateway = Mock(wraps=MockJevGateway())
    gateway.model = "mock"
    result = JevDecisionEngine(taxonomy, gateway).decide(
        game_id="x", game_title=None, observations=[quote(e)], evidence=[e], identity=manifest([e])
    )
    q = result.questions["mechanic_parry"]
    assert q.status == "not_evaluated" and q.answer is None
    assert q.error.code == "no_eligible_evidence"
    assert not any(t.tag_id == "mechanic_parry" for t in result.tags)
    assert result.genre is not None
    assert result.genre.support_links == []


def test_documented_parry_requires_explicit_reviewed_release_matched_claim(taxonomy):
    e = text("s", "Players can parry enemy attacks.")
    o = quote(e)
    m = manifest(
        [e],
        subject=SubjectIdentity(canonical_game_id="game", release_id="release"),
        sources=(source(e, release_id="release"),),
    )
    profile = EvidenceProfile(
        evidence_id=e.id,
        provider="store",
        modality="text",
        authority="official_publisher",
        content_sha256=content_hash(e),
        authority_reviewer="fixture",
    )
    claim = ClaimAttribution(
        property_id="mechanic_parry",
        decision="present",
        observation_id=o.id,
        start=0,
        end=len(o.text),
        quote=o.text,
        origin="human_review",
        reviewer="fixture",
        reviewed_at="2026-09-19",
    )

    def eligible(profiles=(profile,), claims=(claim,), identity=m):
        return evidence_eligibility(taxonomy, [e], [o], identity, profiles, claims)[
            "mechanic_parry"
        ]

    assert eligible()["documented_observation_ids"] == [o.id]
    assert eligible(claims=())["status"] == "not_evaluated"
    assert eligible(profiles=())["status"] == "not_evaluated"
    assert eligible(identity=manifest([e]))["status"] == "not_evaluated"
    assert (
        eligible(claims=(claim.model_copy(update={"origin": "ai_suggestion"}),))["status"]
        == "not_evaluated"
    )
    assert (
        eligible(profiles=(profile.model_copy(update={"modality": "image"}),))["status"]
        == "not_evaluated"
    )
