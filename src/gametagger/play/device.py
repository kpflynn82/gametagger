"""A thin, injectable wrapper around adb for one Android device or emulator.

Everything goes through ``adb`` (Android Debug Bridge): screenshots, taps, swipes, the back
button, launching the game and screen recording. ``run`` is injectable so tests use a fake
device and never need Android installed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
ADB_ENV = "GAMETAGGER_ADB"
# Where Android Studio puts adb on a Mac when it is not on PATH.
MAC_SDK_ADB = Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb"
SAFE_TEXT = re.compile(r"^[A-Za-z0-9 ]{1,16}$")

Runner = Callable[..., subprocess.CompletedProcess]


class AdbError(RuntimeError):
    """adb is missing, no device is connected, or a device command failed."""


def adb_path() -> str | None:
    """adb on PATH, named by GAMETAGGER_ADB, or in Android Studio's default Mac location."""
    if found := os.environ.get(ADB_ENV) or shutil.which("adb"):
        return found
    return str(MAC_SDK_ADB) if MAC_SDK_ADB.exists() else None


def valid_package(package: str) -> str:
    if not PACKAGE.fullmatch(package or ""):
        raise ValueError(f"'{package}' is not an Android package name like com.studio.game")
    return package


@dataclass(frozen=True)
class Foreground:
    package: str | None
    activity: str | None

    @property
    def text(self) -> str:
        return f"{self.package or '?'}/{self.activity or '?'}"


