from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from gametagger.decisions.jev import JevDecisionEngine
from gametagger.decisions.mock import MockJevGateway
from gametagger.domain import EvidenceItem, EvidenceType, Observation
from gametagger.identity import (
    IdentityDecision,
    IdentityManifest,
    SourceIdentity,
    SubjectIdentity,
    content_hash,
    project_upload_manifest,
    validate_identity,
)
from gametagger.pipeline import AnalysisPipeline


def approved(**changes):
    data = dict(
        origin="human_review",
        reviewer="fixture-reviewer",
        justification="Synthetic approval for regression; not real-world adjudication",
        decided_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
    )
    data.update(changes)
    return IdentityDecision(**data)


def source(item, **changes):
    data = dict(
        evidence_id=item.id,
        provider="fixture-store",
        product_or_page_id="store:123",
        content_sha256=content_hash(item),
        relationship="verified_same_release",
        decision=approved(),
    )
    data.update(changes)
    return SourceIdentity(**data)


def manifest(items, **changes):
    data = dict(
        evidence_version="v1",
        raw_record_id="raw-1",
        raw_label="Original title",
        record_kind="game_candidate",
        record_decision=approved(),
        subject=SubjectIdentity(canonical_game_id="catalog:subject"),
        sources=tuple(source(e) for e in items),
    )
    data.update(changes)
    return IdentityManifest(**data)


def text(eid, value):
    return EvidenceItem(
        id=eid, type=EvidenceType.STORE_METADATA, source="store", metadata={"description": value}
    )


def quote(item):
    return Observation(
        id=item.id + ":quote",
        evidence_id=item.id,
        kind="metadata_quote",
        metadata_key="description",
        text=item.metadata["description"],
        observer_model="fixture",
    )


def test_matching_titles_and_store_ids_do_not_approve_identity():
    e = text("s1", "Description")
    m = manifest(
        [e],
        sources=(
            source(
                e, reported_title="Original title", decision=approved(origin="automated_suggestion")
            ),
        ),
    )
    assert validate_identity(m, [e]).status == "no_eligible_sources"
    assert (
        validate_identity(
            manifest([e], record_decision=approved(origin="automated_suggestion")), [e]
        ).status
        == "identity_unresolved"
    )


def test_mixed_sources_excluded_before_question_payload(taxonomy):
    good, bad = text("good", "SUPPORTED_TEXT"), text("bad", "WRONG_ENTITY_SECRET_SENTINEL")
    m = manifest([good, bad], sources=(source(good), source(bad, relationship="mismatch")))
    gateway = Mock(wraps=MockJevGateway())
    gateway.model = "mock"
    batch = JevDecisionEngine(taxonomy, gateway).decide(
        game_id="game",
        game_title=None,
        evidence=[good, bad],
        observations=[quote(good), quote(bad)],
        identity=m,
    )
    assert batch.identity_status == "eligible"
    for call in gateway.run.call_args_list:
        assert "WRONG_ENTITY" not in call.kwargs["state"]
        assert "SUPPORTED_TEXT" in call.kwargs["state"]
    assert batch.genre.evidence_ids == ["good"]
    assert len(validate_identity(m, [good, bad]).sources) == 2


def test_cross_release_scope_never_transfers_unapproved_features(taxonomy):
    e = text("cross", "Cross-release description")
    m = manifest(
        [e],
        subject=SubjectIdentity(canonical_game_id="game", release_id="release-2"),
        sources=(
            source(
                e,
                release_id="release-1",
                relationship="approved_cross_release_scope",
                transferable_properties=("genre",),
            ),
        ),
    )
    batch = JevDecisionEngine(taxonomy, MockJevGateway()).decide(
        game_id="game", game_title=None, observations=[quote(e)], evidence=[e], identity=m
    )
    assert batch.genre is not None and batch.tags == []
    assert batch.questions["engagement_co_op"].status == "not_evaluated"
    assert all(
        set(a.question_ids) <= {"genre_family"}
        or all(k.startswith("genre:") for k in a.question_ids)
        for a in batch.attempts
    )
    wrong = manifest([e], subject=m.subject, sources=(source(e, release_id="release-1"),))
    assert validate_identity(wrong, [e]).status == "no_eligible_sources"


def test_approved_localization_preserves_original_script():
    e = text("localized", "原文")
    s = source(
        e,
        reported_title="星之翼",
        relationship="approved_alias_localization",
        approved_aliases=("星之翼", "Starward"),
    )
    m = manifest([e], sources=(s,))
    assert validate_identity(m, [e]).status == "eligible"
    assert "星之翼" in m.model_dump_json()


def test_shared_franchise_is_not_same_product():
    e = text("franchise", "A different product's description")
    m = manifest(
        [e],
        raw_label="RuneScape",
        sources=(
            source(
                e, reported_title="RuneScape: Dragonwilds", relationship="related_different_product"
            ),
        ),
    )
    assert validate_identity(m, [e]).status == "no_eligible_sources"


