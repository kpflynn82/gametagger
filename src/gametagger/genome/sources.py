"""Source adapters for rich mode: store pages first, YouTube search as a backup.

Store and encyclopedia adapters take an exact identifier chosen by a person (a numeric Steam or
App Store ID, an exact Wikipedia title), never a free-text search, so a lookup cannot silently
pick a different game. Each returns attributed text plus references to the store's own
screenshots and trailers. YouTube is searched by title only when asked, through the official Data
API: it finds a video and YouTube's published still images, and never downloads the video itself.
Tests inject ``fetch``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from gametagger.domain import EvidenceType
from gametagger.genome.dossier import Reference, TextSource, clean_text
from gametagger.genome.net import SourceError, fetch_json, host_allowed

__all__ = ["SourceError", "fetch_json"]  # re-exported for callers of this module

MAX_SOURCE_TEXT = 6000
YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
Fetch = Callable[[str], Any]


@dataclass(frozen=True)
class MediaRef:
    """A screenshot or trailer URL taken from a trusted API response, not yet downloaded."""

    kind: Literal["image", "video", "hls"]
    url: str
    provider: str
    role: Literal["store_screenshot", "store_trailer", "video_still"]
    source_id: str
    title: str | None = None


@dataclass
class Fetched:
    text: TextSource | None = None
    media: list[MediaRef] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _https(url: Any) -> str | None:
    """Upgrade allowlisted CDN links to HTTPS; drop anything else."""
    if not isinstance(url, str) or not url:
        return None
    url = "https:" + url if url.startswith("//") else url
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not host_allowed(parts.hostname, media=True):
        return None
    return urlunsplit(("https", *parts[1:]))


def _names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [
        str(i.get("description")).strip()
        for i in items
        if isinstance(i, dict) and i.get("description")
    ]


def normal_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


# --------------------------------------------------------------------------- Steam


def _steam_trailer(movies: Any) -> MediaRef | None:
    if not isinstance(movies, list):
        return None
    movies = [m for m in movies if isinstance(m, dict)]
    for movie in sorted(movies, key=lambda m: not m.get("highlight")):  # highlights first
        mp4 = movie.get("mp4") if isinstance(movie.get("mp4"), dict) else {}
        options = [("video", mp4.get("480")), ("video", mp4.get("max"))]
        options.append(("hls", movie.get("hls_h264")))
        for kind, url in options:
            if url := _https(url):
                return MediaRef(
                    kind, url, "Steam store trailer", "store_trailer", "steam", movie.get("name")
                )
    return None


def steam_source(app_id: str | int, *, fetch: Fetch = fetch_json) -> Fetched:
    app = str(app_id).strip()
    if not app.isdigit():
        raise SourceError("A Steam app ID must be numeric")
    url = "https://store.steampowered.com/api/appdetails?" + urlencode(
        {"appids": app, "l": "english", "cc": "us"}
    )
    entry = (fetch(url) or {}).get(app) or {}
    data = entry.get("data") if entry.get("success") else None
    if not isinstance(data, dict) or not data.get("name"):
        raise SourceError(f"Steam has no public listing for app {app}")
    text = "\n".join(
        clean_text(str(data.get(key) or ""))
        for key in ("short_description", "about_the_game")
        if data.get(key)
    )[:MAX_SOURCE_TEXT]
    platforms = data.get("platforms") if isinstance(data.get("platforms"), dict) else {}
    descriptors = data.get("content_descriptors") or {}
    fields = {
        "store_genres": _names(data.get("genres")),
        "store_features": _names(data.get("categories")),
        "pricing": ["Free to play"] if data.get("is_free") else ["Requires purchase"],
        "controller_support": [str(data["controller_support"])]
        if data.get("controller_support")
        else [],
        "platforms": sorted(k for k, v in platforms.items() if v is True),
        "content_notes": [clean_text(str(descriptors["notes"]))]
        if isinstance(descriptors, dict) and descriptors.get("notes")
        else [],
        "developers": [str(d) for d in data.get("developers") or []],
        "publishers": [str(p) for p in data.get("publishers") or []],
    }
    media = [
        MediaRef("image", u, "Steam store screenshot", "store_screenshot", "steam")
        for shot in data.get("screenshots") or []
        if isinstance(shot, dict) and (u := _https(shot.get("path_full")))
    ]
    if trailer := _steam_trailer(data.get("movies")):
        media.append(trailer)
    return Fetched(
        text=TextSource(
            id="steam",
            type=EvidenceType.STORE_METADATA,
            provider="Steam store listing",
            uri=f"https://store.steampowered.com/app/{app}",
            reported_title=str(data["name"]),
            retrieved_at=_now(),
            text=text,
            fields={k: v for k, v in fields.items() if v},
        ),
        media=media,
    )


# --------------------------------------------------------------------------- Apple App Store


def app_store_source(app_id: str | int, *, country: str = "us", fetch: Fetch = fetch_json):
    app = str(app_id).strip().removeprefix("id")
    if not app.isdigit():
        raise SourceError("An App Store ID must be numeric (the digits after 'id' in its URL)")
    if not re.fullmatch(r"[a-z]{2}", country):
        raise SourceError("Use a two-letter App Store country code")
    url = "https://itunes.apple.com/lookup?" + urlencode(
        {"id": app, "country": country, "entity": "software"}
    )
    results = [
        r
        for r in (fetch(url) or {}).get("results") or []
        if isinstance(r, dict) and r.get("kind") == "software" and r.get("trackName")
    ]
    if not results:
        raise SourceError(f"The App Store has no public listing for app {app} ({country})")
    r = results[0]
    fields = {
        "store_genres": [str(g) for g in r.get("genres") or []],
        "pricing": [str(r["formattedPrice"])] if r.get("formattedPrice") else [],
        "content_rating": [str(r["contentAdvisoryRating"])]
        if r.get("contentAdvisoryRating")
        else [],
        "content_notes": [str(a) for a in r.get("advisories") or []],
        "developers": [str(r["artistName"])] if r.get("artistName") else [],
        "store_features": ["Game Center"] if r.get("isGameCenterEnabled") else [],
    }
    shots = r.get("screenshotUrls") or r.get("ipadScreenshotUrls") or []
    media = [
        MediaRef("image", u, "Apple App Store screenshot", "store_screenshot", "appstore")
        for shot in shots
        if (u := _https(shot))
    ]
    return Fetched(
        text=TextSource(
            id="appstore",
            type=EvidenceType.STORE_METADATA,
            provider="Apple App Store listing",
            uri=r.get("trackViewUrl") or f"https://apps.apple.com/{country}/app/id{app}",
            reported_title=str(r["trackName"]),
            retrieved_at=_now(),
            text=clean_text(str(r.get("description") or ""))[:MAX_SOURCE_TEXT],
            fields={k: v for k, v in fields.items() if v},
        ),
        media=media,
    )


# --------------------------------------------------------------------------- Google Play


def google_play_reference(package: str) -> Fetched:
    """Placeholder until a Google Play data service is chosen; Google has no public store API."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+", package):
        raise SourceError("A Google Play ID looks like com.studio.game")
    return Fetched(
        references=[
            Reference(
                id="googleplay",
                kind="store_page",
                provider="Google Play",
                uri="https://play.google.com/store/apps/details?" + urlencode({"id": package}),
                note=(
                    "Not analyzed: no Google Play data service is connected yet. Add the "
                    "listing text to the dossier by hand, or connect a service."
                ),
            )
        ]
    )


