import hashlib
import subprocess

import pytest

from gametagger.observers.ordered import OrderedWindow, TimedFrame
from gametagger.workspace.media import extract_windows, inspect_video, video_available


@pytest.mark.skipif(
    not video_available(), reason="Local FFmpeg tools unavailable; capability disabled"
)
def test_synthetic_video_full_timeline_timestamps_hashes_and_idempotence(tmp_path):
    path = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=12",
            "-t",
            "4",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(path),
        ],
        check=True,
        timeout=15,
    )
    duration, _, _ = inspect_video(path)
    result = extract_windows(path, tmp_path / "frames")
    times = [f["timestamp"] for f in result["frames"]]
    assert times == sorted(set(times))
    assert times[0] < 0.3 and times[-1] > duration * 0.8
    assert len(times) <= 48 and not result["temporal_claims_validated"]
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    OrderedWindow(
        source_asset_sha256=sha,
        duration_seconds=duration,
        selection_strategy=result["strategy"],
        frames=[
            TimedFrame(
                evidence_id=str(i),
                asset_sha256=sha,
                frame_sha256=f["sha256"],
                timestamp_seconds=f["timestamp"],
            )
            for i, f in enumerate(result["frames"])
        ],
    )
    assert extract_windows(path, tmp_path / "frames")["frames"] == result["frames"]
    for f in result["frames"]:
        assert (
            hashlib.sha256((tmp_path / "frames" / f["file"]).read_bytes()).hexdigest()
            == f["sha256"]
        )


def test_unordered_windows_cannot_establish_timing():
    f = TimedFrame(evidence_id="x", asset_sha256="a", frame_sha256="b", timestamp_seconds=1)
    with pytest.raises(ValueError):
        OrderedWindow(
            source_asset_sha256="a", duration_seconds=3, selection_strategy="test", frames=[f, f]
        )


@pytest.mark.skipif(not video_available(), reason="Local FFmpeg unavailable")
def test_video_upload_job_and_frame_export_are_bound_to_each_saved_run(tmp_path):
    from fastapi.testclient import TestClient
    from test_workspace import HEAD, project, start

    from gametagger.workspace.app import create_app

    path = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=12",
            "-t",
            "2",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(path),
        ],
        check=True,
        timeout=15,
    )
    with TestClient(create_app(root=tmp_path / "private", local_dev=True)) as c:
        p = project(c)
        upload = c.post(
            f"/api/projects/{p['id']}/assets?name=synthetic.mp4&kind=video",
            content=path.read_bytes(),
            headers=HEAD,
        )
        assert upload.status_code == 200, upload.text
        a = start(c, p["id"], "first-video-run")
        assert a["status"] == "partial"
        frames = a["assets"][0]["frames"]
        assert frames and frames[-1]["timestamp"] > 1.5
        assert a["id"] in frames[0]["url"]
        original = c.get(frames[0]["url"]).content
        assert hashlib.sha256(original).hexdigest() == frames[0]["sha256"]
        b = start(c, p["id"], "second-video-run")
        assert b["id"] != a["id"]
        assert c.get(frames[0]["url"]).content == original
        assert start(c, p["id"], "first-video-run")["id"] == a["id"]
        assert c.get(frames[0]["url"].rsplit("/", 1)[0] + "/999").status_code == 404
        assert a["provenance"]["provider_calls"] == 0
