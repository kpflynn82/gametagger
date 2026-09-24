"""Fixed-host text source adapters for rich mode (Steam store API, English Wikipedia API).

Each adapter takes an exact identifier chosen by a person (a numeric Steam app ID or an exact
Wikipedia title), never a free-text search, so a lookup cannot silently pick a different game.
The title each source reports is kept for identity checks. Only two fixed HTTPS hosts are
contacted; redirects are refused and response size is capped. Tests inject ``fetch``.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from gametagger.domain import EvidenceType
from gametagger.genome.dossier import TextSource, clean_text

ALLOWED_HOSTS = {"store.steampowered.com", "en.wikipedia.org"}
MAX_RESPONSE_BYTES = 3 * 1024 * 1024
MAX_SOURCE_TEXT = 6000
USER_AGENT = "GameTagger/0.1 (evidence-backed game classification research prototype)"
Fetch = Callable[[str], Any]


class SourceError(RuntimeError):
    """A source could not be retrieved or did not describe the requested item."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch_json(url: str) -> Any:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise SourceError("Only fixed HTTPS source hosts may be contacted")
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise SourceError(f"{parts.hostname} returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SourceError(f"Could not reach {parts.hostname}: {type(exc).__name__}") from None
    if len(body) > MAX_RESPONSE_BYTES:
        raise SourceError("Source response exceeded the size limit")
    return json.loads(body)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [
        str(i.get("description")).strip()
        for i in items
        if isinstance(i, dict) and i.get("description")
    ]


def steam_source(app_id: str | int, *, fetch: Fetch = fetch_json) -> TextSource:
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
    return TextSource(
        id="steam",
        type=EvidenceType.STORE_METADATA,
        provider="Steam store listing",
        uri=f"https://store.steampowered.com/app/{app}",
        reported_title=str(data["name"]),
        retrieved_at=_now(),
        text=text,
        fields={k: v for k, v in fields.items() if v},
    )


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


def wikipedia_source(title: str, *, fetch: Fetch = fetch_json) -> TextSource:
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
    return TextSource(
        id="wikipedia",
        type=EvidenceType.WIKIPEDIA,
        provider="English Wikipedia article introduction and infobox",
        uri="https://en.wikipedia.org/wiki/" + quote(page["title"].replace(" ", "_")),
        reported_title=page["title"],
        retrieved_at=_now(),
        text=str(page["extract"])[:MAX_SOURCE_TEXT],
        fields=fields,
    )