# --------------------------------------------------------------------------- Wikipedia


INFOBOX_FIELDS = {"genre": "genres", "modes": "modes", "platforms": "platforms"}


def _infobox_values(wikitext: str, name: str) -> list[str]:
    match = re.search(rf"^\s*\|\s*{name}\s*=(.*)$", wikitext, re.IGNORECASE | re.MULTILINE)
    if not match:
        return []
    value = match.group(1)
    value = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", value)
    value = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", value)
    value = re.sub(r"\{\{\s*(?:hlist|ubl|unbulleted list|plainlist)\s*\|", "", value, flags=re.I)
    value = re.sub(r"\{\{[^{}]*\}\}|[{}]", "", value)
    parts = re.split(r"<br\s*/?>|[|,•*\n]", clean_text(value))
    return [p.strip(" '") for p in parts if p.strip(" '")]


def wikipedia_source(title: str, *, fetch: Fetch = fetch_json) -> Fetched:
    title = title.strip()
    if not title or len(title) > 250:
        raise SourceError("Supply the exact Wikipedia article title")
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
        "prop": "extracts|revisions",
        "exintro": "1",
        "explaintext": "1",
        "rvprop": "content",
        "rvslots": "main",
        "titles": title,
    }
    payload = fetch("https://en.wikipedia.org/w/api.php?" + urlencode(params)) or {}
    pages = (payload.get("query") or {}).get("pages") or []
    page = pages[0] if pages else {}
    if not page or page.get("missing") or page.get("invalid") or not page.get("extract"):
        raise SourceError(f"Wikipedia has no article titled '{title}'")
    revisions = page.get("revisions") or [{}]
    wikitext = ((revisions[0].get("slots") or {}).get("main") or {}).get("content", "")
    fields = {
        key: values
        for name, key in INFOBOX_FIELDS.items()
        if (values := _infobox_values(wikitext, name))
    }
    return Fetched(
        text=TextSource(
            id="wikipedia",
            type=EvidenceType.WIKIPEDIA,
            provider="English Wikipedia article introduction and infobox",
            uri="https://en.wikipedia.org/wiki/" + quote(page["title"].replace(" ", "_")),
            reported_title=page["title"],
            retrieved_at=_now(),
            text=str(page["extract"])[:MAX_SOURCE_TEXT],
            fields=fields,
        )
    )


