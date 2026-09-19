"""Private, immutable saved-window replay. Hash agreement is not provider authentication."""

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from gametagger.observers.anthropic_ordered import (
    PROMPT_SHA256,
    PROMPT_VERSION,
    request_digest,
    validate_frames,
)
from gametagger.observers.ordered import Contract, Hash, OrderedWindow, TimedFrame, WindowAttempt


class ObservationReplay(Contract):
    schema_version: Literal["ordered-observation-replay-v1"] = "ordered-observation-replay-v1"
    input_sha256: Hash
    taxonomy_sha256: Hash
    kind: Literal["saved_provider", "illustrative"]
    attempts: list[WindowAttempt] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def one_attempt_per_window(self):
        if len({a.window_sha256 for a in self.attempts}) != len(self.attempts):
            raise ValueError("One retained attempt per window; no confidence-based selection")
        return self


class ReplayCreate(Contract):
    idempotency_key: str = Field(min_length=8, max_length=100)
    replay: ObservationReplay


def prepared_windows(assets):
    """Never bridge different sampling windows or gaps. Return only observable pairs."""
    output = []
    for asset in assets:
        video = asset.get("video")
        if not video:
            continue
        seen = set()
        for start in video["window_starts"]:
            selected = [
                (i, f)
                for i, f in enumerate(video["frames"])
                if start - 1e-6 <= f["timestamp"] <= start + video["window_length_seconds"] + 1e-6
            ]
            groups = []
            for pair in selected:
                if (
                    not groups
                    or pair[1]["timestamp"] - groups[-1][-1][1]["timestamp"] > 0.5 + 1e-6
                    or len(groups[-1]) >= 12
                ):
                    groups.append([])
                groups[-1].append(pair)
            for group in groups:
                if len(group) < 2:
                    continue
                window = OrderedWindow(
                    source_asset_sha256=asset["sha256"],
                    duration_seconds=video["duration"],
                    selection_strategy=video["strategy"],
                    frames=[
                        TimedFrame(
                            evidence_id=f"{asset['id']}:frame:{i}",
                            asset_sha256=asset["sha256"],
                            frame_sha256=f["sha256"],
                            timestamp_seconds=f["timestamp"],
                        )
                        for i, f in group
                    ],
                )
                if window.sha256 not in seen:
                    output.append((asset, group, window))
                    seen.add(window.sha256)
    return output


def window_views(assets):
    return [
        {
            "asset_id": a["id"],
            "window_sha256": w.sha256,
            "frame_indices": [i for i, _ in group],
            **w.model_dump(mode="json"),
        }
        for a, group, w in prepared_windows(assets)
    ]


def validate_replay(bundle, run, store, taxonomy, current_taxonomy_sha):
    if run["status"] != "partial" or run["snapshot"]["identity_status"] != "associated_project":
        raise ValueError("Replay requires a prepared, identity-associated parent run")
    if bundle.input_sha256 != run["input_hash"] or bundle.taxonomy_sha256 != current_taxonomy_sha:
        raise ValueError("Replay input/taxonomy provenance does not match")
    if run["result"]["provenance"]["taxonomy_sha256"] != current_taxonomy_sha:
        raise ValueError("Parent taxonomy changed; prepare a new evidence version")
    if bundle.kind == "illustrative" and run["snapshot"]["entry"] != "demo":
        raise ValueError("Illustrative replay belongs only to a demo project")
    # Verify original assets as well as exact prepared frame bytes before attaching saved output.
    for asset in run["assets"]:
        if (
            hashlib.sha256((store.assets / asset["file"]).read_bytes()).hexdigest()
            != asset["sha256"]
        ):
            raise ValueError("Saved source asset changed")
    available = {w.sha256: (a, group, w) for a, group, w in prepared_windows(run["assets"])}
    observations, executions = [], []
    for attempt in bundle.attempts:
        if attempt.window_sha256 not in available:
            raise ValueError("Replay refers to an unknown or changed observation window")
        asset, group, window = available[attempt.window_sha256]
        if (
            attempt.prompt_version != PROMPT_VERSION
            or attempt.prompt_sha256 != PROMPT_SHA256
            or attempt.request_sha256 != request_digest(window, attempt.requested_model)
        ):
            raise ValueError("Replay model/prompt/request provenance does not match")
        frames = [
            (store.assets / asset["frame_directory"] / f["file"]).read_bytes() for _, f in group
        ]
        validate_frames(window, frames)
        if attempt.output is not None:
            attempt.output.validate_against(window, taxonomy)
            lookup = {f.evidence_id: f for f in window.frames}
            for n, statement in enumerate(attempt.output.observations):
                observations.append(
                    {
                        "id": f"{window.sha256}:observation:{n}",
                        "evidence_id": asset["id"],
                        **statement.model_dump(mode="json"),
                        "timestamp_start": lookup[statement.frame_ids[0]].timestamp_seconds,
                        "timestamp_end": lookup[statement.frame_ids[-1]].timestamp_seconds,
                        "observer_model": attempt.returned_model,
                        "window_sha256": window.sha256,
                        "context": attempt.output.context,
                        "provenance_status": "Imported saved claim; not human-verified",
                        "support_status": "Context only; no classification support assessed",
                    }
                )
        executions.append(
            {
                "window_sha256": window.sha256,
                "status": attempt.status,
                "error_code": attempt.error_code,
            }
        )
    supplied = {a.window_sha256 for a in bundle.attempts}
    executions.extend(
        {"window_sha256": h, "status": "not_evaluated", "error_code": None}
        for h in available
        if h not in supplied
    )
    return observations, executions
