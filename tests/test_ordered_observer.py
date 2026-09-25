import base64
import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx2
import pytest
from anthropic import Anthropic
from PIL import Image

from gametagger.observers.anthropic_ordered import (
    PROMPT_SHA256,
    PROMPT_VERSION,
    AnthropicOrderedObserver,
    request_digest,
)
from gametagger.observers.ordered import OrderedWindow, TimedFrame, WindowOutput


def samples():
    frames = []
    for color in ("black", "gray", "white"):
        out = io.BytesIO()
        Image.new("RGB", (64, 48), color).save(out, format="JPEG")
        frames.append(out.getvalue())
    return frames


def window(frames):
    return OrderedWindow(
        source_asset_sha256="a" * 64,
        duration_seconds=2,
        selection_strategy="synthetic-test",
        frames=[
            TimedFrame(
                evidence_id=f"frame-{i}",
                asset_sha256="a" * 64,
                frame_sha256=hashlib.sha256(data).hexdigest(),
                timestamp_seconds=0.2 * i,
            )
            for i, data in enumerate(frames)
        ],
    )


def payload():
    return {
        "context": "unknown",
        "observations": [
            {
                "kind": "sequence_fact",
                "text": "The rectangle is darker in the first sample and lighter in the next.",
                "frame_ids": ["frame-0", "frame-1"],
                "image_region": None,
            },
            {
                "kind": "visual_text",
                "text": "Merge",
                "frame_ids": ["frame-1"],
                "image_region": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.1},
            },
        ],
    }


def test_real_sdk_transport_uses_exact_ordered_frames_without_identity_and_records_usage(taxonomy):
    frames = samples()
    w = window(frames)

    def handler(request):
        body = json.loads(request.content)
        content = body["messages"][0]["content"]
        assert [
            base64.b64decode(c["source"]["data"]) for c in content if c["type"] == "image"
        ] == frames
        assert "timestamp 0.200000s" in content[2]["text"]
        assert "source_metadata" not in request.content.decode()
        assert body["tool_choice"]["name"] == "record_window_observations"
        assert body["tools"][0]["input_schema"]["additionalProperties"] is False
        return httpx2.Response(
            200,
            headers={"request-id": "private-request-id"},
            json={
                "id": "synthetic",
                "type": "message",
                "role": "assistant",
                "model": "resolved-offline-test",
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 123, "output_tokens": 45},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool",
                        "name": "record_window_observations",
                        "input": payload(),
                    }
                ],
            },
        )

    with Anthropic(
        api_key="offline-key",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
    ) as client:
        result = AnthropicOrderedObserver(
            taxonomy, model="requested-test", client=client
        ).observe_window(w, frames=frames)
    assert result.status == "valid", result
    assert result.requested_model == "requested-test"
    assert result.returned_model == "resolved-offline-test"
    assert result.usage["input_tokens"] == 123 and result.usage["output_tokens"] == 45
    assert result.latency_ms >= 0 and result.request_id_sha256
    assert result.request_sha256 == request_digest(w, "requested-test")
    assert result.prompt_version == PROMPT_VERSION and result.prompt_sha256 == PROMPT_SHA256
    assert result.output.observations[1].text == "Merge"


@pytest.mark.parametrize(
    "change",
    [
        {
            "kind": "sequence_fact",
            "text": "This is a parry mechanic",
            "frame_ids": ["frame-0", "frame-1"],
        },
        {"kind": "sequence_fact", "text": "A shape moves.", "frame_ids": ["frame-0"]},
        {"kind": "sequence_fact", "text": "A shape moves.", "frame_ids": ["frame-0", "frame-2"]},
        {"kind": "visual_fact", "text": "Action RPG", "frame_ids": ["frame-0"]},
        {"kind": "visual_text", "text": "Survival", "frame_ids": ["frame-0"]},
        {"kind": "visual_fact", "text": "A shape.", "frame_ids": ["not-supplied"]},
        {"kind": "visual_fact", "text": "A shape.", "frame_ids": ["frame-1", "frame-0"]},
    ],
)
def test_temporal_and_classifier_boundary(taxonomy, change):
    with pytest.raises(ValueError):
        WindowOutput(context="unknown", observations=[change]).validate_against(
            window(samples()), taxonomy
        )


