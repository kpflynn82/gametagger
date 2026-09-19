"""Bounded local-only media inspection; synthetic tests validate processing, not recognition."""

import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_VIDEO_SECONDS = 60


def video_available():
    return sys.platform != "win32" and bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def inspect_image(data: bytes):
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("Images must be no larger than 5 MiB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                raise ValueError("Use a nonanimated PNG, JPEG, or WebP")
            if image.width > 8000 or image.height > 8000 or image.width * image.height > 24_000_000:
                raise ValueError("Image exceeds 24 megapixels or 8000 pixels per side")
            if image.format == "PNG" and not data.endswith(b"IEND\xaeB`\x82"):
                raise ValueError("Trailing data after PNG")
            if image.format == "JPEG" and not data.endswith(b"\xff\xd9"):
                raise ValueError("Trailing data after JPEG")
            if image.format == "WEBP" and int.from_bytes(data[4:8], "little") + 8 != len(data):
                raise ValueError("Invalid WebP container size")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            # Serve only decoded/re-encoded preview; retain/hash originals privately for analysis.
            preview = io.BytesIO()
            image.convert("RGB").save(preview, format="JPEG", quality=88)
            return image.width, image.height, preview.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Image content could not be safely decoded") from exc


def inspect_video(path: Path):
    if not video_available():
        raise ValueError("Local FFmpeg is unavailable")
    data = path.read_bytes()[:16]
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise ValueError("Only local MP4 containers are supported")
    raw = subprocess.run(
        [
            sys.executable,
            "-m",
            "gametagger.workspace.decoder",
            "ffprobe",
            "-v",
            "error",
            "-max_alloc",
            "67108864",
            "-enable_drefs",
            "0",
            "-use_absolute_path",
            "0",
            "-protocol_whitelist",
            "file",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        timeout=10,
        check=True,
    )
    info = json.loads(raw.stdout)
    streams = [s for s in info["streams"] if s["codec_type"] == "video"]
    if len(streams) != 1:
        raise ValueError("Supply one video stream")
    s = streams[0]
    duration = float(info["format"]["duration"])
    if (
        not 0 < duration <= MAX_VIDEO_SECONDS
        or s["width"] * s["height"] > 1920 * 1080
        or max(s["width"], s["height"]) > 1920
        or min(s["width"], s["height"]) <= 0
    ):
        raise ValueError("Video limit: 60 seconds and 1920×1080 pixels")
    if s["codec_name"] not in {"h264", "hevc", "mpeg4", "av1"}:
        raise ValueError("Unsupported video codec")
    return duration, s["width"], s["height"]


def extract_windows(path: Path, directory: Path):
    duration, _, _ = inspect_video(path)
    directory.mkdir(exist_ok=True)
    window_length = min(1.0, duration / 6)
    starts = (0.0, duration / 2, max(0, duration - window_length))
    # Three uniformly spaced ordered windows, not a claim of semantic scene selection.
    # Bounded decode emits real presentation timestamps from showinfo; no invented seeks.
    raw = subprocess.run(
        [
            sys.executable,
            "-m",
            "gametagger.workspace.decoder",
            "ffmpeg",
            "-nostdin",
            "-y",
            "-filter_threads",
            "1",
            "-v",
            "info",
            "-threads",
            "1",
            "-max_alloc",
            "67108864",
            "-enable_drefs",
            "0",
            "-use_absolute_path",
            "0",
            "-protocol_whitelist",
            "file",
            "-i",
            str(path),
            "-an",
            "-vf",
            "select='("
            + "+".join(
                f"between(t,{start:.6f},{min(duration, start + window_length):.6f})"
                for start in starts
            )
            + ")*(isnan(prev_selected_t)+gte(t-prev_selected_t,0.2))',"
            "scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2,showinfo",
            "-fps_mode",
            "vfr",
            "-frames:v",
            "48",
            "-threads",
            "1",
            str(directory / "frame-%03d.jpg"),
        ],
        capture_output=True,
        timeout=25,
        check=True,
    )
    import re

    timestamps = [float(t) for t in re.findall(rb"pts_time:([0-9.]+)", raw.stderr)]
    paths = sorted(directory.glob("frame-*.jpg"))
    frames = []
    for i, p in enumerate(paths):
        if i >= len(timestamps):
            raise ValueError("Decoder timestamp missing")
        frames.append(
            {
                "file": p.name,
                "timestamp": timestamps[i],
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
        )
    if not frames:
        raise ValueError("No decodable frames")
    return {
        "strategy": "uniform-three-ordered-windows-v1",
        "duration": duration,
        "frame_budget": 48,
        "maximum_sampling_hz": 5,
        "window_starts": starts,
        "window_length_seconds": window_length,
        "frames": frames,
        "temporal_claims_validated": False,
    }
