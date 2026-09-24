"""Bounded ordered-frame observations; timestamps describe samples, not hidden events."""

import hashlib
import json
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gametagger.domain import EvidenceItem, EvidenceType, ImageRegion, Observation
from gametagger.observers.boundary import ObservationBoundary

Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TimedFrame(Contract):
    evidence_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9:_.-]+$")
    asset_sha256: Hash
    frame_sha256: Hash
    timestamp_seconds: float = Field(ge=0)


class OrderedWindow(Contract):
    source_asset_sha256: Hash
    # Source length. Website uploads are capped at 60 s in workspace.media; rich mode samples
    # store trailers, which are longer. Each window's own frames stay at most 0.5 s apart.
    duration_seconds: float = Field(gt=0, le=1800)
    selection_strategy: str = Field(min_length=1, max_length=120)
    frames: list[TimedFrame] = Field(min_length=2, max_length=12)
    # Sampling limit, not proof that all intermediate events are visible.
    maximum_gap_seconds: float = Field(default=0.5, gt=0, le=0.5)

    @model_validator(mode="after")
    def ordered(self):
        times = [f.timestamp_seconds for f in self.frames]
        if (
            any(
                a >= b or b - a > self.maximum_gap_seconds + 1e-6
                for a, b in zip(times, times[1:], strict=False)
            )
            or times[-1] > self.duration_seconds
        ):
            raise ValueError("Frames require ordered, in-range timestamps without sampling gaps")
        if len({f.evidence_id for f in self.frames}) != len(self.frames):
            raise ValueError("Frame IDs must be unique")
        if any(f.asset_sha256 != self.source_asset_sha256 for f in self.frames):
            raise ValueError("Frames must come from the same source asset")
        return self

    @property
    def sha256(self):
        return digest(self.model_dump(mode="json"))


class WindowStatement(Contract):
    kind: Literal["visual_fact", "visual_text", "sequence_fact"]
    text: str = Field(min_length=1, max_length=2000)
    frame_ids: list[str] = Field(min_length=1, max_length=12)
    image_region: ImageRegion | None = None


class WindowOutput(Contract):
    # This is the Observer's proposed context, never a human gameplay certification.
    context: Literal[
        "gameplay", "menu", "cinematic", "title_card", "creator_overlay", "mixed", "unknown"
    ]
    observations: list[WindowStatement] = Field(max_length=32)

    def validate_against(self, window: OrderedWindow, taxonomy, *, enforce_boundary=True):
        """Check frame references; with ``enforce_boundary`` also reject taxonomy words.

        Rich mode passes False and quarantines individual statements itself instead.
        """
        positions = {f.evidence_id: i for i, f in enumerate(window.frames)}
        boundary = ObservationBoundary(taxonomy)
        for n, s in enumerate(self.observations):
            if any(i not in positions for i in s.frame_ids):
                raise ValueError("Unknown frame reference")
            indices = [positions[i] for i in s.frame_ids]
            if indices != sorted(set(indices)):
                raise ValueError("Statement frame references must be distinct and ordered")
            if s.kind == "sequence_fact":
                if len(indices) < 2 or indices != list(range(indices[0], indices[-1] + 1)):
                    raise ValueError("Sequence facts need consecutive supplied frames")
            elif len(indices) != 1:
                raise ValueError("Still facts/text must refer to exactly one frame")
            if not enforce_boundary:
                continue
            evidence = EvidenceItem(
                id=s.frame_ids[0], type=EvidenceType.GAMEPLAY_IMAGE, source="ordered-frame"
            )
            boundary.validate(
                [
                    Observation(
                        id=str(n),
                        evidence_id=evidence.id,
                        kind="visual_text" if s.kind == "visual_text" else "visual_fact",
                        text=s.text,
                        image_region=s.image_region,
                        observer_model="boundary-check",
                    )
                ],
                evidence,
            )
        return self


class WindowAttempt(Contract):
    status: Literal["valid", "error"]
    window_sha256: Hash
    request_sha256: Hash
    prompt_version: str
    prompt_sha256: Hash
    requested_model: str = Field(min_length=1, max_length=160)
    returned_model: str | None = Field(default=None, max_length=160)
    sdk_version: str = Field(max_length=80)
    request_id_sha256: Hash | None = None
    response_sha256: Hash | None = None
    output_sha256: Hash | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    usage: (
        dict[
            Literal[
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            ],
            Annotated[int | None, Field(ge=0, strict=True)],
        ]
        | None
    ) = None
    error_code: Literal["transport", "provider_contract", "observation_contract"] | None = None
    output: WindowOutput | None = None

    @model_validator(mode="after")
    def execution_is_not_semantics(self):
        if self.status == "valid" and (
            not self.returned_model
            or self.output is None
            or self.error_code
            or not self.response_sha256
        ):
            raise ValueError("A valid attempt requires a returned model and valid output")
        if self.output is not None and self.output_sha256 != digest(
            self.output.model_dump(mode="json")
        ):
            raise ValueError("Saved structured output hash does not match")
        if self.status == "error" and (self.output is not None or self.error_code is None):
            raise ValueError("A failed attempt has an error, never semantic observations")
        return self


class OrderedObserver(Protocol):
    model: str
    prompt_version: str

    def observe_window(self, window: OrderedWindow, *, frames: list[bytes]) -> WindowAttempt: ...
