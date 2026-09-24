"""Rich mode media: store screenshots/trailers, YouTube backup, frame bursts. No network."""

import functools
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from gametagger.domain import EvidenceItem, EvidenceType
from gametagger.evidence import prepare_evidence
from gametagger.genome import cli, sources
from gametagger.genome.dossier import Dossier, TextSource, VideoSource
from gametagger.genome.engine import GenomeEngine, GenomePipeline
from gametagger.genome.media import (
    FRAME_SIDE,
    OBSERVER_IMAGE_SIDE,
    assemble_hls,
    burst_claims,
    download_media,
    frame_bursts,
    normalize_image,
    probe_video,
)
from gametagger.genome.net import SourceError, _AllowlistRedirect, check_url, host_allowed
from gametagger.genome.sources import (
    MediaRef,
    app_store_source,
    google_play_reference,
    steam_source,
    youtube_search,
)
from gametagger.genome.vocabulary import load_vocabulary
from gametagger.observers.boundary import ObservationBoundary
from gametagger.observers.ordered import OrderedWindow, TimedFrame, WindowAttempt, WindowOutput
from gametagger.observers.ordered import digest as window_digest

needs_ffmpeg = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("ffmpeg") is None, reason="Local FFmpeg unavailable"
)


def png(width=64, height=48, color="green") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, "PNG")
    return out.getvalue()


# --------------------------------------------------------------------------- network guard


@pytest.mark.parametrize(
    "host, media, allowed",
    [
        ("store.steampowered.com", False, True),
        ("shared.akamai.steamstatic.com", True, True),
        ("shared.akamai.steamstatic.com", False, False),  # media hosts only for media
        ("evilsteamstatic.com", True, False),  # suffix must match a whole label
        ("steamstatic.com.attacker.net", True, False),
        ("is1-ssl.mzstatic.com", True, True),
        ("i.ytimg.com", True, True),
        ("x.akamaihd.net", True, False),  # only the exact Steam asset host is allowed
        ("169.254.169.254", True, False),
        (None, True, False),
    ],
)
def test_host_allowlist(host, media, allowed):
    assert host_allowed(host, media=media) is allowed


def test_http_and_offlist_redirects_are_refused():
    with pytest.raises(SourceError):
        check_url("http://store.steampowered.com/api", media=False)
    with pytest.raises(SourceError, match="allowlist"):
        _AllowlistRedirect(media=True).redirect_request(
            None, None, 302, "Found", {}, "https://example.com/x.mp4"
        )


# --------------------------------------------------------------------------- store adapters


def steam_payload(movies=None, screenshots=6):
    return {
        "4242": {
            "success": True,
            "data": {
                "name": "Synthetic Blade",
                "short_description": "A sword-fighting adventure.",
                "developers": ["Test Studio"],
                "screenshots": [
                    {"path_full": f"https://shared.akamai.steamstatic.com/ss_{i}.jpg"}
                    for i in range(screenshots)
                ]
                + [{"path_full": "https://example.com/not-a-steam-cdn.jpg"}],
                "movies": movies or [],
            },
        }
    }


def test_steam_collects_screenshots_and_prefers_highlight_mp4():
    movies = [
        {"name": "Old", "mp4": {"480": "https://video.akamai.steamstatic.com/old.mp4"}},
        {
            "name": "Launch Trailer",
            "highlight": True,
            "mp4": {"max": "http://video.akamai.steamstatic.com/launch.mp4"},
        },
    ]
    fetched = steam_source("4242", fetch=lambda url: steam_payload(movies))
    shots = [m for m in fetched.media if m.kind == "image"]
    assert len(shots) == 6  # the off-allowlist screenshot is dropped
    trailer = fetched.media[-1]
    assert trailer.title == "Launch Trailer" and trailer.role == "store_trailer"
    assert trailer.url == "https://video.akamai.steamstatic.com/launch.mp4"  # upgraded to https


