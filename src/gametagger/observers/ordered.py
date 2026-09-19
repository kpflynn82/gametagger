"""Experimental ordered-frame input contract; a still observer cannot assert temporal facts."""

from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from gametagger.domain import Observation


class TimedFrame(BaseModel):
    evidence_id: str
    asset_sha256: str
    frame_sha256: str
    timestamp_seconds: float = Field(ge=0, allow_inf_nan=False)


class OrderedWindow(BaseModel):
    source_asset_sha256: str
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    selection_strategy: str
    frames: list[TimedFrame] = Field(min_length=2, max_length=48)
    context: str = "unreviewed; gameplay/menu/cinematic/overlay unknown"

    @model_validator(mode="after")
    def ordered(self):
        times = [f.timestamp_seconds for f in self.frames]
        if (
            any(a >= b for a, b in zip(times, times[1:], strict=False))
            or times[-1] > self.duration_seconds
        ):
            raise ValueError("Frames require strictly ordered, in-range presentation timestamps")
        if any(f.asset_sha256 != self.source_asset_sha256 for f in self.frames):
            raise ValueError("Frames must come from the same source asset")
        return self


class OrderedObserver(Protocol):
    model: str
    prompt_version: str

    def observe_window(
        self, window: OrderedWindow, *, frames: list[bytes]
    ) -> list[Observation]: ...
