"""Scene-change ("systems") sampling: distinct still screens, motion spread, capture contexts."""

from __future__ import annotations

import random
import shutil
import subprocess
import sys

import pytest
from test_genome_media import RecordingGateway, ScriptedOrdered, output, window

from gametagger.genome.dossier import CaptureSegment, Dossier, VideoSource
from gametagger.genome.engine import GenomeEngine, GenomePipeline
from gametagger.genome.media import burst_claims
from gametagger.genome.systems import (
    SYSTEMS_STRATEGY,
    Scan,
    Segment,
    distinct_stills,
    plan_bursts,
    segment_scans,
    systems_bursts,
)
from gametagger.genome.vocabulary import load_vocabulary
from gametagger.observers.boundary import ObservationBoundary

needs_ffmpeg = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("ffmpeg") is None, reason="Local FFmpeg unavailable"
)

A = int("F0" * 8, 16)  # a still screen
B = int("FF00" * 4, 16)  # a different still screen


def noisy(seed: int) -> int:
    return random.Random(seed).getrandbits(64)


def scans_for(pattern: list[tuple[str, int]]) -> list[Scan]:
    """pattern: (kind, seconds) where kind is 'motion', 'A' or 'B'."""
    scans, t = [], 0
    for kind, seconds in pattern:
        for _ in range(seconds):
            h = {"A": A, "B": B}.get(kind)
            scans.append(Scan(float(t), h if h is not None else noisy(t)))
            t += 1
    return scans


def test_segments_split_still_screens_from_motion_and_drop_repeats():
    scans = scans_for([("motion", 10), ("A", 5), ("motion", 8), ("B", 4), ("A", 3), ("motion", 2)])
    segments = segment_scans(scans)
    stills = [s for s in segments if s.still]
    assert [(s.start, s.end) for s in stills] == [(10, 15), (23, 27), (27, 30)]
    assert all(not s.still for s in segments if s not in stills)
    # consecutive motion seconds merge into one stretch
    assert segments[0].start == 0 and segments[0].end == 10 and not segments[0].still
    distinct = distinct_stills(segments)
    assert [s.hash for s in distinct] == [A, B]  # the second A is a repeat


def test_a_single_still_second_is_motion():
    segments = segment_scans(scans_for([("motion", 3), ("A", 1), ("motion", 3)]))
    assert not any(s.still for s in segments)


def test_plan_gives_still_screens_short_bursts_and_spreads_motion():
    segments = [
        Segment(0, 30, False),
        Segment(30, 36, True, A),
        Segment(36, 60, False),
        Segment(60, 66, True, B),
        Segment(66, 90, False),
    ]
    plans = plan_bursts(segments, 6, frames=6, spacing=0.4, duration=90)
    stills = [p for p in plans if p.still]
    motion = [p for p in plans if not p.still]
    assert [p.start for p in stills] == [30.5, 60.5] and all(p.frames == 3 for p in stills)
    assert len(motion) == 4 and all(p.frames == 6 for p in motion)
    assert all(not (30 <= p.start < 36 or 60 <= p.start < 66) for p in motion)
    assert [p.start for p in plans] == sorted(p.start for p in plans)


def test_plan_without_motion_takes_distinct_stills_then_fills_gaps():
    segments = [Segment(0, 5, True, A), Segment(5, 10, True, B), Segment(10, 15, True, A)]
    plans = plan_bursts(segments, 6, frames=6, spacing=0.4, duration=15)
    assert [p.start for p in plans if p.still] == [0.5, 5.5]
    starts = [p.start for p in plans]
    assert all(b - a >= 3 for a, b in zip(starts, starts[1:], strict=False))


def test_one_long_still_video_still_spends_its_budget_across_it():
    plans = plan_bursts([Segment(0, 600, True, A)], 6, frames=6, spacing=0.4, duration=600)
    starts = [p.start for p in plans]
    assert len(plans) == 6 and starts[0] < 5 and starts[-1] > 250


def test_each_systems_context_gets_a_burst_even_without_a_still_screen():
    segments = [Segment(0, 40, True, A)]
    captures = [(0.0, 20.0, "first_session"), (20.0, 30.0, "shop"), (30.0, 40.0, "event")]
    plans = plan_bursts(segments, 4, frames=6, spacing=0.4, duration=40, captures=captures)
    by_context = {p.context: p.start for p in plans if p.context}
    assert 20 <= by_context["shop"] < 30 and 30 <= by_context["event"] < 40


def test_capture_contexts_are_taken_round_robin():
    hashes = [int(f"{n:02x}" * 8, 16) for n in (1, 64, 128, 170, 200, 255)]
    segments = [
        Segment(10 * i, 10 * i + 5, True, h, ctx)
        for i, (h, ctx) in enumerate(
            zip(hashes, ["shop", "shop", "shop", "shop", "event", "social"], strict=True)
        )
    ]
    for s in segments:
        s.hash = s.hash ^ (s.hash << 1)  # make them far apart
    stills = distinct_stills(segments)
    plans = plan_bursts(stills, 3, frames=6, spacing=0.4, duration=100)
    assert sorted(p.context for p in plans) == ["event", "shop", "social"]


