import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from gametagger.decisions.jev import JevDecisionEngine
from gametagger.decisions.mock import MockJevGateway
from gametagger.domain import AnalysisResult, PolicyAction, TagState
from gametagger.observers.boundary import ObserverBoundaryError
from gametagger.observers.mock import MockObserver
from gametagger.pipeline import AnalysisPipeline


def test_full_offline_pipeline(taxonomy, evidence):
    facts = {evidence.id: ["A figure holds a shield beside a bright white flash."]}
    result = AnalysisPipeline(
        MockObserver(facts), JevDecisionEngine(taxonomy, MockJevGateway())
    ).analyze(
        game_id="test",
        project_id="test",
        evidence=[evidence],
        offline=True,
    )
    assert len(result.tags) == 17
    assert all(
        result.execution.questions[t.id].status in {"valid", "not_evaluated"} for t in taxonomy.tags
    )
    assert result.execution.questions["mechanic_parry"].answer is None
    for tag in result.tags:
        assert set(tag.probabilities) == set(TagState)
        assert tag.state == TagState.INSUFFICIENT
        assert tag.action == PolicyAction.ACQUIRE_EVIDENCE
        assert tag.evidence_ids == [evidence.id]
    assert len(result.genre.global_genre_probabilities) == 101
    assert result.genre.primary_genre is None
    assert result.genre.evidence_ids == [evidence.id]
    assert result.run.decision_model == "mock-jev-v1"
    assert result.run.latency_ms >= 0
    assert set(result.run.stage_latency_ms) == {"observe", "decide", "policy"}
    assert result.run.sdk_versions["typesafe-sdk"] == "0.7.0"
    assert result.evidence[0].sha256 == hashlib.sha256(Path(evidence.uri).read_bytes()).hexdigest()
    assert evidence.sha256 is None
    assert AnalysisResult.model_validate_json(result.model_dump_json()) == result


def test_pipeline_checks_injected_observers_before_jev(taxonomy, evidence):
    gateway = Mock()
    observer = MockObserver({evidence.id: ["This is an Action RPG."]})
    with pytest.raises(ObserverBoundaryError):
        AnalysisPipeline(observer, JevDecisionEngine(taxonomy, gateway)).analyze(
            game_id="test",
            project_id="test",
            evidence=[evidence],
        )
    gateway.run.assert_not_called()


def test_blind_metadata_removed_before_observer_and_jev(taxonomy, evidence):
    evidence.metadata = {"description": "Famous Game is a Souls-like"}
    evidence.source = "Famous Game store page"
    gateway = Mock(wraps=MockJevGateway())
    gateway.model = "mock-jev-v1"
    result = AnalysisPipeline(MockObserver(), JevDecisionEngine(taxonomy, gateway)).analyze(
        game_id="blind-1",
        project_id="blind-1",
        game_title="Famous Game",
        evidence=[evidence],
        blind_media=True,
    )
    assert result.observations == []
    assert result.identity_audit["eligibility"]["status"] == "eligible"
    assert result.run.game_title is None
    gateway.run.assert_not_called()
    assert result.execution.execution_status == "not_evaluated"


@pytest.mark.parametrize("invalid", ["empty", "duplicate", "hash_mismatch", "missing_image"])
def test_invalid_evidence_stops_before_classification(taxonomy, evidence, invalid):
    items = [evidence]
    if invalid == "empty":
        items = []
    elif invalid == "duplicate":
        items = [evidence, evidence]
    elif invalid == "hash_mismatch":
        evidence.sha256 = "bad"
    else:
        evidence.uri = None
    gateway = Mock()
    with pytest.raises(ValueError):
        AnalysisPipeline(MockObserver(), JevDecisionEngine(taxonomy, gateway)).analyze(
            game_id="test",
            project_id="test",
            evidence=items,
        )
    gateway.run.assert_not_called()


def test_cli_offline_json(evidence, tmp_path):
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"description": "A figure holds a shield."}))
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "gametagger.cli",
            "--image",
            evidence.uri,
            "--metadata",
            str(metadata),
            "--offline",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    result = AnalysisResult.model_validate_json(completed.stdout)
    assert result.run.offline
    assert len(result.tags) == 0
    assert all(
        q.answer is None
        for key, q in result.execution.questions.items()
        if not key.startswith("genre")
    )
    assert result.observations[0].kind == "metadata_quote"
    assert len(result.genre.global_genre_probabilities) == 101


def test_mixed_distributions_preserved_through_policy(taxonomy, evidence):
    from typesafe_sdk import SystemOneResponse

    class MixedGateway(MockJevGateway):
        def run(self, *, state, specs):
            payload = super().run(state=state, specs=specs).model_dump()
            if "genre_family" not in specs:
                return SystemOneResponse.model_validate(payload)
            for key, state in zip(list(specs)[:4], TagState, strict=True):
                payload["answers"][key].update(
                    choice=state.value,
                    probabilities={s.value: float(s == state) for s in TagState},
                )
            return SystemOneResponse.model_validate(payload)

    result = AnalysisPipeline(
        MockObserver({evidence.id: ["A figure holds a shield."]}),
        JevDecisionEngine(taxonomy, MixedGateway()),
    ).analyze(
        game_id="test",
        project_id="test",
        evidence=[evidence],
        offline=True,
    )
    assert [tag.state for tag in result.tags[:4]] == list(TagState)
    assert [tag.action for tag in result.tags[:4]] == [
        PolicyAction.ACCEPT,
        PolicyAction.ACCEPT,
        PolicyAction.ACQUIRE_EVIDENCE,
        PolicyAction.HUMAN_REVIEW,
    ]
    assert all(tag.evidence_ids == [evidence.id] for tag in result.tags)


def test_cli_passes_workspace_environment_to_observer(evidence, monkeypatch, capsys):
    from gametagger import cli

    constructor = Mock(return_value=MockObserver())
    monkeypatch.setattr(cli, "AnthropicObserver", constructor)
    monkeypatch.setattr(cli, "TypeSafeGateway", lambda **kwargs: MockJevGateway())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "offline-test-key")
    monkeypatch.setenv("TYPESAFE_API_KEY", "offline-test-key")
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test")
    monkeypatch.setattr(
        sys, "argv", ["gametagger", "--image", evidence.uri, "--observer-model", "test-model"]
    )
    cli.main()
    assert constructor.call_args.kwargs["workspace_id"] == "wrkspc_test"
    assert (
        json.loads(capsys.readouterr().out)["run"]["decision_prompt_version"] == "jev-evidence-v1"
    )