def test_steam_falls_back_to_hls_trailer():
    movies = [{"name": "T", "hls_h264": "https://video.fastly.steamstatic.com/t/master.m3u8"}]
    fetched = steam_source("4242", fetch=lambda url: steam_payload(movies))
    assert fetched.media[-1].kind == "hls"


def test_app_store_lookup():
    urls = []
    payload = {
        "results": [
            {
                "kind": "software",
                "trackName": "Pocket Farm",
                "description": "Grow crops.\nTrade with friends.",
                "genres": ["Games", "Simulation"],
                "formattedPrice": "Free",
                "contentAdvisoryRating": "4+",
                "advisories": ["Infrequent/Mild Cartoon Violence"],
                "artistName": "Test Studio",
                "isGameCenterEnabled": True,
                "screenshotUrls": ["https://is1-ssl.mzstatic.com/a.png", "https://evil.test/b.png"],
                "trackViewUrl": "https://apps.apple.com/us/app/id123",
            }
        ]
    }

    def fetch(url):
        urls.append(url)
        return payload

    fetched = app_store_source("id123", fetch=fetch)
    assert parse_qs(urlsplit(urls[0]).query)["id"] == ["123"]
    assert fetched.text.reported_title == "Pocket Farm"
    assert fetched.text.fields["pricing"] == ["Free"]
    assert fetched.text.fields["store_features"] == ["Game Center"]
    assert [m.url for m in fetched.media] == ["https://is1-ssl.mzstatic.com/a.png"]
    for bad in ("abc", "12x"):
        with pytest.raises(SourceError):
            app_store_source(bad, fetch=fetch)
    with pytest.raises(SourceError):
        app_store_source("999", fetch=lambda url: {"results": []})


def test_google_play_is_a_reference_until_a_service_is_connected():
    fetched = google_play_reference("com.studio.game")
    assert fetched.text is None and fetched.media == []
    assert fetched.references[0].uri.endswith("id=com.studio.game")
    assert "no Google Play data service" in fetched.references[0].note
    with pytest.raises(SourceError):
        google_play_reference("not a package")


# --------------------------------------------------------------------------- YouTube (API only)


def youtube_fetch(videos_by_query):
    """Fake Data API: search.list returns IDs for a query, videos.list returns details."""
    catalog = {v["id"]: v for vs in videos_by_query.values() for v in vs}
    calls = []

    def fetch(url):
        calls.append(url)
        query = parse_qs(urlsplit(url).query)
        if url.split("?")[0].endswith("/search"):
            return {"items": [{"id": {"videoId": v["id"]}} for v in videos_by_query[query["q"][0]]]}
        return {"items": [catalog[i] for i in query["id"][0].split(",")]}

    return fetch, calls


def video(vid, title, channel, views):
    return {
        "id": vid,
        "snippet": {"title": title, "channelTitle": channel},
        "statistics": {"viewCount": str(views)},
        "contentDetails": {"duration": "PT2M3S"},
    }


def test_youtube_prefers_official_trailer_and_never_leaks_the_key():
    fetch, calls = youtube_fetch(
        {
            "Synthetic Blade official trailer": [
                video("aaaaaaaaaaa", "Synthetic Blade - Launch Trailer", "Fan Uploads", 900_000),
                video("bbbbbbbbbbb", "Synthetic Blade Official Trailer", "Test Studio", 50_000),
                video("ccccccccccc", "Other Game Trailer", "Test Studio", 5_000_000),
            ]
        }
    )
    found = youtube_search(
        "Synthetic Blade", "SECRET-KEY", official_names=("Test Studio",), fetch=fetch
    )
    ref = found.references[0]
    assert ref.uri == "https://www.youtube.com/watch?v=bbbbbbbbbbb" and ref.official is True
    assert [m.url.rsplit("/", 1)[1] for m in found.media] == ["hq1.jpg", "hq2.jpg", "hq3.jpg"]
    assert all(m.role == "video_still" and m.kind == "image" for m in found.media)
    assert "SECRET-KEY" not in json.dumps(ref.model_dump()) + str(found.media)
    assert len(calls) == 2  # one search, one details lookup: about 101 quota units


