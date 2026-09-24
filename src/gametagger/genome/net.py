"""Fixed-host HTTPS fetching for rich mode.

Only named API hosts and the store/YouTube image and video CDNs are contacted. Media URLs come
from those APIs' own responses, never from free text. Redirects may only land on an allowed
host, responses are size-capped, and error messages never echo URLs (which can carry API keys).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

API_HOSTS = frozenset(
    {
        "store.steampowered.com",
        "en.wikipedia.org",
        "itunes.apple.com",
        "www.googleapis.com",
    }
)
# Suffixes match whole DNS labels: "steamstatic.com" allows "cdn.akamai.steamstatic.com".
MEDIA_HOST_SUFFIXES = frozenset(
    {
        "steamstatic.com",  # Steam screenshots and trailers
        "steamcdn-a.akamaihd.net",  # older Steam asset host (exact host only)
        "mzstatic.com",  # Apple App Store screenshots
        "ytimg.com",  # YouTube published still images
    }
)
MAX_JSON_BYTES = 3 * 1024 * 1024
USER_AGENT = "GameTagger/0.1 (evidence-backed game classification research prototype)"


class SourceError(RuntimeError):
    """A source could not be retrieved or did not describe the requested item."""


def host_allowed(host: str | None, *, media: bool) -> bool:
    if not host:
        return False
    host = host.lower().rstrip(".")
    if host in API_HOSTS:
        return True
    return media and any(host == s or host.endswith("." + s) for s in MEDIA_HOST_SUFFIXES)


def check_url(url: str, *, media: bool) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not host_allowed(parts.hostname, media=media):
        raise SourceError(f"Refusing to contact a host outside the allowlist: {parts.hostname}")
    return url


class _AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, media: bool):
        self.media = media

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, media=self.media)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_bytes(url: str, *, max_bytes: int, media: bool = False, timeout: float = 30) -> bytes:
    host = urlsplit(check_url(url, media=media)).hostname
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    opener = urllib.request.build_opener(_AllowlistRedirect(media))
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise SourceError(f"{host} returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"Could not reach {host}: {type(exc).__name__}") from None
    if len(body) > max_bytes:
        raise SourceError(f"Response from {host} exceeded the {max_bytes:,}-byte limit")
    return body


def fetch_json(url: str) -> Any:
    try:
        return json.loads(fetch_bytes(url, max_bytes=MAX_JSON_BYTES))
    except ValueError:
        raise SourceError(f"{urlsplit(url).hostname} returned invalid JSON") from None
