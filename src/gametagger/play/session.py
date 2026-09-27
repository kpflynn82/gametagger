"""One automated play session: launch the game, let the agent play, record, and hand off.

What comes out, in ``<out>/<package>/<time>/``:

* ``recording.mp4``: the screen recording, joined and at a constant 10 frames a second.
* ``dossier.json``: a dossier-v1 file with the recording as a ``gameplay_recording`` video and
  the player's screen labels as capture contexts. ``gametagger-genome dossier.json`` tags it.
* ``steps.jsonl``: every action with its time, screen label, reason and safety events.
* ``screens/``: the screenshot the agent saw at each step (small JPEGs).
* ``session.json``: a summary: device, model, goals reached, why it stopped, cost.

All of it is third-party game content and stays out of git (``gametagger-play/`` is ignored).

Safety checks run in code, not only in the prompt. Before every step the app in front is
checked: a purchase screen is closed with the back button, and leaving the game (an ad's
link, the Play Store, a sign-in sheet) is undone with back and, if needed, a relaunch.
"""

from __future__ import annotations

import io
import json
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from gametagger.comparison.budget import BudgetExceeded
from gametagger.genome.dossier import CaptureSegment, Dossier, ImageSource, VideoSource
from gametagger.genome.media import sha256
from gametagger.genome.systems import average_hash, hamming
from gametagger.play.agent import GOALS, PROMPT_VERSION, PlayAgent, PlayerAction, model_image
from gametagger.play.agent import to_device as grid
from gametagger.play.device import AdbDevice, AdbError, Foreground, ScreenRecorder, join_recording

PURCHASE_WORDS = ("billing", "purchase", "acquire", "payment", "wallet", "checkout")
# System screens the agent may answer itself (it is told to deny permissions).
ALLOWED_OTHER_PACKAGES = {
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
}
MAX_MODEL_ERRORS = 5
MAX_FALLBACK_SCREENSHOTS = 12


@dataclass
class PlayConfig:
    package: str
    title: str | None = None
    minutes: float = 12.0
    first_session_minutes: float = 5.0
    max_steps: int = 200
    settle_seconds: float = 1.5
    record: bool = True
    launch_wait_seconds: float = 8.0

    def __post_init__(self):
        if not 1 <= self.minutes <= 14:
            raise ValueError("Play between 1 and 14 minutes (recordings are sampled up to 15)")
        if not 0 <= self.first_session_minutes < self.minutes:
            raise ValueError("The first-session phase must be shorter than the whole session")
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")


@dataclass
class StepRecord:
    step: int
    seconds: float
    recording_seconds: float | None
    phase: str
    screen: str | None
    action: dict[str, Any] | None
    note: str
    foreground: str
    events: list[str] = field(default_factory=list)
    error: str | None = None
    usage: dict[str, Any] | None = None


@dataclass
class SessionResult:
    directory: Path
    stop_reason: str
    steps: list[StepRecord]
    goals_reached: dict[str, float]
    dossier_path: Path | None
    recording_path: Path | None
    cost_usd: float
    warnings: list[str]


