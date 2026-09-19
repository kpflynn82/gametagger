import json

import httpx2
import pytest
from typesafe_sdk import TypeSafeClient

from gametagger.decisions.jev import JevDecisionEngine, TypeSafeGateway
from gametagger.decisions.mock import MockJevGateway


class BrokenQuestions(MockJevGateway):
    def __init__(self, key, *, recover=False):
        self.key, self.recover = key, recover
        self.calls = []
        self.failures = 0

    def run(self, *, state, specs):
        self.calls.append((state, set(specs)))
        raw = super().run(state=state, specs=specs).model_dump()
        if "genre_family" in specs:
            p = raw["answers"]["genre_family"]["probabilities"]
            p.update(action=0.6, role_playing=0.4, insufficient_evidence=0)
            raw["answers"]["genre_family"]["choice"] = "action"
        if self.key in specs and (not self.recover or self.failures == 0):
            self.failures += 1
            p = raw["answers"][self.key]["probabilities"]
            winner = raw["answers"][self.key]["choice"]
            p[winner] -= 0.01
        return raw


def run(taxonomy, gateway, **kwargs):
    return JevDecisionEngine(taxonomy, gateway).decide(
        game_id="fixture", game_title=None, observations=[], require_identity=False, **kwargs
    )


def test_bad_tag_does_not_erase_other_tags_or_genre(taxonomy):
    gateway = BrokenQuestions("mechanic_ranged_combat")
    b = run(taxonomy, gateway)
    assert len(b.tags) == 24 and b.genre is not None
    assert b.questions["mechanic_ranged_combat"].status == "error"
    assert b.questions["mechanic_ranged_combat"].answer is None
    assert gateway.calls[1][1] == {"mechanic_ranged_combat"}
    assert b.execution_status == "partial"
    assert len(b.attempts) == 3


def test_failed_family_keeps_tags_and_never_computes_children(taxonomy):
    g = BrokenQuestions("genre_family")
    b = run(taxonomy, g)
    assert len(b.tags) == 25 and b.genre is None
    assert b.genre_execution.error.code == "family_dependency"
    assert g.calls[1][1] == {"genre_family"}
    assert len(g.calls) == 2


def test_failed_positive_branch_preserves_other_conditionals_without_pruning(taxonomy):
    g = BrokenQuestions("genre:role_playing")
    b = run(taxonomy, g)
    assert b.questions["genre:action"].status == "valid"
    assert b.questions["genre:role_playing"].status == "error"
    assert len(b.tags) == 25 and b.genre is None
    assert g.calls[-1][1] == {"genre:role_playing"}
    assert b.genre_execution.error.code == "conditional_dependency"


@pytest.mark.parametrize("key", ["mechanic_ranged_combat", "genre_family", "genre:role_playing"])
def test_retry_first_valid_and_hashes_unchanged(taxonomy, key):
    g = BrokenQuestions(key, recover=True)
    b = run(taxonomy, g)
    assert b.execution_status == "complete"
    attempts = [a for a in b.attempts if key in a.question_ids]
    assert len(attempts) == 2
    assert attempts[0].evidence_hash == attempts[1].evidence_hash
    assert attempts[0].spec_hashes[key] == attempts[1].spec_hashes[key]
    assert b.questions[key].selected_attempt_id == attempts[1].id
    # Already valid questions never recur in the same stage.
    for q in set(b.questions) - {key}:
        assert sum(q in a.question_ids for a in b.attempts) == 1


@pytest.mark.parametrize(
    "bad", ["shape", "missing", "nan", "inf", "string_number", "extra_option", "choice"]
)
def test_sdk_custom_envelope_isolates_bad_question_and_pins_retries(taxonomy, bad):
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        raw = (
            MockJevGateway()
            .run(
                state="",
                specs={
                    k: type("S", (), {"criteria": v["criteria"]})
                    for k, v in body["questions"].items()
                },
            )
            .model_dump()
        )
        raw["model"] = "jev-1.13.0"
        raw["usage"] = {"input_tokens": 10, "output_tokens": 5}
        if len(calls) == 1:
            a = raw["answers"]["mechanic_ranged_combat"]
            if bad == "shape":
                a["probabilities"] = []
            if bad == "missing":
                del raw["answers"]["mechanic_ranged_combat"]
            if bad in ("nan", "inf"):
                a["probabilities"]["present"] = float(bad)
            if bad == "string_number":
                a["probabilities"]["present"] = "0.0"
            if bad == "extra_option":
                a["probabilities"]["x"] = 0
            if bad == "choice":
                a["choice"] = "absent"
        return httpx2.Response(
            200, content=json.dumps(raw).encode(), headers={"content-type": "application/json"}
        )

    with TypeSafeClient(api_key="offline-test-key", transport=httpx2.MockTransport(handle)) as c:
        b = run(taxonomy, TypeSafeGateway(client=c))
    assert b.execution_status == "complete"
    assert set(calls[1]["questions"]) == {"mechanic_ranged_combat"}
    assert all(c["model"] == "jev-1.13.0" for c in calls[1:])
    assert b.usage == {"input_tokens": 30, "output_tokens": 15}


def test_pinned_model_drift_fails_closed(taxonomy):
    class Drifting(TypeSafeGateway):
        def run_pinned(self, *, state, specs, model):
            raw = MockJevGateway().run(state=state, specs=specs).model_dump()
            raw["model"] = "version-1" if "genre_family" in specs else "version-2"
            return raw

    b = run(taxonomy, Drifting())
    assert len(b.tags) == 25 and b.genre is None
    assert b.attempts[-1].error.code == "envelope"


@pytest.mark.parametrize("failure", ["answers", "usage", "model", "extra"])
def test_invalid_envelope_never_accepts_partial_answers(taxonomy, failure):
    class Bad(MockJevGateway):
        def run(self, *, state, specs):
            raw = super().run(state=state, specs=specs).model_dump()
            if failure == "extra":
                raw["answers"]["unrequested"] = {}
            else:
                raw[failure] = None
            return raw

    b = run(taxonomy, Bad())
    assert b.tags == [] and b.genre is None and b.execution_status == "failed"
    assert len(b.attempts) == 2
    assert all(q.answer is None for q in b.questions.values())


def test_transport_failure_has_unknown_usage_and_no_semantic_answers(taxonomy):
    class Down(MockJevGateway):
        def run(self, **kwargs):
            raise TimeoutError("do not leak a secret")

    b = run(taxonomy, Down())
    assert b.tags == [] and b.genre is None
    assert b.usage == {"input_tokens": None, "output_tokens": None}
    assert "do not leak" not in b.model_dump_json()