class AdbDevice:
    def __init__(self, serial: str | None = None, *, adb: str | None = None, run: Runner = None):
        self.adb = adb or adb_path()
        if not self.adb:
            raise AdbError(
                "adb was not found. Install it with: brew install --cask android-platform-tools"
            )
        self.run = run or subprocess.run
        self.serial = serial or self._only_device()

    # ------------------------------------------------------------------ plumbing

    def _call(self, args: list[str], *, timeout: float = 30) -> subprocess.CompletedProcess:
        try:
            return self.run([self.adb, *args], capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"adb timed out: {' '.join(args[:3])}") from exc
        except OSError as exc:
            raise AdbError(f"adb could not run: {exc}") from exc

    def cmd(self, *args: str, timeout: float = 30, check: bool = True) -> bytes:
        result = self._call(["-s", self.serial, *args], timeout=timeout)
        if check and result.returncode != 0:
            detail = (result.stderr or b"").decode("utf-8", "replace").strip()[:200]
            raise AdbError(f"adb {' '.join(args[:2])} failed: {detail}")
        return result.stdout or b""

    def shell(self, *args: str, timeout: float = 30, check: bool = True) -> str:
        return self.cmd("shell", *args, timeout=timeout, check=check).decode("utf-8", "replace")

    def devices(self) -> list[str]:
        out = self._call(["devices"]).stdout.decode("utf-8", "replace")
        return [
            line.split()[0]
            for line in out.splitlines()[1:]
            if line.strip() and line.split()[-1] == "device"
        ]

    def _only_device(self) -> str:
        found = self.devices()
        if not found:
            raise AdbError(
                "No Android device or emulator is connected. Start the emulator in Android "
                "Studio (Device Manager > the play button) and try again."
            )
        if len(found) > 1:
            raise AdbError(f"Several devices are connected ({', '.join(found)}); pass --serial.")
        return found[0]

    # ------------------------------------------------------------------ device facts

    def info(self) -> dict[str, str]:
        def prop(name: str) -> str:
            return self.shell("getprop", name, check=False).strip()

        return {
            "serial": self.serial,
            "model": prop("ro.product.model"),
            "android_version": prop("ro.build.version.release"),
            "emulator": "yes" if prop("ro.kernel.qemu") == "1" or "emulator" in self.serial
            else "no",
        }  # fmt: skip

    def is_installed(self, package: str) -> bool:
        return "package:" in self.shell("pm", "path", valid_package(package), check=False)

    def foreground(self) -> Foreground:
        """The app and screen (activity) currently in front."""
        text = self.shell("dumpsys", "activity", "activities", check=False)
        match = re.search(
            r"(?:mResumedActivity|topResumedActivity|ResumedActivity)\S*[:=]\s*"
            r"ActivityRecord\{\S+ \S+ ([\w.]+)/([\w.$]+)",
            text,
        )
        if not match:
            text = self.shell("dumpsys", "window", check=False)
            match = re.search(r"mCurrentFocus=Window\{\S+ \S+ ([\w.]+)/([\w.$]+)", text)
        if not match:
            return Foreground(None, None)
        package, activity = match.groups()
        if activity.startswith("."):
            activity = package + activity
        return Foreground(package, activity)

    # ------------------------------------------------------------------ actions

    def screenshot(self) -> bytes:
        data = self.cmd("exec-out", "screencap", "-p", timeout=20)
        if not data.startswith(PNG_MAGIC):
            raise AdbError("The device did not return a screenshot")
        return data

    def tap(self, x: int, y: int) -> None:
        self.shell("input", "tap", str(int(x)), str(int(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 400) -> None:
        coords = [str(int(v)) for v in (x1, y1, x2, y2)]
        self.shell("input", "swipe", *coords, str(int(ms)))

    def long_press(self, x: int, y: int, ms: int = 900) -> None:
        self.swipe(x, y, x, y, ms)

    def back(self) -> None:
        self.shell("input", "keyevent", "KEYCODE_BACK")

    def type_text(self, text: str) -> None:
        """Only short letters, digits and spaces (a player name), never free text."""
        if not SAFE_TEXT.fullmatch(text):
            raise ValueError("Only up to 16 letters, digits and spaces may be typed")
        self.shell("input", "text", text.replace(" ", "%s"))

    def launch(self, package: str) -> None:
        self.shell(
            "monkey", "-p", valid_package(package), "-c", "android.intent.category.LAUNCHER", "1"
        )

    def open_store_page(self, package: str) -> None:
        self.shell(
            "am", "start", "-a", "android.intent.action.VIEW",
            "-d", f"market://details?id={valid_package(package)}",
        )  # fmt: skip


# ---------------------------------------------------------------------- screen recording


@dataclass
class RecordedSegment:
    remote: str
    started: float
    ended: float
    local: Path | None = None


class ScreenRecorder:
    """Records the device screen in back-to-back segments (Android caps one at 3 minutes).

    Segment wall-clock times are kept so a moment in the play session can be mapped to a
    moment in the joined recording.
    """

    SEGMENT_SECONDS = 170
    REMOTE_DIR = "/sdcard/gametagger"

    def __init__(self, device: AdbDevice, *, clock: Callable[[], float] = time.monotonic):
        self.device, self.clock = device, clock
        self.segments: list[RecordedSegment] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: str | None = None

    def start(self) -> None:
        self.device.shell("mkdir", "-p", self.REMOTE_DIR, check=False)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        n = 0
        while not self._stop.is_set():
            remote = f"{self.REMOTE_DIR}/seg{n:03d}.mp4"
            segment = RecordedSegment(remote, self.clock(), self.clock())
            self.segments.append(segment)
            try:
                self.device.shell(
                    "screenrecord", "--time-limit", str(self.SEGMENT_SECONDS),
                    "--bit-rate", "4000000", remote,
                    timeout=self.SEGMENT_SECONDS + 30, check=False,
                )  # fmt: skip
            except AdbError as exc:
                self.error = str(exc)
                segment.ended = self.clock()
                return
            segment.ended = self.clock()
            n += 1

    def recording_time(self, wall: float) -> float | None:
        """Seconds into the joined recording for a wall-clock moment, if it was recorded."""
        elapsed = 0.0
        for segment in self.segments:
            end = segment.ended if segment.ended > segment.started else self.clock()
            if segment.started <= wall <= end:
                return elapsed + (wall - segment.started)
            elapsed += end - segment.started
        return None

    def stop(self, directory: Path) -> list[Path]:
        """Stop, copy the segments off the device, and delete them there."""
        self._stop.set()
        self.device.shell("pkill", "-INT", "screenrecord", check=False)
        if self._thread:
            self._thread.join(timeout=20)
        time.sleep(0.5)  # let the device finish writing the last file
        directory.mkdir(parents=True, exist_ok=True)
        files = []
        for n, segment in enumerate(self.segments):
            local = directory / f"segment{n:03d}.mp4"
            try:
                self.device.cmd("pull", segment.remote, str(local), timeout=120)
            except AdbError:
                continue
            if local.exists() and local.stat().st_size > 0:
                segment.local = local
                files.append(local)
        self.device.shell("rm", "-rf", self.REMOTE_DIR, check=False)
        return files


def join_recording(parts: list[Path], output: Path, *, run: Runner = subprocess.run) -> Path:
    """Join segments into one constant-frame-rate MP4, at most 1280 pixels on the long side.

    Android records only when the screen changes; a constant 10 frames a second gives still
    menus enough frames for the burst sampler.
    """
    if not parts:
        raise ValueError("Nothing was recorded")
    listing = output.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    scale = "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))'"
    result = run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-an", "-vf", f"fps=10,{scale}", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "28", "-pix_fmt", "yuv420p", str(output)],
        capture_output=True, timeout=900,
    )  # fmt: skip
    listing.unlink(missing_ok=True)
    if result.returncode != 0 or not output.exists():
        detail = (result.stderr or b"").decode("utf-8", "replace").strip()[-200:]
        raise ValueError(f"ffmpeg could not join the recording: {detail}")
    return output