def test_youtube_falls_back_to_most_viewed_gameplay():
    fetch, calls = youtube_fetch(
        {
            "Synthetic Blade official trailer": [
                video("ddddddddddd", "Unrelated Trailer", "Someone", 10),
            ],
            "Synthetic Blade gameplay": [
                video("eeeeeeeeeee", "Synthetic Blade gameplay part 1", "Player A", 1_000),
                video("fffffffffff", "SYNTHETIC BLADE - 1 hour gameplay", "Player B", 20_000),
            ],
        }
    )
    found = youtube_search("Synthetic Blade", "k", fetch=fetch)
    ref = found.references[0]
    assert ref.uri.endswith("fffffffffff") and ref.official is False
    assert "not confirmed" in ref.note
    empty, _ = youtube_fetch({"X official trailer": [], "X gameplay": []})
    with pytest.raises(SourceError):
        youtube_search("X", "k", fetch=empty)


# --------------------------------------------------------------------------- images


def test_normalize_image_reencodes_and_bounds_size():
    out = normalize_image(png(4000, 2000))
    with Image.open(io.BytesIO(out)) as image:
        assert image.format == "JPEG" and max(image.size) == OBSERVER_IMAGE_SIDE
    frames = [Image.new("RGB", (8, 8), c) for c in ("red", "blue")]
    gif = io.BytesIO()
    frames[0].save(gif, "GIF", save_all=True, append_images=frames[1:])
    for bad in (b"not an image", gif.getvalue()):
        with pytest.raises(ValueError):
            normalize_image(bad)


def test_prepare_evidence_accepts_jpeg(tmp_path):
    path = tmp_path / "shot.jpg"
    Image.new("RGB", (32, 32), "blue").save(path, "JPEG")
    item, data = prepare_evidence(
        EvidenceItem(id="shot", type=EvidenceType.GAMEPLAY_IMAGE, source="t", uri=str(path))
    )
    assert item.media_type == "image/jpeg" and data == path.read_bytes()


def test_download_media_caps_per_source_and_keeps_first_trailer(tmp_path):
    refs = [
        MediaRef(
            "image", f"https://a.steamstatic.com/{i}.png", "Steam", "store_screenshot", "steam"
        )
        for i in range(5)
    ]
    refs += [
        MediaRef("image", "https://i.ytimg.com/vi/x/hq1.jpg", "YouTube", "video_still", "youtube"),
        MediaRef("video", "https://v.steamstatic.com/a.mp4", "Steam", "store_trailer", "steam"),
        MediaRef("video", "https://v.steamstatic.com/b.mp4", "Steam", "store_trailer", "steam"),
        MediaRef("image", "https://a.steamstatic.com/bad.png", "Steam", "store_screenshot", "x"),
    ]

    def fetch(url, *, max_bytes, media, timeout=30):
        if url.endswith("bad.png"):
            return b"garbage"
        return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64 if url.endswith(".mp4") else png()

    images, videos, notes = download_media(
        refs, tmp_path, max_screenshots=3, video=True, fetch=fetch
    )
    assert [i.id for i in images] == ["steam-shot1", "steam-shot2", "steam-shot3", "youtube-still1"]
    assert all(Path(i.path).exists() and i.sha256 for i in images)
    assert [v.id for v in videos] == ["steam-trailer"] and videos[0].path.endswith(".mp4")
    assert len(notes) == 1 and "could not be safely decoded" in notes[0]
    _, none, _ = download_media(refs, tmp_path / "t", max_screenshots=0, video=False, fetch=fetch)
    assert none == []


# --------------------------------------------------------------------------- HLS


def hls_fetch(files):
    asked = []

    def fetch(url, *, max_bytes, media, timeout=30):
        asked.append(url)
        data = files[urlsplit(url).path]
        assert media and len(data) <= max_bytes
        return data

    return fetch, asked


