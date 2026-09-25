"""Store media for rich mode: download screenshots and trailers, sample trailers into bursts.

Images are decoded and re-encoded (never passed through raw) at a size the vision Observer uses
well. Trailers are downloaded as a file or assembled from an HLS playlist, then sampled locally
with ffmpeg inside the project's resource-limited decoder wrapper. Each burst is a short run of
consecutive frames (at most 0.5 s apart) so the ordered Observer can describe visible change.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from gametagger.domain import EvidenceItem, EvidenceType, Observation
from gametagger.genome.dossier import Claim, ImageSource, VideoSource
from gametagger.genome.net import SourceError, fetch_bytes
from gametagger.genome.sources import MediaRef
from gametagger.observers.boundary import ObservationBoundary
from gametagger.observers.ordered import OrderedWindow, TimedFrame, WindowOutput

MAX_IMAGE_DOWNLOAD = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
OBSERVER_IMAGE_SIDE = 1568  # larger images cost more and are downscaled by the provider anyway
MAX_VIDEO_BYTES = 150 * 1024 * 1024
MAX_PLAYLIST_BYTES = 1024 * 1024
MAX_HLS_SEGMENTS = 600
MAX_VIDEO_SECONDS = 900
FRAME_SIDE = 640  # the ordered Observer accepts JPEG frames up to 640 pixels per side
WINDOW_STRATEGY = "even-bursts-v1: bursts spread over 5-95% of the video, 0.4 s apart"
EXCLUDED_CONTEXTS = {"cinematic", "title_card"}
Fetch = Callable[..., bytes]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- images


def normalize_image(data: bytes) -> bytes:
    """Decode a still image and re-encode it as a bounded JPEG; reject anything else."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"} or getattr(image, "n_frames", 1) != 1:
                raise ValueError("Only still JPEG, PNG or WebP images are accepted")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image is too large to decode safely")
            image.load()
            rgb = image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Image content could not be safely decoded") from exc
    rgb.thumbnail((OBSERVER_IMAGE_SIDE, OBSERVER_IMAGE_SIDE))
    out = io.BytesIO()
    rgb.save(out, format="JPEG", quality=88)
    return out.getvalue()


def download_image(ref: MediaRef, directory: Path, image_id: str, *, fetch: Fetch = fetch_bytes):
    data = normalize_image(fetch(ref.url, max_bytes=MAX_IMAGE_DOWNLOAD, media=True))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{image_id}.jpg"
    path.write_bytes(data)
    return ImageSource(
        id=image_id,
        path=str(path),
        provider=ref.provider,
        role=ref.role,
        uri=ref.url,
        sha256=sha256(data),
    )


# --------------------------------------------------------------------------- videos


def _container(data: bytes) -> str:
    if data[4:8] == b"ftyp":
        return "mp4"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if data[:1] == b"\x47" and (len(data) < 189 or data[188:189] == b"\x47"):
        return "ts"
    raise ValueError("Unrecognized video container")


def _attributes(line: str) -> dict[str, str]:
    return {
        k: v.strip('"')
        for k, v in re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', line.split(":", 1)[-1])
    }


def assemble_hls(url: str, *, fetch: Fetch = fetch_bytes, max_bytes: int = MAX_VIDEO_BYTES):
    """Download one video rendition of an HLS playlist and join its segments into one file."""

    def text(u: str) -> str:
        body = fetch(u, max_bytes=MAX_PLAYLIST_BYTES, media=True).decode("utf-8", "replace")
        if not body.lstrip().startswith("#EXTM3U"):
            raise ValueError("Not an HLS playlist")
        return body

    playlist = text(url)
    if "#EXT-X-STREAM-INF" in playlist:
        lines = playlist.splitlines()
        variants = []
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF"):
                attrs = _attributes(line)
                uri = next((x.strip() for x in lines[i + 1 :] if x.strip()), "")
                size = re.fullmatch(r"(\d+)x(\d+)", attrs.get("RESOLUTION", ""))
                height = int(size.group(2)) if size else 0
                bandwidth = int(attrs["BANDWIDTH"]) if attrs.get("BANDWIDTH", "").isdigit() else 0
                if uri and not uri.startswith("#"):
                    variants.append((height, bandwidth, urljoin(url, uri)))
        if not variants:
            raise ValueError("HLS playlist has no video renditions")
        usable = [v for v in variants if v[0] >= 360] or variants
        url = min(usable, key=lambda v: (v[0], v[1]))[2]  # smallest rendition of at least 360p
        playlist = text(url)
    parts = []
    for line in playlist.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-KEY") and _attributes(line).get("METHOD", "NONE") != "NONE":
            raise ValueError("Encrypted HLS streams are not supported")
        if line.startswith("#EXT-X-MAP"):
            if uri := _attributes(line).get("URI"):
                parts.append(urljoin(url, uri))
        elif line and not line.startswith("#"):
            parts.append(urljoin(url, line))
    if not parts or len(parts) > MAX_HLS_SEGMENTS:
        raise ValueError("HLS playlist has no segments or too many segments")
    data, total = [], 0
    for part in parts:
        chunk = fetch(part, max_bytes=max_bytes - total, media=True)
        total += len(chunk)
        data.append(chunk)
    return b"".join(data)