class PlaySession:
    def __init__(
        self,
        device: AdbDevice,
        agent: PlayAgent,
        config: PlayConfig,
        out_dir: Path,
        *,
        meter=None,
        recorder: ScreenRecorder | None = None,
        joiner: Callable[..., Path] = join_recording,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.device, self.agent, self.config = device, agent, config
        self.meter = meter
        self.clock, self.sleep = clock, sleep
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.directory = out_dir / config.package / stamp
        self.recorder = recorder if recorder is not None else (
            ScreenRecorder(device, clock=clock) if config.record else None
        )  # fmt: skip
        self.joiner = joiner
        self.steps: list[StepRecord] = []
        self.goals: dict[str, float] = {}
        self.warnings: list[str] = []
        self._outside = 0
        self._shots: list[tuple[int, bytes, str | None]] = []  # (hash, jpeg, screen)

    # ------------------------------------------------------------------ safety

    def guard(self, fg: Foreground) -> list[str]:
        """Undo purchase screens and trips out of the game. Returns what was done."""
        events = []
        activity = (fg.activity or "").lower()
        if fg.package and any(w in activity for w in PURCHASE_WORDS):
            self.device.back()
            self.sleep(1.0)
            self.device.back()
            events.append(f"purchase_screen_closed ({fg.text})")
            return events
        if (
            fg.package
            and fg.package != self.config.package
            and fg.package not in ALLOWED_OTHER_PACKAGES
        ):
            self._outside += 1
            if self._outside >= 3:
                self.device.launch(self.config.package)
                self.sleep(self.config.launch_wait_seconds)
                events.append(f"relaunched_game (was in {fg.package})")
                self._outside = 0
            else:
                self.device.back()
                self.sleep(1.0)
                events.append(f"left_game_back ({fg.package})")
        else:
            self._outside = 0
        return events

    # ------------------------------------------------------------------ actions

    def apply(self, action: PlayerAction, size: tuple[int, int]) -> None:
        w, h = size
        if action.action == "tap":
            self.device.tap(grid(action.x, w), grid(action.y, h))
        elif action.action == "long_press":
            self.device.long_press(grid(action.x, w), grid(action.y, h))
        elif action.action == "swipe":
            self.device.swipe(
                grid(action.x, w), grid(action.y, h), grid(action.x2, w), grid(action.y2, h)
            )
        elif action.action == "back":
            self.device.back()
        elif action.action == "type_text":
            self.device.type_text(action.text or "")

    # ------------------------------------------------------------------ the loop

    def situation(self, elapsed: float, phase: str, warnings: list[str]) -> str:
        c = self.config
        open_goals = [g for g in GOALS if g not in self.goals]
        lines = [
            f"Minute {elapsed / 60:.1f} of {c.minutes:g}. Phase: {phase}.",
            (
                "Play normally; goals come later."
                if phase == "first session"
                else f"Goals still open: {', '.join(open_goals) or 'none (keep playing)'}."
            ),
        ]
        recent = [s for s in self.steps if s.action][-10:]
        if recent:
            lines.append("Your recent actions, oldest first:")
            for s in recent:
                a = s.action or {}
                where = f" ({a['x']}, {a['y']})" if a.get("x") is not None else ""
                lines.append(
                    f"- {s.seconds / 60:.1f} min, {s.screen}: {a['action']}{where}: {s.note}"
                )
        if warnings:
            lines.append("Warnings: " + " ".join(warnings))
        return "\n".join(lines)

    def _stuck(self, image_hash: int) -> bool:
        recent = self._shots[-3:]
        acted = [s for s in self.steps[-3:] if s.action and s.action["action"] != "wait"]
        return (
            len(recent) == 3
            and len(acted) == 3
            and all(hamming(image_hash, h) <= 2 for h, _, _ in recent)
        )

    def run(self) -> SessionResult:
        c = self.config
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "screens").mkdir(exist_ok=True)
        self.device.launch(c.package)
        self.sleep(c.launch_wait_seconds)
        if self.recorder:
            self.recorder.start()
        start = self.clock()
        stop_reason, model_errors = "time", 0
        pending: deque[str] = deque(maxlen=4)
        try:
            for step in range(1, c.max_steps + 1):
                elapsed = self.clock() - start
                phase = "first session" if elapsed < c.first_session_minutes * 60 else "explore"
                if elapsed >= c.minutes * 60:
                    stop_reason = "time"
                    break
                if phase == "explore" and all(g in self.goals for g in GOALS):
                    stop_reason = "all_goals_reached"
                    break
                fg = self.device.foreground()
                events = self.guard(fg)
                pending.extend(events)
                if events:
                    fg = self.device.foreground()
                png = self.device.screenshot()
                shot_at = self.clock()
                jpeg, size = model_image(png)
                with Image.open(io.BytesIO(jpeg)) as im:
                    image_hash = average_hash(im.convert("L").resize((8, 8)).tobytes())
                if self._stuck(image_hash):
                    pending.append("The screen has not changed after your last 3 actions.")
                (self.directory / "screens" / f"step-{step:03d}.jpg").write_bytes(jpeg)
                record = StepRecord(
                    step=step,
                    seconds=round(shot_at - start, 2),
                    recording_seconds=(
                        round(t, 2)
                        if self.recorder
                        and (t := self.recorder.recording_time(shot_at)) is not None
                        else None
                    ),
                    phase=phase,
                    screen=None,
                    action=None,
                    note="",
                    foreground=fg.text,
                    events=events,
                )
                self.steps.append(record)
                try:
                    action = self.agent.decide(png, self.situation(elapsed, phase, list(pending)))
                except BudgetExceeded as exc:  # the cap, or the account has no credit
                    record.error = str(exc)
                    stop_reason = "budget"
                    break
                except ValueError as exc:
                    record.error = str(exc)
                    record.usage = self.agent.last_usage
                    model_errors += 1
                    if model_errors >= MAX_MODEL_ERRORS:
                        stop_reason = "model_errors"
                        break
                    self.sleep(1.0)
                    continue
                pending.clear()
                model_errors = 0
                record.usage = self.agent.last_usage
                record.screen, record.note = action.screen, action.note
                record.action = action.model_dump(
                    include={"action", "x", "y", "x2", "y2", "text", "seconds"}, exclude_none=True
                )
                self._shots.append((image_hash, jpeg, action.screen))
                for goal in [*action.goals_reached, action.screen]:
                    if goal in GOALS and goal not in self.goals and phase == "explore":
                        self.goals[goal] = record.seconds
                if action.action == "done" and phase == "explore":
                    stop_reason = "agent_done"
                    break
                try:
                    self.apply(action, size)
                except (ValueError, AdbError) as exc:
                    record.error = f"Action not performed: {exc}"
                self.sleep(action.seconds if action.action == "wait" else c.settle_seconds)
            else:
                stop_reason = "max_steps"
        except KeyboardInterrupt:
            stop_reason = "stopped_by_you"
        finally:
            recording = self._finish_recording()
        dossier_path = self._write_outputs(recording, stop_reason)
        return SessionResult(
            directory=self.directory,
            stop_reason=stop_reason,
            steps=self.steps,
            goals_reached=self.goals,
            dossier_path=dossier_path,
            recording_path=recording,
            cost_usd=self.cost(),
            warnings=self.warnings,
        )

    # ------------------------------------------------------------------ outputs

    def cost(self) -> float:
        if self.meter is None:
            return 0.0
        return round(sum(c.get("cost_usd") or 0.0 for c in self.meter.calls), 4)

    def _finish_recording(self) -> Path | None:
        if not self.recorder:
            return None
        try:
            parts = self.recorder.stop(self.directory / "segments")
            if self.recorder.error:
                self.warnings.append(f"Screen recording stopped early: {self.recorder.error}")
            if not parts:
                self.warnings.append("The screen recording produced no files.")
                return None
            path = self.joiner(parts, self.directory / "recording.mp4")
            for part in parts:
                part.unlink(missing_ok=True)
            (self.directory / "segments").rmdir()
            return path
        except (AdbError, ValueError, OSError) as exc:
            self.warnings.append(f"The screen recording could not be saved: {exc}")
            return None

    def capture_contexts(self, length: float | None = None) -> list[CaptureSegment]:
        """Merge consecutive steps with the same screen label into recording segments."""
        timed = [s for s in self.steps if s.screen and s.recording_seconds is not None]
        segments: list[CaptureSegment] = []
        for i, s in enumerate(timed):
            end = timed[i + 1].recording_seconds if i + 1 < len(timed) else length
            end = max(s.recording_seconds, end if end is not None else s.recording_seconds + 2)
            if segments and segments[-1].context == s.screen:
                segments[-1].end_seconds = end
            else:
                segments.append(
                    CaptureSegment(
                        start_seconds=s.recording_seconds, end_seconds=end, context=s.screen
                    )
                )
        return segments

    def _fallback_images(self) -> list[ImageSource]:
        """Without a recording, keep up to 12 distinct screenshots as image evidence."""
        kept: list[tuple[int, bytes, str | None]] = []
        for h, jpeg, screen in self._shots:
            if all(hamming(h, k) > 6 for k, _, _ in kept):
                kept.append((h, jpeg, screen))
        step = max(
            1, len(kept) // MAX_FALLBACK_SCREENSHOTS + (len(kept) % MAX_FALLBACK_SCREENSHOTS > 0)
        )
        images = []
        for n, (_, jpeg, screen) in enumerate(kept[::step][:MAX_FALLBACK_SCREENSHOTS], 1):
            path = self.directory / f"android-shot{n}.jpg"
            path.write_bytes(jpeg)
            images.append(
                ImageSource(
                    id=f"android-shot{n}",
                    path=path.name,
                    provider=f"Automated Android play screenshot (player's label: {screen})",
                    sha256=sha256(jpeg),
                )
            )
        return images

    def _write_outputs(self, recording: Path | None, stop_reason: str) -> Path | None:
        c = self.config
        with (self.directory / "steps.jsonl").open("w") as f:
            for s in self.steps:
                f.write(json.dumps(asdict(s)) + "\n")
        try:
            device = self.device.info()
        except AdbError:
            device = {}
        videos, images = [], []
        if recording:
            data = recording.read_bytes()
            length = max((s.recording_seconds or 0) for s in self.steps) + 5 if self.steps else None
            videos.append(
                VideoSource(
                    id="android-play",
                    path=recording.name,
                    provider="Automated Android play session (emulator screen recording)",
                    role="gameplay_recording",
                    title=f"{c.title or c.package}: automated play, {c.minutes:g} min",
                    uri=f"https://play.google.com/store/apps/details?id={c.package}",
                    sha256=sha256(data),
                    capture_method="automated_play",
                    capture_contexts=self.capture_contexts(length),
                )
            )
        else:
            images = self._fallback_images()
        dossier_path = None
        if videos or images:
            dossier = Dossier(
                game_id=f"android:{c.package}",
                title=c.title,
                videos=videos,
                images=images,
                notes=[
                    f"Automated Android play session ({PROMPT_VERSION}, model "
                    f"{self.agent.model}); stopped: {stop_reason}. Goals reached: "
                    f"{', '.join(self.goals) or 'none'}.",
                    *self.warnings,
                ],
            )
            dossier_path = self.directory / "dossier.json"
            dossier_path.write_text(dossier.model_dump_json(indent=2) + "\n")
        summary = {
            "schema_version": "play-session-v1",
            "package": c.package,
            "title": c.title,
            "prompt_version": PROMPT_VERSION,
            "model": self.agent.model,
            "device": device,
            "config": asdict(c),
            "stop_reason": stop_reason,
            "steps": len(self.steps),
            "model_errors": sum(1 for s in self.steps if s.error and not s.action),
            "safety_events": [e for s in self.steps for e in s.events],
            "goals_reached_at_seconds": self.goals,
            "goals_missed": [g for g in GOALS if g not in self.goals],
            "screens": {
                k: sum(s.screen == k for s in self.steps)
                for k in {s.screen for s in self.steps if s.screen}
            },
            "recording": recording.name if recording else None,
            "dossier": dossier_path.name if dossier_path else None,
            "cost_usd": self.cost(),
            "warnings": self.warnings,
        }
        (self.directory / "session.json").write_text(json.dumps(summary, indent=2) + "\n")
        return dossier_path
