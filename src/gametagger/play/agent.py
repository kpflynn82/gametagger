"""Claude chooses one action at a time from the current screenshot.

The agent sees one screenshot per turn (never the whole history of images, which would multiply
the cost) plus a short text log of its last actions, the goals still open and any warnings from
the safety checks. It answers through a single tool, ``act``, whose arguments are validated
before anything touches the device.

The player is not the Observer and never tags. Its ``screen`` label says which part of the
game it believes it is on (shop, event, ...). That label is kept as navigation context for the
recording, and the Observer still describes the frames on its own.
"""

from __future__ import annotations

import base64
import io
from typing import Any, Literal, get_args

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from gametagger.genome.dossier import CaptureContext

PROMPT_VERSION = "android-player-v1"
MODEL_IMAGE_SIDE = 1024  # screenshots are shrunk to this before being sent

GOALS: dict[str, str] = {
    "shop": "Open the shop or store screen and scroll through what it sells.",
    "currency": "Open a screen that shows the game's currencies, wallet or premium currency.",
    "event": "Open a limited-time event, season, pass or daily-reward screen.",
    "social": "Open a social screen: guild, clan, alliance, friends, chat or leaderboard.",
    "progression": "Open an upgrade, collection, character, deck or base-building menu.",
    "ad": "If the game offers an optional ad for a reward, watch one ad to the end.",
}

SYSTEM_PROMPT = f"""You are an automated game tester for GameTagger, a catalog that describes
mobile games. You are playing one Android game on an emulator. A screen recording of your
session is used later as evidence of what the game contains, so your job is to reach and show
the game's screens, not to win.

The session has two phases:
1. First session: play the game normally from the start, following any tutorial, as a new
   player would. Do this until the phase changes.
2. Explore systems: reach each open goal below at least once, staying a few seconds on each
   screen and scrolling it if it has more content. Go back to normal play between goals.

Goals: {"; ".join(f"{k}: {v}" for k, v in GOALS.items())}

Every turn you see the current screenshot and call the act tool exactly once.
Coordinates are on a 0-1000 grid over the screenshot: x=0 is the left edge, x=1000 the right
edge, y=0 the top, y=1000 the bottom. Aim at the centre of the button.

Rules you must always follow:
- Never buy anything. Do not tap prices, "Buy", "Purchase" or payment buttons; if a payment or
  Google Play purchase sheet appears, press back. Looking at the shop is fine; paying is not.
- Never sign in, link or create an account (Google, Facebook, Apple, email). Choose guest play
  or skip. Never change phone settings.
- Never write in chat, send messages or friend requests, or post anything. Only type a short
  player name (letters and digits) when the game requires one to continue.
- If a terms, privacy or age screen blocks play, accept it (choose an adult age).
- For permission requests (notifications, location, contacts) choose deny or "don't allow".
- If an ad is playing, wait for it; then close it with its X or skip button. Never tap an ad's
  install or "learn more" button. If you land in the Play Store or a browser, press back.
- If the screen has not changed after your last actions, try something different: a different
  button, back, or a swipe.

In the screen field, say which part of the game the current screenshot shows. In goals_reached,
list goals whose screen is visible right now. Keep note to one short sentence.
"""

Action = Literal["tap", "long_press", "swipe", "back", "wait", "type_text", "done"]
SCREENS = list(get_args(CaptureContext))

ACT_TOOL = {
    "name": "act",
    "description": "Perform one action on the game.",
    "input_schema": {
        "type": "object",
        "properties": {
            "screen": {"type": "string", "enum": SCREENS},
            "action": {"type": "string", "enum": list(get_args(Action))},
            "x": {"type": "integer", "minimum": 0, "maximum": 1000},
            "y": {"type": "integer", "minimum": 0, "maximum": 1000},
            "x2": {"type": "integer", "minimum": 0, "maximum": 1000},
            "y2": {"type": "integer", "minimum": 0, "maximum": 1000},
            "text": {"type": "string", "maxLength": 16},
            "seconds": {"type": "number", "minimum": 1, "maximum": 10},
            "goals_reached": {"type": "array", "items": {"type": "string", "enum": list(GOALS)}},
            "note": {"type": "string", "maxLength": 200},
        },
        "required": ["screen", "action", "note"],
    },
}


class PlayerAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    screen: CaptureContext
    action: Action
    x: int | None = Field(default=None, ge=0, le=1000)
    y: int | None = Field(default=None, ge=0, le=1000)
    x2: int | None = Field(default=None, ge=0, le=1000)
    y2: int | None = Field(default=None, ge=0, le=1000)
    text: str | None = Field(default=None, max_length=16)
    seconds: float | None = Field(default=None, ge=1, le=10)
    goals_reached: list[str] = Field(default_factory=list)
    note: str = Field(default="", max_length=400)

    @model_validator(mode="after")
    def needs_points(self):
        if self.action in {"tap", "long_press", "swipe"} and (self.x is None or self.y is None):
            raise ValueError(f"{self.action} needs x and y")
        if self.action == "swipe" and (self.x2 is None or self.y2 is None):
            raise ValueError("swipe needs x2 and y2")
        if self.action == "type_text" and not self.text:
            raise ValueError("type_text needs text")
        self.goals_reached = [g for g in self.goals_reached if g in GOALS]
        return self


def model_image(png: bytes) -> tuple[bytes, tuple[int, int]]:
    """A JPEG of the screenshot, at most MODEL_IMAGE_SIDE on its long side; and device size."""
    with Image.open(io.BytesIO(png)) as image:
        size = image.size
        rgb = image.convert("RGB")
    rgb.thumbnail((MODEL_IMAGE_SIDE, MODEL_IMAGE_SIDE))
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=75)
    return out.getvalue(), size


def to_device(value: int, size: int) -> int:
    """0-1000 grid position to a device pixel."""
    return round(value / 1000 * (size - 1))


class PlayAgent:
    def __init__(
        self,
        client,
        *,
        model: str,
        workspace_id: str | None = None,
        max_tokens: int = 400,
    ):
        self.client, self.model = client, model
        self.workspace_id, self.max_tokens = workspace_id, max_tokens
        self.last_usage: dict[str, Any] | None = None

    def decide(self, screenshot_png: bytes, situation: str) -> PlayerAction:
        """One action for this screenshot. Raises ValueError on a malformed answer."""
        jpeg, _ = model_image(screenshot_png)
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            tools=[ACT_TOOL],
            tool_choice={"type": "tool", "name": "act"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.b64encode(jpeg).decode(),
                            },
                        },
                        {"type": "text", "text": situation},
                    ],
                }
            ],
        )
        if self.workspace_id:
            kwargs["extra_headers"] = {"anthropic-workspace-id": self.workspace_id}
        response = self.client.messages.create(**kwargs)
        usage = getattr(response, "usage", None)
        self.last_usage = (
            {k: getattr(usage, k, None) for k in ("input_tokens", "output_tokens")}
            if usage is not None
            else None
        )
        block = next(
            (
                b
                for b in getattr(response, "content", []) or []
                if getattr(b, "type", None) == "tool_use" and getattr(b, "name", None) == "act"
            ),
            None,
        )
        if block is None:
            raise ValueError("The model did not call the act tool")
        try:
            return PlayerAction.model_validate(block.input)
        except ValidationError as exc:
            raise ValueError(f"Malformed action: {exc.errors()[0]['msg']}") from None