def test_wrong_bytes_and_no_spending_before_client_creation(taxonomy, monkeypatch):
    frames = samples()
    client = Mock()
    observer = AnthropicOrderedObserver(taxonomy, model="test", client=client)
    with pytest.raises(ValueError, match="hash"):
        observer.observe_window(window(frames), frames=list(reversed(frames)))
    client.messages.create.assert_not_called()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "available-is-not-authorized")
    with pytest.raises(ValueError, match="disabled"):
        AnthropicOrderedObserver(taxonomy, model="test").observe_window(
            window(frames), frames=frames
        )


def test_cross_window_gaps_rejected():
    w = window(samples()).model_dump()
    w["frames"][2]["timestamp_seconds"] = 1.9
    with pytest.raises(ValueError, match="gaps"):
        OrderedWindow.model_validate(w)


def test_failed_window_preserves_usage_and_next_independent_answer(taxonomy):
    from types import SimpleNamespace as NS

    frames = samples()
    client = Mock()
    invalid = payload()
    invalid["observations"][0]["text"] = "Souls-like"

    def response(output):
        return NS(
            model="resolved",
            stop_reason="tool_use",
            usage=NS(input_tokens=90, output_tokens=30),
            content=[NS(type="tool_use", name="record_window_observations", input=output)],
        )

    client.messages.create.side_effect = [
        response(invalid),
        response(payload()),
        RuntimeError("private error"),
    ]
    observer = AnthropicOrderedObserver(taxonomy, model="test", client=client)
    a, b, c = [observer.observe_window(window(frames), frames=frames) for _ in range(3)]
    assert a.status == "error" and a.error_code == "observation_contract" and a.output is None
    assert a.usage["input_tokens"] == 90 and a.response_sha256
    assert b.status == "valid"
    assert c.status == "error" and c.error_code == "transport" and c.usage is None
    assert "private error" not in c.model_dump_json()
    assert client.messages.create.call_count == 3  # No hidden retries.


@pytest.mark.parametrize(
    "model, tokens", [(None, 10), ("resolved", -1), ("resolved", float("nan"))]
)
def test_malformed_model_or_usage_is_a_provider_failure(taxonomy, model, tokens):
    from types import SimpleNamespace as NS

    frames = samples()
    client = Mock()
    client.messages.create.return_value = NS(model=model, usage=NS(input_tokens=tokens))
    attempt = AnthropicOrderedObserver(taxonomy, model="test", client=client).observe_window(
        window(frames), frames=frames
    )
    assert attempt.status == "error" and attempt.error_code == "provider_contract"
    assert attempt.output is None


def test_lenient_window_quarantines_malformed_statements_and_keeps_the_rest(taxonomy):
    frames = samples()
    reply = payload()
    region = {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.1}
    reply["observations"] += [
        {"kind": "visual_fact", "text": "Two frames at once.", "frame_ids": ["frame-0", "frame-1"]},
        {
            "kind": "visual_fact",
            "text": "A tree.",
            "frame_ids": ["frame-2"],
            "image_region": region,
        },
        {"kind": "visual_text", "text": "GO", "frame_ids": ["frame-2"]},
    ]
    usage = SimpleNamespace(
        input_tokens=1, output_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0
    )
    block = SimpleNamespace(type="tool_use", name="record_window_observations", input=reply)
    client = Mock()
    client.messages.create.return_value = SimpleNamespace(
        model="m", stop_reason="tool_use", usage=usage, content=[block]
    )
    strict = AnthropicOrderedObserver(taxonomy, model="test", client=client)
    assert strict.observe_window(window(frames), frames=frames).status == "error"
    lenient = AnthropicOrderedObserver(
        taxonomy, model="test", client=client, enforce_boundary=False
    )
    attempt = lenient.observe_window(window(frames), frames=frames)
    assert attempt.status == "valid"
    texts = [s.text for s in attempt.output.observations]
    assert texts[:2] == [o["text"] for o in payload()["observations"]] and texts[2] == "A tree."
    assert attempt.output.observations[2].image_region is None
    assert [q["text"] for q in lenient.last_quarantined] == ["Two frames at once.", "GO"]