def download_video(ref: MediaRef, directory: Path, video_id: str, *, fetch: Fetch = fetch_bytes):
    if ref.kind == "hls":
        data = assemble_hls(ref.url, fetch=fetch)
    else:
        data = fetch(ref.url, max_bytes=MAX_VIDEO_BYTES, media=True, timeout=120)
    kind = _container(data)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{video_id}.{kind}"
    path.write_bytes(data)
    return VideoSource(
        id=video_id,
        path=str(path),
        provider=ref.provider,
        role=ref.role,
        title=ref.title,
        uri=ref.url,
        sha256=sha256(data),
    )


def download_media(refs, directory: Path, *, max_screenshots: int, video: bool, fetch=fetch_bytes):
    """Download screenshots (per source) and the first trailer; failures become notes."""
    images, videos, notes, counts = [], [], [], {}
    for ref in refs:
        try:
            if ref.kind == "image":
                if counts.get(ref.source_id, 0) >= max_screenshots:
                    continue
                n = counts[ref.source_id] = counts.get(ref.source_id, 0) + 1
                name = "still" if ref.role == "video_still" else "shot"
                images.append(
                    download_image(ref, directory, f"{ref.source_id}-{name}{n}", fetch=fetch)
                )
            elif video and not videos:
                videos.append(
                    download_video(ref, directory, f"{ref.source_id}-trailer", fetch=fetch)
                )
        except (SourceError, ValueError) as exc:
            notes.append(f"Skipped {ref.provider.lower()} ({exc}).")
    return images, videos, notes


# --------------------------------------------------------------------------- frame bursts


def ffmpeg_available() -> bool:
    # The decoder wrapper applies POSIX resource limits, so Windows is not supported.
    return sys.platform != "win32" and shutil.which("ffmpeg") is not None


def _ffmpeg(*args: str, timeout: float) -> subprocess.CompletedProcess:
    command = [sys.executable, "-m", "gametagger.workspace.decoder", "ffmpeg", "-hide_banner"]
    command += ["-nostdin", "-max_alloc", "67108864", *args]
    return subprocess.run(command, capture_output=True, timeout=timeout)


def _input(path: Path) -> list[str]:
    """Local-file-only input options; MP4 references to other files are disabled."""
    with path.open("rb") as stream:
        head = stream.read(16)
    options = ["-protocol_whitelist", "file"]
    if _container(head) == "mp4":
        options += ["-enable_drefs", "0", "-use_absolute_path", "0"]
    return [*options, "-i", str(path)]


