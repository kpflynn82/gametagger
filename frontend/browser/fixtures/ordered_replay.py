"""Scripted response ONLY for the synthetic browser test video. No network calls."""

import json
import sys

from gametagger.observers.anthropic_ordered import PROMPT_SHA256, PROMPT_VERSION, request_digest
from gametagger.observers.ordered import OrderedWindow, WindowAttempt, WindowOutput, digest

request = json.load(sys.stdin)
attempts = []
for i, view in enumerate(request["windows"][:2]):
    window = OrderedWindow.model_validate(
        {k: v for k, v in view.items() if k not in {"asset_id", "frame_indices", "window_sha256"}}
    )
    output = WindowOutput(
        context="unknown",
        observations=[
            {
                "kind": "visual_fact",
                "text": "Colored bars fill the sampled image.",
                "frame_ids": [window.frames[0].evidence_id],
                "image_region": None,
            }
        ],
    )
    attempts.append(
        WindowAttempt(
            status="valid" if i == 0 else "error",
            window_sha256=window.sha256,
            request_sha256=request_digest(window, "synthetic-ui-fixture"),
            prompt_version=PROMPT_VERSION,
            prompt_sha256=PROMPT_SHA256,
            requested_model="synthetic-ui-fixture",
            returned_model="synthetic-ui-fixture",
            sdk_version="ui-test-not-provider",
            response_sha256=digest(output.model_dump(mode="json")),
            output_sha256=digest(output.model_dump(mode="json")) if i == 0 else None,
            output=output if i == 0 else None,
            error_code="observation_contract" if i else None,
            usage=None,
            latency_ms=None,
        ).model_dump(mode="json")
    )
json.dump(
    {
        "schema_version": "ordered-observation-replay-v1",
        "kind": "illustrative",
        "input_sha256": request["input_sha256"],
        "taxonomy_sha256": request["taxonomy_sha256"],
        "attempts": attempts,
    },
    sys.stdout,
)