# --------------------------------------------------------------------------- YouTube (API only)


def _iso_seconds(value: str | None) -> int | None:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not match or not any(match.groups()):
        return None
    h, m, s = (int(g or 0) for g in match.groups())
    return h * 3600 + m * 60 + s


def youtube_search(
    title: str,
    api_key: str,
    *,
    official_names: tuple[str, ...] = (),
    fetch: Fetch = fetch_json,
) -> Fetched:
    """Find an official trailer, else the most-viewed gameplay video, whose title names the game.

    Uses search.list (100 quota units per search) and videos.list (1 unit). Returns a reference
    to the video plus YouTube's published still frames; the video itself is never downloaded.
    """
    wanted = normal_title(title)
    if not wanted or not api_key:
        raise SourceError("YouTube search needs a game title and YOUTUBE_API_KEY")
    official = {normal_title(n) for n in official_names if normal_title(n)}

    def candidates(query: str, order: str) -> list[dict]:
        search = fetch(
            f"{YOUTUBE_API}/search?"
            + urlencode(
                {
                    "part": "snippet",
                    "type": "video",
                    "maxResults": "8",
                    "q": query,
                    "order": order,
                    "key": api_key,
                }
            )
        )
        ids = [
            item["id"]["videoId"]
            for item in (search or {}).get("items") or []
            if isinstance(item.get("id"), dict)
            and re.fullmatch(r"[A-Za-z0-9_-]{11}", str(item["id"].get("videoId", "")))
        ]
        if not ids:
            return []
        videos = fetch(
            f"{YOUTUBE_API}/videos?"
            + urlencode(
                {"part": "snippet,statistics,contentDetails", "id": ",".join(ids), "key": api_key}
            )
        )
        return [
            v
            for v in (videos or {}).get("items") or []
            if wanted in normal_title(str((v.get("snippet") or {}).get("title", "")))
        ]

    def views(video: dict) -> int:
        count = (video.get("statistics") or {}).get("viewCount")
        return int(count) if str(count).isdigit() else 0

    def is_official(video: dict) -> bool:
        channel = normal_title(str((video.get("snippet") or {}).get("channelTitle", "")))
        return bool(channel) and any(n in channel or channel in n for n in official)

    trailers = [
        v
        for v in candidates(f"{title} official trailer", "relevance")
        if "trailer" in str(v["snippet"].get("title", "")).casefold()
    ]
    if trailers:
        chosen = max(trailers, key=lambda v: (is_official(v), views(v)))
        kind = "trailer"
    else:
        gameplay = candidates(f"{title} gameplay", "viewCount")
        if not gameplay:
            raise SourceError(f"YouTube found no trailer or gameplay video titled '{title}'")
        chosen, kind = max(gameplay, key=views), "gameplay video"
    video_id = chosen["id"]
    snippet = chosen.get("snippet") or {}
    confirmed = is_official(chosen)
    reference = Reference(
        id="youtube",
        kind="video",
        provider="YouTube (found by title search)",
        uri=f"https://www.youtube.com/watch?v={video_id}",
        title=str(snippet.get("title") or "") or None,
        channel=str(snippet.get("channelTitle") or "") or None,
        view_count=views(chosen),
        duration=(chosen.get("contentDetails") or {}).get("duration"),
        official=confirmed,
        note=(
            f"Best {kind} match. Channel matches the store's developer/publisher."
            if confirmed
            else f"Best {kind} match. Channel not confirmed as official; check it is this game."
        ),
    )
    stills = [
        MediaRef(
            "image",
            f"https://i.ytimg.com/vi/{video_id}/hq{n}.jpg",
            f"YouTube still from {kind} ({'official' if confirmed else 'unconfirmed'} channel)",
            "video_still",
            "youtube",
        )
        for n in (1, 2, 3)
    ]
    return Fetched(media=stills, references=[reference])