def test_hls_picks_smallest_rendition_of_at_least_360p_and_joins_segments():
    files = {
        "/t/master.m3u8": (
            b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=200000,RESOLUTION=426x240\nlow/v.m3u8\n"
            b"#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=1280x720\nhd/v.m3u8\n"
            b"#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360\nsd/v.m3u8\n"
        ),
        "/t/sd/v.m3u8": (
            b'#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:4,\nseg0.m4s\n#EXTINF:4,\nseg1.m4s\n'
        ),
        "/t/sd/init.mp4": b"INIT",
        "/t/sd/seg0.m4s": b"AAAA",
        "/t/sd/seg1.m4s": b"BBBB",
    }
    fetch, asked = hls_fetch(files)
    data = assemble_hls("https://video.fastly.steamstatic.com/t/master.m3u8", fetch=fetch)
    assert data == b"INITAAAABBBB"
    assert [urlsplit(u).path for u in asked][1] == "/t/sd/v.m3u8"


@pytest.mark.parametrize(
    "playlist, message",
    [
        (b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="k"\nseg.ts\n', "Encrypted"),
        (b"#EXTM3U\n" + b"#EXTINF:1,\ns.ts\n" * 601, "too many"),
        (b"not a playlist", "Not an HLS"),
    ],
)
def test_hls_rejects_unsupported_streams(playlist, message):
    fetch, _ = hls_fetch({"/v.m3u8": playlist})
    with pytest.raises(ValueError, match=message):
        assemble_hls("https://video.fastly.steamstatic.com/v.m3u8", fetch=fetch)


# --------------------------------------------------------------------------- frame bursts


@pytest.fixture
def trailer(tmp_path):
    if sys.platform == "win32" or shutil.which("ffmpeg") is None:
        pytest.skip("Local FFmpeg unavailable")
    path = tmp_path / "trailer.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24", "-t",
         "75", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)],
        check=True,
        timeout=60,
    )  # fmt: skip
    return VideoSource(id="steam-trailer", path=str(path), provider="Steam store trailer")


@needs_ffmpeg
def test_probe_and_bursts_cover_a_trailer_longer_than_a_minute(trailer, tmp_path):
    duration, offset, width, height = probe_video(Path(trailer.path))
    assert duration == pytest.approx(75, abs=0.1) and offset == pytest.approx(0, abs=0.1)
    assert (width, height) == (320, 240)
    bursts = frame_bursts(trailer, tmp_path / "frames", windows=4, frames=5)
    assert len(bursts) == 4
    starts = [w.frames[0].timestamp_seconds for w, _ in bursts]
    assert starts == sorted(starts) and starts[0] >= 75 * 0.05 and starts[-1] <= 75 * 0.95
    for window, frames in bursts:
        assert window.duration_seconds == pytest.approx(75, abs=0.1)
        times = [f.timestamp_seconds for f in window.frames]
        assert len(frames) == 5 and all(
            0 < b - a <= 0.5 for a, b in zip(times, times[1:], strict=False)
        )
        with Image.open(io.BytesIO(frames[0])) as image:
            assert image.format == "JPEG" and max(image.size) <= FRAME_SIDE
    changed = trailer.model_copy(update={"sha256": "0" * 64})
    with pytest.raises(ValueError, match="changed"):
        frame_bursts(changed, tmp_path / "frames")


# --------------------------------------------------------------------------- burst claims


def window(duration=95.0):
    asset = "a" * 64
    frames = [
        TimedFrame(
            evidence_id=f"v:w0:f{k}",
            asset_sha256=asset,
            frame_sha256=f"{k}" * 64,
            timestamp_seconds=40 + 0.4 * k,
        )
        for k in range(3)
    ]
    return OrderedWindow(
        source_asset_sha256=asset, duration_seconds=duration, selection_strategy="t", frames=frames
    )


def output(context="gameplay"):
    return WindowOutput(
        context=context,
        observations=[
            {
                "kind": "sequence_fact",
                "text": "The figure moves left as the enemy swings.",
                "frame_ids": ["v:w0:f0", "v:w0:f1", "v:w0:f2"],
            },
            {"kind": "visual_fact", "text": "It is Souls-like.", "frame_ids": ["v:w0:f1"]},
            {
                "kind": "visual_text",
                "text": "PRESS A",
                "frame_ids": ["v:w0:f2"],
                "image_region": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1},
            },
        ],
    )


