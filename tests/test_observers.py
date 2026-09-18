from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from gametagger.domain import Observation
from gametagger.evidence import prepare_evidence
from gametagger.observers.anthropic import AnthropicObserver
from gametagger.observers.boundary import ObservationBoundary, ObserverBoundaryError
from gametagger.observers.mock import MockObserver


@pytest.mark.parametrize(
    "text",
    [
        "This is Souls-like.",
        "Action RPG",
        "The parry mechanic is present.",
        "Player parries an attack.",
        "mechanic_parry=true",
        "The game supports Multiplayer",
        "This has procedural generation.",
        "It is a SOULS–LIKE game.",
    ],
)
def test_visual_classification_rejected(taxonomy, evidence, text):
    observation = Observation(id="o", evidence_id=evidence.id, text=text, observer_model="test")
    with pytest.raises(ObserverBoundaryError, match="taxonomy"):
        ObservationBoundary(taxonomy).validate([observation], evidence)


def test_all_canonical_labels_rejected(taxonomy, evidence):
    for label in [*taxonomy.primary_genres, *(t.label for t in taxonomy.tags)]:
        observation = Observation(
            id="o", evidence_id=evidence.id, text=f"This is {label}.", observer_model="test"
        )
        with pytest.raises(ObserverBoundaryError):
            ObservationBoundary(taxonomy).validate([observation], evidence)


def test_concrete_visible_fact_allowed(taxonomy, evidence):
    facts = {
        evidence.id: ["A shield covers the figure's left arm; a bright flash appears beside it."]
    }
    observer = MockObserver(facts)
    assert observer.observe(evidence) == observer.observe(evidence)
    ObservationBoundary(taxonomy).validate(observer.observe(evidence), evidence)


def test_only_exact_attributed_metadata_may_contain_labels(taxonomy, evidence):
    evidence.metadata = {"description": "An Action RPG with a parry mechanic."}
    boundary = ObservationBoundary(taxonomy)
    observations = MockObserver().observe(evidence)
    boundary.validate(observations, evidence)
    for update in [
        {"text": "Souls-like"},
        {"metadata_key": "missing"},
        {"kind": "visual_fact", "metadata_key": None},
        {"evidence_id": "other"},
    ]:
        with pytest.raises(ObserverBoundaryError):
            boundary.validate([observations[0].model_copy(update=update)], evidence)


def fake_response(text="A circular red icon appears in the upper left corner.", **overrides):
    return SimpleNamespace(
        model="resolved-vision-version",
        stop_reason="tool_use",
        content=[
            SimpleNamespace(
                type="tool_use",
                name="record_observations",
                input={
                    "observations": [
                        {"kind": "visual_fact", "text": text, "metadata_key": None, **overrides}
                    ],
                },
            )
        ],
    )


def test_anthropic_sends_image_and_metadata_and_assigns_provenance(taxonomy, evidence):
    evidence.metadata = {"description": "User supplied caption"}
    evidence, data = prepare_evidence(evidence)
    client = Mock()
    client.messages.create.return_value = fake_response()
    result = AnthropicObserver(taxonomy, model="configured-model", client=client).observe(
        evidence,
        image=data,
    )
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "configured-model"
    assert kwargs["messages"][0]["content"][0]["source"]["media_type"] == "image/png"
    assert "User supplied caption" in kwargs["messages"][0]["content"][1]["text"]
    assert kwargs["tool_choice"]["name"] == "record_observations"
    assert result[0].evidence_id == evidence.id
    assert result[0].observer_model == "resolved-vision-version"


@pytest.mark.parametrize(
    "response",
    [
        fake_response("Souls-like"),
        fake_response(tag="mechanic_parry"),
        SimpleNamespace(stop_reason="max_tokens", content=[]),
        SimpleNamespace(stop_reason="tool_use", content=[]),
    ],
)
def test_provider_boundary_fails_closed(taxonomy, evidence, response):
    evidence, data = prepare_evidence(evidence)
    client = Mock()
    client.messages.create.return_value = response
    with pytest.raises((ValueError, ValidationError)):
        AnthropicObserver(taxonomy, model="test", client=client).observe(evidence, image=data)


def test_anthropic_real_sdk_transport(taxonomy, evidence):
    import base64
    import json

    import httpx2
    from anthropic import Anthropic

    evidence, data = prepare_evidence(evidence)

    def handler(request):
        assert request.url.path == "/v1/messages"
        body = json.loads(request.content)
        image = body["messages"][0]["content"][0]
        assert base64.b64decode(image["source"]["data"]) == data
        assert body["tools"][0]["input_schema"]["additionalProperties"] is False
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "resolved-vision-version",
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 50, "output_tokens": 40},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_1",
                        "name": "record_observations",
                        "input": {
                            "observations": [
                                {
                                    "kind": "visual_fact",
                                    "metadata_key": None,
                                    "text": "A gray square fills the image.",
                                }
                            ]
                        },
                    }
                ],
            },
        )

    with Anthropic(
        api_key="offline-test-key",
        http_client=httpx2.Client(
            transport=httpx2.MockTransport(handler),
        ),
    ) as client:
        observations = AnthropicObserver(taxonomy, model="test-model", client=client).observe(
            evidence,
            image=data,
        )
    assert observations[0].text == "A gray square fills the image."
    assert observations[0].observer_model == "resolved-vision-version"