def test_capture_segments_validate_and_locate():
    video = VideoSource(
        id="rec",
        path="x.mp4",
        role="gameplay_recording",
        capture_method="automated_play",
        capture_contexts=[
            CaptureSegment(start_seconds=0, end_seconds=30, context="first_session"),
            CaptureSegment(start_seconds=30, end_seconds=40, context="shop"),
        ],
    )
    assert video.capture_at(35) == "shop" and video.capture_at(10) == "first_session"
    assert video.capture_at(50) is None
    with pytest.raises(ValueError):
        CaptureSegment(start_seconds=5, end_seconds=1, context="shop")
    with pytest.raises(ValueError):
        CaptureSegment(start_seconds=0, end_seconds=1, context="energy_system")


def test_capture_context_labels_claims_as_navigation(taxonomy):
    boundary = ObservationBoundary(taxonomy)
    claims, _, _ = burst_claims("v", 0, window(), output(), boundary, capture="the shop")
    assert claims[0].text.startswith("[gameplay, 40.0-40.8s, capture context: the shop]")


# --------------------------------------------------------------------------- real video


def _frames(pattern, fps, width=160, height=120):
    """Raw RGB frames: block noise for motion, fixed patterns for still screens."""
    rng = random.Random(7)

    def still(kind):
        rows = []
        for y in range(height):
            row = bytearray()
            for x in range(width):
                on = x < width // 2 if kind == "A" else y < height // 2
                row += bytes((230, 230, 230) if on else (20, 20, 20))
            rows.append(bytes(row))
        return b"".join(rows)

    stills = {"A": still("A"), "B": still("B")}
    for kind, seconds in pattern:
        for _ in range(int(seconds * fps)):
            if kind in stills:
                yield stills[kind]
                continue
            grid = [[rng.randrange(256) for _ in range(8)] for _ in range(6)]
            out = bytearray()
            for y in range(height):
                for x in range(width):
                    v = grid[y * 6 // height][x * 8 // width]
                    out += bytes((v, 255 - v, v // 2))
            yield bytes(out)


PATTERN = [
    ("motion", 15),
    ("A", 7),
    ("motion", 13),
    ("B", 7),
    ("motion", 8),
    ("A", 6),
    ("motion", 4),
]


@pytest.fixture(scope="module")
def play_video(tmp_path_factory):
    if sys.platform == "win32" or shutil.which("ffmpeg") is None:
        pytest.skip("Local FFmpeg unavailable")
    path = tmp_path_factory.mktemp("rec") / "play.mp4"
    fps = 10
    process = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "160x120",
         "-r", str(fps), "-i", "-", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-g", "20",
         str(path)],
        stdin=subprocess.PIPE,
    )  # fmt: skip
    for frame in _frames(PATTERN, fps):
        process.stdin.write(frame)
    process.stdin.close()
    assert process.wait(timeout=120) == 0
    return path


@needs_ffmpeg
def test_systems_bursts_find_each_distinct_screen_once(play_video, tmp_path):
    video = VideoSource(id="youtube-gameplay1", path=str(play_video), role="community_video")
    bursts = systems_bursts(video, tmp_path / "frames", windows=6, frames=5)
    assert len(bursts) == 6
    stills = [(w, f) for w, f, _ in bursts if len(f) == 3]
    starts = sorted(w.frames[0].timestamp_seconds for w, _ in stills)
    assert len(stills) == 2
    assert 15 <= starts[0] < 22 and 35 <= starts[1] < 42  # A once, B once; A's repeat dropped
    assert all(w.selection_strategy == SYSTEMS_STRATEGY for w, _, _ in bursts)


@needs_ffmpeg
def test_recording_contexts_flow_into_claims_and_state(taxonomy, play_video):
    recording = VideoSource(
        id="android-play",
        path=str(play_video),
        provider="Automated Android play session",
        role="gameplay_recording",
        capture_method="automated_play",
        capture_contexts=[
            CaptureSegment(start_seconds=0, end_seconds=30, context="first_session"),
            CaptureSegment(start_seconds=30, end_seconds=45, context="shop"),
            CaptureSegment(start_seconds=45, end_seconds=60, context="event"),
        ],
    )
    gateway = RecordingGateway()
    engine = GenomeEngine(taxonomy, load_vocabulary(taxonomy), gateway)
    pipeline = GenomePipeline(
        engine, None, ScriptedOrdered(), bursts=6, frames_per_burst=4, burst_strategy="auto"
    )
    profile = pipeline.analyze(Dossier(game_id="g", videos=[recording]), offline=True)
    media = profile.media[0]
    assert media["strategy"] == "systems" and media["capture_method"] == "automated_play"
    assert "the shop" in " ".join(c.text for c in profile.claims)
    assert "capture context is navigation" in gateway.states["mechanic_real_time_combat"]
    assert profile.provenance["burst_strategy"] == SYSTEMS_STRATEGY
    source = next(s for s in profile.sources if s.id == "android-play")
    assert source.metadata["capture_method"] == "automated_play"


@needs_ffmpeg
def test_auto_keeps_even_bursts_for_store_trailers(taxonomy, play_video):
    trailer = VideoSource(id="steam-trailer", path=str(play_video), role="store_trailer")
    engine = GenomeEngine(taxonomy, load_vocabulary(taxonomy), RecordingGateway())
    pipeline = GenomePipeline(engine, bursts=4, frames_per_burst=3, burst_strategy="auto")
    prepared = pipeline.prepare(Dossier(game_id="g", videos=[trailer]), observe=False)
    assert prepared.media[0]["strategy"] == "even"
    assert prepared.burst_strategies[0].startswith("even-bursts-v1")
