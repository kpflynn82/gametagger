"""Scene-change ("systems") sampling for long gameplay videos and screen recordings.

Store trailers are short and edited, so rich mode spreads its bursts evenly over them. A
YouTube gameplay video or a screen recording is long and mostly ordinary play; the screens
product teams care about (shop, timers, events, social menus) flash by for a few seconds. Even
spreading misses them. This sampler looks at the whole video cheaply first and then spends the
same burst budget on what is distinct:

1. Scan: one tiny 8x8 grey thumbnail per second, turned into a 64-bit average hash. This runs
   locally with ffmpeg and costs nothing.
2. Segment: consecutive seconds whose hashes stay close are one *still screen* (menus, shops and
   dialogs hold still); everything else is *motion* (play).
3. Deduplicate: a still screen that looks like an earlier one is a repeat and is dropped.
4. Allocate: about a third of the bursts go to motion, spread over the play time; the rest go
   to distinct still screens, spread over the video. When a recording carries capture contexts
   (shop, event, social...), still screens are taken round-robin across contexts so each gets a
   burst before any gets two.
5. Extract: motion bursts keep the usual frame count; still screens get 3 frames, since six
   copies of a still menu add cost and nothing else.

The Observer is not told why a burst was chosen. It still only describes what is visible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from gametagger.genome.dossier import VideoSource
from gametagger.genome.media import _ffmpeg, _input, extract_burst, probe_video, sha256
from gametagger.observers.ordered import OrderedWindow

SYSTEMS_STRATEGY = "scene-change-v1: one burst per distinct still screen, plus motion bursts"
SCAN_INTERVAL = 1.0  # seconds between scan thumbnails
SCAN_CHUNK = 60.0  # seconds decoded per ffmpeg process (each runs under a CPU-time limit)
STABLE_DISTANCE = 6  # of 64 bits: consecutive seconds this close show one still screen
DISTINCT_DISTANCE = 10  # a still screen this close to an earlier one is a repeat
MIN_STILL_SCANS = 2  # a still screen must hold for at least this many scans
STILL_FRAMES = 3
MOTION_SHARE = 1 / 3


@dataclass(frozen=True)
class Scan:
    time: float
    hash: int


@dataclass
class Segment:
    start: float
    end: float
    still: bool
    hash: int | None = None
    context: str | None = None

    @property
    def length(self) -> float:
        return self.end - self.start


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def average_hash(pixels: bytes) -> int:
    """64-bit average hash of an 8x8 grey thumbnail."""
    mean = sum(pixels) / len(pixels)
    return sum(1 << i for i, v in enumerate(pixels) if v > mean)


def scan_video(
    path: Path, duration: float, offset: float = 0.0, *, interval: float = SCAN_INTERVAL
) -> list[Scan]:
    """One average hash per ``interval`` seconds, decoded in chunks to stay under CPU limits."""
    scans: list[Scan] = []
    start = 0.0
    while start < duration:
        length = min(SCAN_CHUNK, duration - start)
        result = _ffmpeg(
            "-v", "info", "-threads", "1", "-copyts", "-ss", f"{start + offset:.3f}",
            "-t", f"{length:.3f}", *_input(path), "-an", "-vf",
            f"fps=1/{interval},scale=8:8:flags=area,format=gray,showinfo",
            "-f", "rawvideo", "-",
            timeout=120,
        )  # fmt: skip
        stamps = re.findall(rb"pts_time:(-?[0-9.]+)", result.stderr)
        data = result.stdout or b""
        for k in range(min(len(data) // 64, len(stamps))):
            t = max(0.0, float(stamps[k]) - offset)
            if scans and t <= scans[-1].time:
                continue  # chunk boundaries can repeat a frame
            scans.append(Scan(t, average_hash(data[k * 64 : (k + 1) * 64])))
        start += SCAN_CHUNK
    return scans


def segment_scans(scans: list[Scan], *, interval: float = SCAN_INTERVAL) -> list[Segment]:
    """Split scans into still screens and motion stretches."""
    segments: list[Segment] = []
    i = 0
    while i < len(scans):
        j = i + 1
        while j < len(scans) and hamming(scans[j].hash, scans[i].hash) <= STABLE_DISTANCE:
            j += 1
        still = j - i >= MIN_STILL_SCANS
        end = scans[j - 1].time + interval
        if still:
            segments.append(Segment(scans[i].time, end, True, scans[i].hash))
        elif segments and not segments[-1].still:
            segments[-1].end = end  # extend the current motion stretch
        else:
            segments.append(Segment(scans[i].time, end, False))
        i = j
    return segments


def distinct_stills(segments: list[Segment]) -> list[Segment]:
    """Still screens that do not repeat an earlier still screen."""
    kept: list[Segment] = []
    for segment in segments:
        if not segment.still or segment.hash is None:
            continue
        if any(hamming(segment.hash, k.hash or 0) <= DISTINCT_DISTANCE for k in kept):
            continue
        kept.append(segment)
    return kept


def _spread(items: list, count: int) -> list:
    """Up to ``count`` items evenly spread over the list, keeping order."""
    if count >= len(items):
        return list(items)
    if count <= 0:
        return []
    return [items[int((i + 0.5) * len(items) / count)] for i in range(count)]


def _round_robin(stills: list[Segment], count: int) -> list[Segment]:
    """Pick stills so each capture context gets one before any gets two, in video order."""
    groups: dict[str | None, list[Segment]] = {}
    for s in stills:
        groups.setdefault(s.context, []).append(s)
    chosen: list[Segment] = []
    round_ = 0
    while len(chosen) < count and any(round_ < len(g) for g in groups.values()):
        for group in groups.values():
            if round_ < len(group) and len(chosen) < count:
                chosen.append(group[round_])
        round_ += 1
    return sorted(chosen, key=lambda s: s.start)


@dataclass(frozen=True)
class BurstPlan:
    start: float
    frames: int
    still: bool
    context: str | None


def plan_bursts(
    segments: list[Segment],
    windows: int,
    *,
    frames: int,
    spacing: float,
    duration: float,
) -> list[BurstPlan]:
    """Choose burst start times: distinct still screens first, then motion spread over play."""
    stills = distinct_stills(segments)
    motion = [s for s in segments if not s.still]
    motion_time = sum(s.length for s in motion)
    want_motion = max(1, round(windows * MOTION_SHARE)) if motion_time > 0 else 0
    want_motion = min(want_motion, windows)
    want_stills = min(len(stills), windows - want_motion)
    want_motion = windows - want_stills if motion_time > 0 else 0  # unused still slots
    has_contexts = any(s.context for s in stills)
    picked = _round_robin(stills, want_stills) if has_contexts else _spread(stills, want_stills)

    plans = []
    still_frames = min(frames, STILL_FRAMES)
    for s in picked:
        span = (still_frames - 1) * spacing
        # Half a second in, past any transition, but inside the still stretch when possible.
        start = min(s.start + 0.5, max(s.start, s.end - span))
        latest = max(0.0, duration - span - 0.05)
        plans.append(BurstPlan(min(start, latest), still_frames, True, s.context))
    span = (frames - 1) * spacing
    for k in range(want_motion):
        # Positions spread evenly over total motion time, mapped back onto the video.
        target = motion_time * (k + 0.5) / want_motion
        for s in motion:
            if target <= s.length:
                start = s.start + min(target, max(0.0, s.length - span))
                latest = max(0.0, duration - span - 0.05)
                plans.append(BurstPlan(min(start, latest), frames, False, s.context))
                break
            target -= s.length
    return sorted(plans, key=lambda p: p.start)


def label_contexts(segments: list[Segment], video: VideoSource) -> None:
    """Give each segment the capture context covering its middle, if the video has any."""
    if not video.capture_contexts:
        return
    for s in segments:
        s.context = video.capture_at((s.start + s.end) / 2)


def systems_bursts(
    video: VideoSource,
    directory: Path,
    *,
    windows: int = 6,
    frames: int = 6,
    spacing: float = 0.4,
) -> list[tuple[OrderedWindow, list[bytes], str | None]]:
    """Scene-change bursts: (window, frames, capture context at that moment) per burst."""
    if not 1 <= windows <= 20 or not 2 <= frames <= 12 or not 0 < spacing <= 0.5:
        raise ValueError("Use 1-20 bursts of 2-12 frames at most 0.5 s apart")
    path = Path(video.path)
    asset = sha256(path.read_bytes())
    if video.sha256 and video.sha256 != asset:
        raise ValueError(f"Video {video.id} changed since it was recorded")
    duration, offset, _, _ = probe_video(path)
    segments = segment_scans(scan_video(path, duration, offset))
    label_contexts(segments, video)
    plans = plan_bursts(segments, windows, frames=frames, spacing=spacing, duration=duration)
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    for i, plan in enumerate(plans):
        sampled = extract_burst(
            path,
            video.id,
            i,
            plan.start,
            directory,
            asset=asset,
            duration=duration,
            offset=offset,
            frames=plan.frames,
            spacing=spacing,
            strategy=SYSTEMS_STRATEGY,
        )
        if sampled:
            window, data = sampled
            moment = window.frames[0].timestamp_seconds
            results.append((window, data, video.capture_at(moment) or plan.context))
    return results
