import json

import httpx2
import pytest
from typesafe_sdk import SystemOneResponse, TypeSafeClient

from gametagger.decisions.jev import (
    JevContractError,
    JevDecisionEngine,
    JevQuestionCompiler,
    TypeSafeGateway,
    select_families,
    validate_response,
)
from gametagger.decisions.mock import MockJevGateway


def sdk_payload(specs):
    payload = MockJevGateway().run(state="", specs=specs).model_dump()
    payload["model"] = "jev-contract-fixture"
    payload["usage"] = {"input_tokens": 123, "output_tokens": 456}
    return payload


def test_real_sdk_http_serialization_and_parsing(taxonomy):
    specs = JevQuestionCompiler(taxonomy).build_specs()
    payload = sdk_payload(specs)
    probabilities = {
        "present": 0.955,
        "absent": 0.01,
        "insufficient_evidence": 0.03,
        "conflicting_evidence": 0.005,
    }
    payload["answers"][taxonomy.tags[0].id].update(
        choice="present",
        probabilities=probabilities,
        confidence=0.9,
    )

    def handler(request):
        assert request.url.path == "/v1/systemone"
        body = json.loads(request.content)
        assert body["model"] == (
            "jev-latest" if "genre_family" in body["questions"] else "jev-contract-fixture"
        )
        if "genre_family" in body["questions"]:
            assert len(body["questions"]) == 26
            assert len(body["questions"]["genre_family"]["criteria"]) == 15
            assert body["questions"][taxonomy.tags[0].id]["type"] == "choice"
            return httpx2.Response(200, json=payload)
        selected = select_families(taxonomy, payload["answers"]["genre_family"]["probabilities"])
        conditional = JevQuestionCompiler(taxonomy).build_genre_specs(selected)
        assert set(body["questions"]) == set(conditional)
        assert all(len(q["criteria"]) < 24 for q in body["questions"].values())
        return httpx2.Response(200, json=sdk_payload(conditional))

    with TypeSafeClient(
        api_key="offline-test-key", transport=httpx2.MockTransport(handler)
    ) as client:
        batch = JevDecisionEngine(taxonomy, TypeSafeGateway(client=client)).decide(
            require_identity=False,
            game_id="test",
            game_title=None,
            observations=[],
        )
    assert batch.model == "jev-contract-fixture"
    assert batch.tags[0].probabilities == probabilities
    assert batch.tags[0].confidence == 0.9
    assert batch.usage == {"input_tokens": 246, "output_tokens": 912}
    assert batch.genre.primary_genre is None
    assert len(batch.genre.global_genre_probabilities) == 101


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_answer",
        "extra_answer",
        "missing_option",
        "extra_option",
        "nan",
        "negative",
        "too_large",
        "bad_sum",
        "wrong_choice",
        "unknown_choice",
        "bad_confidence",
        "wrong_type",
    ],
)
def test_bad_distributions_never_silently_repaired(taxonomy, mutation):
    specs = JevQuestionCompiler(taxonomy).build_specs()
    payload = sdk_payload(specs)
    key = taxonomy.tags[0].id
    answer = payload["answers"][key]
    p = answer["probabilities"]
    if mutation == "missing_answer":
        del payload["answers"][key]
    elif mutation == "extra_answer":
        payload["answers"]["extra"] = answer
    elif mutation == "missing_option":
        del p["absent"]
    elif mutation == "extra_option":
        p["unknown"] = 0.0
    elif mutation == "nan":
        p["present"] = float("nan")
    elif mutation == "negative":
        p["present"] = -0.1
    elif mutation == "too_large":
        p["present"] = 1.1
    elif mutation == "bad_sum":
        p["present"] = 0.2
    elif mutation == "wrong_choice":
        answer["choice"] = "absent"
    elif mutation == "unknown_choice":
        answer["choice"] = "surprise"
    elif mutation == "bad_confidence":
        answer["confidence"] = 2.0
    elif mutation == "wrong_type":
        payload["answers"][key] = {"type": "noul", "noul": 0.5}
    with pytest.raises(JevContractError):
        validate_response(SystemOneResponse.model_validate(payload), specs)


def test_authentication_failure_is_not_replaced_with_mock(taxonomy):

    def handler(request):
        return httpx2.Response(401, json={"error": "Unauthorized"})

    with TypeSafeClient(
        api_key="offline-test-key", transport=httpx2.MockTransport(handler)
    ) as client:
        batch = JevDecisionEngine(taxonomy, TypeSafeGateway(client=client)).decide(
            require_identity=False, game_id="test", game_title=None, observations=[]
        )
    assert batch.execution_status == "failed"
    assert batch.tags == [] and batch.genre is None
    assert len(batch.attempts) == 1
    assert batch.attempts[0].error.code == "authentication"