def _seconds(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + float(s)


def probe_video(path: Path) -> tuple[float, float, int, int]:
    """Return (duration, start offset, width, height) using ffmpeg alone (no ffprobe needed)."""
    result = _ffmpeg(*_input(path), "-map", "0:v:0", "-c", "copy", "-f", "null", "-", timeout=60)
    log = result.stderr.decode("utf-8", "replace")
    size = re.search(r"Stream #0:\d+\S*: Video: .*?, (\d{2,5})x(\d{2,5})[ ,\[]", log)
    header = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", log)
    start = re.search(r"start: (-?\d+(?:\.\d+)?)", log)
    progress = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", log)
    duration = (
        _seconds(*header.groups()) if header else _seconds(*progress[-1]) if progress else 0.0
    )
    if result.returncode != 0 or not size or duration <= 0:
        raise ValueError("Video could not be decoded")
    width, height = int(size.group(1)), int(size.group(2))
    if duration > MAX_VIDEO_SECONDS or width * height > 3840 * 2160:
        raise ValueError("Video exceeds 15 minutes or 4K resolution")
    return duration, float(start.group(1)) if start else 0.0, width, height


def frame_bursts(
    video: VideoSource,
    directory: Path,
    *,
    windows: int = 6,
    frames: int = 6,
    spacing: float = 0.4,
) -> list[tuple[OrderedWindow, list[bytes]]]:
    """Sample ``windows`` bursts of ``frames`` consecutive frames spread across the video."""
    if not 1 <= windows <= 20 or not 2 <= frames <= 12 or not 0 < spacing <= 0.5:
        raise ValueError("Use 1-20 bursts of 2-12 frames at most 0.5 s apart")
    path = Path(video.path)
    asset = sha256(path.read_bytes())
    if video.sha256 and video.sha256 != asset:
        raise ValueError(f"Video {video.id} changed since it was recorded")
    duration, offset, _, _ = probe_video(path)
    burst = (frames - 1) * spacing
    low, high = duration * 0.05, duration * 0.95 - burst
    starts = (
        [low + (high - low) * (i + 0.5) / windows for i in range(windows)]
        if high > low
        else [max(0.0, (duration - burst) / 2)]
    )
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    for i, start in enumerate(starts):
        for old in directory.glob(f"{video.id}-w{i}-*.jpg"):
            old.unlink()
        result = _ffmpeg(
            "-v", "info", "-threads", "1", "-copyts", "-ss", f"{start:.3f}", *_input(path),
            "-an", "-vf",
            f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{spacing})',"
            f"scale={FRAME_SIDE}:{FRAME_SIDE}:force_original_aspect_ratio=decrease"
            ":force_divisible_by=2,showinfo",
            "-fps_mode", "vfr", "-frames:v", str(frames), "-q:v", "3", "-y",
            str(directory / f"{video.id}-w{i}-%02d.jpg"),
            timeout=60,
        )  # fmt: skip
        stamps = re.findall(rb"pts_time:(-?[0-9.]+)", result.stderr)
        files = sorted(directory.glob(f"{video.id}-w{i}-*.jpg"))
        if result.returncode != 0 or len(files) < 2 or len(stamps) < len(files):
            continue
        data = [f.read_bytes() for f in files]
        try:
            window = OrderedWindow(
                source_asset_sha256=asset,
                duration_seconds=duration,
                selection_strategy=WINDOW_STRATEGY,
                frames=[
                    TimedFrame(
                        evidence_id=f"{video.id}:w{i}:f{k}",
                        asset_sha256=asset,
                        frame_sha256=sha256(b),
                        timestamp_seconds=max(0.0, float(stamps[k]) - offset),
                    )
                    for k, b in enumerate(data)
                ],
            )
        except ValidationError:
            continue  # sampled frames too far apart or out of range: not a usable burst
        results.append((window, data))
    return results


def burst_claims(
    video_id: str,
    index: int,
    window: OrderedWindow,
    output: WindowOutput,
    boundary: ObservationBoundary,
) -> tuple[list[Claim], list[dict[str, str]], int]:
    """Turn one burst's Observer output into gameplay_clip claims.

    Returns (claims, quarantined statements, statements excluded because the Observer labelled
    the burst cinematic or a title card, which cannot establish normal gameplay).
    """
    if output.context in EXCLUDED_CONTEXTS:
        return [], [], len(output.observations)
    times = {f.evidence_id: f.timestamp_seconds for f in window.frames}
    claims, quarantined = [], []
    for n, statement in enumerate(output.observations):
        claim_id = f"{video_id}:w{index}:s{n}"
        frame = EvidenceItem(
            id=statement.frame_ids[0], type=EvidenceType.GAMEPLAY_IMAGE, source="ordered-frame"
        )
        _, rejected = boundary.partition(
            [
                Observation(
                    id=claim_id,
                    evidence_id=frame.id,
                    kind="visual_text" if statement.kind == "visual_text" else "visual_fact",
                    text=statement.text,
                    image_region=statement.image_region,
                    observer_model="ordered-observer",
                )
            ],
            frame,
        )
        if rejected:
            quarantined.extend({"evidence_id": video_id, **r} for r in rejected)
            continue
        t0, t1 = times[statement.frame_ids[0]], times[statement.frame_ids[-1]]
        span = f"{t0:.1f}s" if t0 == t1 else f"{t0:.1f}-{t1:.1f}s"
        claims.append(
            Claim(
                id=claim_id,
                evidence_id=video_id,
                evidence_type=EvidenceType.GAMEPLAY_CLIP.value,
                kind={
                    "sequence_fact": "sequence_fact",
                    "visual_text": "screen_text",
                    "visual_fact": "visual_fact",
                }[statement.kind],
                text=f"[{output.context}, {span}] {statement.text}",
            )
        )
    return claims, quarantined, 0