def test_ordered_window_accepts_full_length_trailers(taxonomy):
    assert window(95.0).duration_seconds == 95.0
    with pytest.raises(ValueError):
        window(4000.0)
    out = output()
    with pytest.raises(ValueError):
        out.validate_against(window(), taxonomy)  # default still rejects taxonomy words
    assert out.validate_against(window(), taxonomy, enforce_boundary=False) is out


def test_burst_claims_quarantine_and_exclude_cinematics(taxonomy):
    boundary = ObservationBoundary(taxonomy)
    claims, quarantined, excluded = burst_claims("v", 0, window(), output(), boundary)
    assert [c.kind for c in claims] == ["sequence_fact", "screen_text"]
    assert claims[0].evidence_type == "gameplay_clip"
    assert claims[0].text == "[gameplay, 40.0-40.8s] The figure moves left as the enemy swings."
    assert [q["text"] for q in quarantined] == ["It is Souls-like."] and excluded == 0
    claims, quarantined, excluded = burst_claims("v", 0, window(), output("cinematic"), boundary)
    assert claims == [] and quarantined == [] and excluded == 3


# --------------------------------------------------------------------------- pipeline + CLI


class ScriptedOrdered:
    model = "scripted-vision"

    def __init__(self, fail_first=False):
        self.fail_first, self.calls = fail_first, 0

    def observe_window(self, window, *, frames):
        self.calls += 1
        base = dict(
            window_sha256=window.sha256,
            request_sha256="0" * 64,
            prompt_version="t",
            prompt_sha256="0" * 64,
            requested_model=self.model,
            sdk_version="t",
        )
        if self.fail_first and self.calls == 1:
            return WindowAttempt(status="error", error_code="transport", **base)
        ids = [f.evidence_id for f in window.frames]
        out = WindowOutput(
            context="gameplay",
            observations=[
                {
                    "kind": "sequence_fact",
                    "text": "The figure rolls sideways.",
                    "frame_ids": ids[:2],
                }
            ],
        )
        return WindowAttempt(
            status="valid",
            returned_model=self.model,
            response_sha256="1" * 64,
            output=out,
            output_sha256=window_digest(out.model_dump(mode="json")),
            **base,
        )


class RecordingGateway:
    model = "recording"

    def __init__(self):
        self.states = {}

    def run(self, *, state, specs):
        answers = {}
        for key, spec in specs.items():
            self.states[key] = state
            options = list(spec.criteria)
            answers[key] = {
                "type": "choice",
                "choice": "insufficient_evidence",
                "confidence": 1.0,
                "probabilities": {o: float(o == "insufficient_evidence") for o in options},
            }
        return {
            "model": "jev-t",
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "answers": answers,
        }


@needs_ffmpeg
def test_trailer_bursts_reach_timing_tags(taxonomy, trailer):
    gateway = RecordingGateway()
    engine = GenomeEngine(taxonomy, load_vocabulary(taxonomy), gateway)
    dossier = Dossier(game_id="g", videos=[trailer])
    observer = ScriptedOrdered(fail_first=True)
    profile = GenomePipeline(engine, None, observer, bursts=3, frames_per_burst=4).analyze(
        dossier, offline=True
    )
    summary = profile.media[0]
    assert summary["bursts"] == 3 and summary["errors"] == 1 and summary["claims"] == 2
    assert "The figure rolls sideways." in gateway.states["mechanic_dodge_roll"]
    assert "gameplay_clip" in gateway.states["mechanic_real_time_combat"]
    assert profile.provenance["burst_strategy"].startswith("even-bursts-v1")
    assert [r["status"] for r in profile.provenance["observer_requests"]] == [
        "error",
        "valid",
        "valid",
    ]