@pytest.mark.parametrize("kind", ["dlc", "mode", "clip_chapter", "location_encounter", "other"])
def test_nongame_records_remain_auditable_not_classified(kind, taxonomy):
    e = text("x", "source")
    m = manifest([e], record_kind=kind)
    batch = JevDecisionEngine(taxonomy, MockJevGateway()).decide(
        game_id="x", game_title=None, observations=[quote(e)], evidence=[e], identity=m
    )
    assert batch.identity_status == "invalid_record" and batch.attempts == []
    assert batch.genre is None and batch.tags == []
    assert len(batch.questions) == 26


def test_default_identity_unresolved_has_no_fake_probabilities(taxonomy):
    batch = JevDecisionEngine(taxonomy, MockJevGateway()).decide(
        game_id="raw", game_title=None, observations=[]
    )
    assert batch.execution_status == "not_evaluated" and batch.attempts == []
    assert all(q.answer is None for q in batch.questions.values())


def test_project_upload_works_without_store_resolution_and_observes_once(evidence, taxonomy):
    from gametagger.observers.mock import MockObserver

    observer = Mock(wraps=MockObserver())
    observer.model = "fixture"
    observer.prompt_version = "fixture"
    batch = AnalysisPipeline(observer, JevDecisionEngine(taxonomy, MockJevGateway())).analyze(
        game_id="unknown", evidence=[evidence], project_id="publisher:unannounced", offline=True
    )
    assert batch.identity_audit["eligibility"]["status"] == "eligible"
    assert observer.observe.call_count == 1


def test_unapproved_pipeline_never_calls_observer(evidence, taxonomy):
    observer = Mock()
    observer.model = "fixture"
    observer.prompt_version = "fixture"
    result = AnalysisPipeline(observer, JevDecisionEngine(taxonomy, MockJevGateway())).analyze(
        game_id="unresolved", evidence=[evidence]
    )
    observer.observe.assert_not_called()
    assert result.genre is None and result.execution.execution_status == "not_evaluated"


def test_jev_retry_does_not_rerun_observer(evidence, taxonomy):
    from gametagger.observers.mock import MockObserver

    class Recovering(MockJevGateway):
        calls = 0

        def run(self, *, state, specs):
            self.calls += 1
            raw = super().run(state=state, specs=specs).model_dump()
            if self.calls == 1:
                raw["answers"]["mechanic_ranged_combat"]["probabilities"][
                    "insufficient_evidence"
                ] = 0.99
            return raw

    observer = Mock(wraps=MockObserver())
    observer.model = "fixture"
    observer.prompt_version = "fixture"
    result = AnalysisPipeline(observer, JevDecisionEngine(taxonomy, Recovering())).analyze(
        game_id="opaque", evidence=[evidence], project_id="project", offline=True
    )
    assert result.execution.execution_status == "complete"
    assert len(result.execution.attempts) == 3
    observer.observe.assert_called_once()


def test_content_edits_require_new_version_and_history():
    e = text("x", "Original")
    old = manifest([e])
    before = old.model_dump_json()
    changed = e.model_copy(update={"metadata": {"description": "Changed"}})
    assert validate_identity(old, [changed]).status == "no_eligible_sources"
    new = old.corrected(
        evidence_version="v2",
        reason="Corrected source association",
        reviewer="fixture",
        sources=(source(changed),),
    )
    assert new.corrections[-1].previous_version_hash == old.version_hash
    assert old.model_dump_json() == before
    assert validate_identity(new, [changed]).status == "eligible"
    with pytest.raises(ValueError):
        old.corrected(reason="x", reviewer="fixture")
    with pytest.raises(ValueError, match="immutable"):
        old.corrected(
            evidence_version="v2", raw_label="replacement", reason="x", reviewer="fixture"
        )


def test_blind_context_does_not_leak_review_names_or_identifiers(taxonomy):
    e = EvidenceItem(
        id="FamousGame-asset",
        type=EvidenceType.GAMEPLAY_IMAGE,
        source="FamousGame-store",
        sha256="a" * 64,
        metadata={"title": "FamousGame"},
    )
    m = project_upload_manifest([e], "FamousGame-project")
    obs = Observation(
        id="FamousGame-fact",
        evidence_id=e.id,
        text="A red square is visible.",
        observer_model="fixture",
    )
    gateway = Mock(wraps=MockJevGateway())
    gateway.model = "mock"
    JevDecisionEngine(taxonomy, gateway).decide(
        game_id="FamousGame",
        game_title="FamousGame",
        evidence=[e],
        observations=[obs],
        identity=m,
        blind_media=True,
    )
    assert all("FamousGame" not in c.kwargs["state"] for c in gateway.run.call_args_list)