@needs_ffmpeg
def test_unobserved_video_is_sampled_and_reported(taxonomy, trailer):
    engine = GenomeEngine(taxonomy, load_vocabulary(taxonomy), RecordingGateway())
    prepared = GenomePipeline(engine, bursts=2, frames_per_burst=3).prepare(
        Dossier(game_id="g", videos=[trailer]), observe=False
    )
    assert prepared.observer_calls == 2 and len(prepared.observer_image_sizes) == 6
    assert prepared.observer_estimate()["approx_input_tokens_total"] > 0
    assert any("not observed" in w for w in prepared.warnings)


STEAM_NO_TRAILER = {
    "4242": {
        "success": True,
        "data": {
            "name": "Synthetic Blade",
            "short_description": "A sword-fighting adventure.",
            "developers": ["Test Studio"],
            "screenshots": [{"path_full": "https://shared.akamai.steamstatic.com/a.png"}],
        },
    }
}


def patch_sources(monkeypatch, youtube=None):
    monkeypatch.setattr(
        cli, "steam_source", lambda x: steam_source(x, fetch=lambda url: STEAM_NO_TRAILER)
    )
    monkeypatch.setattr(
        cli,
        "download_media",
        functools.partial(download_media, fetch=lambda url, **kw: png(1920, 1080)),
    )
    calls = []

    def fake_youtube(title, key, *, official_names=()):
        calls.append((title, key, official_names))
        return sources.Fetched(
            media=[
                MediaRef(
                    "image", "https://i.ytimg.com/vi/x/hq1.jpg", "YT", "video_still", "youtube"
                )
            ],
            references=[
                sources.Reference(id="youtube", kind="video", provider="YouTube", uri="https://y/x")
            ],
        )

    monkeypatch.setattr(cli, "youtube_search", youtube or fake_youtube)
    return calls


def test_cli_uses_youtube_only_when_store_has_no_trailer(monkeypatch, tmp_path, capsys):
    calls = patch_sources(monkeypatch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")
    saved = tmp_path / "out" / "g.dossier.json"
    saved.parent.mkdir()
    cli.main(["--game-id", "g", "--steam-app", "4242", "--media-dir", str(tmp_path / "m"),
              "--save-dossier", str(saved)])  # fmt: skip
    out = capsys.readouterr().out
    assert calls == [("Synthetic Blade", "k", ("Test Studio",))]
    assert "Screenshots: 2" in out and "Reference (not analyzed as video): YouTube" in out
    dossier = json.loads(saved.read_text())
    assert dossier["title"] == "Synthetic Blade"
    assert all(not Path(i["path"]).is_absolute() for i in dossier["images"])
    cli.main([str(saved), "--youtube", "never"])  # saved relative paths still resolve
    assert "Screenshots: 2" in capsys.readouterr().out


def test_cli_notes_missing_youtube_key_and_text_only_mode(monkeypatch, tmp_path, capsys):
    calls = patch_sources(monkeypatch)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    cli.main(["--game-id", "g", "--steam-app", "4242", "--media-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert calls == [] and "YOUTUBE_API_KEY" in captured.err
    cli.main(["--game-id", "g", "--steam-app", "4242", "--no-media", "--youtube", "always"])
    assert calls == [] and "Screenshots" not in capsys.readouterr().out


def test_cli_live_refuses_media_without_observer_and_over_vision_cap(monkeypatch, tmp_path):
    patch_sources(monkeypatch)
    monkeypatch.setenv("TYPESAFE_API_KEY", "placeholder")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "TypeSafeGateway", lambda model: RecordingGateway())
    args = ["--game-id", "g", "--steam-app", "4242", "--media-dir", str(tmp_path), "--live"]
    with pytest.raises(SystemExit):
        cli.main(args + ["--youtube", "never"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder")
    with pytest.raises(SystemExit):
        cli.main(
            args + ["--youtube", "never", "--observer-model", "m", "--max-observer-tokens", "10"]
        )


def test_text_source_rejects_media_types():
    with pytest.raises(ValueError):
        TextSource(id="v", type=EvidenceType.GAMEPLAY_CLIP, provider="p", text="x")
