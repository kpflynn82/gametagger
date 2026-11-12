"""Fortnite Radar: keep a daily record of Fortnite Discover's top islands and their numbers.

Standard library only, so the scheduled GitHub workflow runs it without installing the package:

    PYTHONPATH=src python -m gametagger.fortnite_radar run --out <data-dir>

Every source is Epic's public, unauthenticated Fortnite Data API (the "ecosystem" API that Epic
publishes for creators and third-party analytics sites):

- /genres                          the 13 Discover genres
- /genres/{slug}/rankings          Epic's own rank order of islands inside one genre
- /islands/{code}                  title, creator, and the tags the creator chose
- /islands/{code}/metrics/day      daily minutes played, players, peak players, favorites,
                                   recommendations, and day-1 / day-7 retention

Why this runs daily: the API only serves a short window of history (seven days at most), so a
trend line longer than a week has to be saved as it happens. Nothing here can be backfilled.

What these numbers are and are not: they are Epic's published per-island observations. The
genre and tags are whatever the creator selected; this module never assigns a genre or a tag.
A metric the API leaves empty is stored as null and means "not reported", never zero.

Outputs in the data directory:
- rankings/YYYY-MM-DD.json  each genre's rank order (up to 100 islands) as last seen that UTC day
- islands.json              every island tracked so far: title, creator, creator tags, the
                            genres and best rank it was seen at, first and last ranked dates
- metrics/<code>.json       one file per island: every daily bucket seen so far, merged
- summary.json              the latest ranks joined to the latest numbers (what a dashboard reads)
- last_run.json             when the last run happened, what it covered, and anything that failed
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

USER_AGENT = "gametagger-fortnite-radar/1.0 (+https://github.com/kpflynn82/gametagger)"
API = "https://api.fortnite.com/ecosystem/v1"

VALUE_METRICS = (
    "averageMinutesPerPlayer",
    "peakCCU",
    "favorites",
    "minutesPlayed",
    "recommendations",
    "plays",
    "uniquePlayers",
)
RETENTION_FIELDS = ("d1", "d7")

DEFAULT_TOP = 50  # islands per genre that get daily numbers
RANKS_KEPT = 100  # rank order saved per genre (one request each, so depth is free)
KEEP_TRACKING_DAYS = 14  # keep collecting an island this long after it leaves the top
MAX_TRACKED = 1500
HISTORY_DAYS = 7  # the longest window the API serves
FAILURE_LIMIT = 25  # consecutive failed islands before the run stops asking

Fetch = Callable[[str], Any]


# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------


def http_json(url: str, *, retries: int = 5, pause: float = 3.0) -> Any:
    """GET a JSON document, backing off on rate limits and transient errors."""
    last: Exception | None = None
    for attempt in range(retries):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        wait = pause * (2**attempt)
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as err:
            last = err
            if err.code not in (429, 500, 502, 503, 504):
                raise
            retry_after = err.headers.get("Retry-After") if err.headers else None
            if retry_after and retry_after.strip().isdigit():
                wait = max(wait, float(retry_after))
        except (URLError, TimeoutError) as err:
            last = err
        if attempt < retries - 1:
            time.sleep(min(wait, 60.0))
    assert last is not None
    raise last


def polite(fetch: Fetch, delay: float) -> Fetch:
    """Wrap a fetcher so consecutive calls are spaced out."""

    def wrapped(url: str) -> Any:
        if delay:
            time.sleep(delay)
        return fetch(url)

    return wrapped


def _status(err: Exception) -> str:
    if isinstance(err, HTTPError):
        return f"HTTP {err.code}"
    return type(err).__name__


# ---------------------------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------------------------


def fetch_genres(fetch: Fetch) -> list[dict[str, str]]:
    payload = fetch(f"{API}/genres")
    rows = payload.get("data", payload) if isinstance(payload, dict) else payload
    genres = [
        {"slug": str(row["slug"]), "displayName": str(row.get("displayName") or row["slug"])}
        for row in rows or []
        if isinstance(row, dict) and row.get("slug")
    ]
    if not genres:
        raise ValueError("the genres endpoint returned no genres")
    return genres


def fetch_rankings(fetch: Fetch, slug: str) -> dict[str, Any]:
    """One genre's rank order: the first page (up to 100 islands), in Epic's order."""
    payload = fetch(f"{API}/genres/{quote(slug)}/rankings")
    meta = payload.get("meta") or {}
    ranked = [
        (int(row["rank"]), str(row["islandCode"]))
        for row in payload.get("data") or []
        if isinstance(row, dict) and row.get("islandCode") and row.get("rank") is not None
    ]
    ranked.sort()
    return {
        "snapshot": meta.get("snapshot"),
        "total": meta.get("total"),
        "codes": [code for _, code in ranked[:RANKS_KEPT]],
    }


def fetch_island(fetch: Fetch, code: str) -> dict[str, Any]:
    payload = fetch(f"{API}/islands/{quote(code)}")
    row = payload.get("data", payload) if isinstance(payload, dict) else {}
    return {
        "title": row.get("title"),
        "creatorCode": row.get("creatorCode"),
        "createdIn": row.get("createdIn"),
        "category": row.get("category"),
        "tags": [str(tag) for tag in row.get("tags") or []],
    }


def parse_metrics(payload: Any) -> dict[str, dict[str, Any]]:
    """Turn the API's per-metric arrays into one record per bucket timestamp.

    The API returns {"plays": [{"value": 1, "timestamp": "..."}], ...,
    "retention": [{"d1": 0.5, "d7": 0.4, "timestamp": "..."}]}. Empty values stay None.
    """
    days: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return days
    for name in VALUE_METRICS:
        for point in payload.get(name) or []:
            if isinstance(point, dict) and point.get("timestamp"):
                days.setdefault(str(point["timestamp"]), {})[name] = point.get("value")
    for point in payload.get("retention") or []:
        if isinstance(point, dict) and point.get("timestamp"):
            bucket = days.setdefault(str(point["timestamp"]), {})
            for field in RETENTION_FIELDS:
                bucket[field] = point.get(field)
    return days


def metrics_url(code: str, now: datetime, *, window: bool) -> str:
    """The daily-metrics address for one island, with or without an explicit date window."""
    base = f"{API}/islands/{quote(code)}/metrics/day"
    if not window:
        return base
    stamp = "%Y-%m-%dT%H:%M:%S.000Z"
    start = (now - timedelta(days=HISTORY_DAYS)).strftime(stamp)
    return f"{base}?{urlencode({'from': start, 'to': now.strftime(stamp)})}"


def merge_days(
    stored: dict[str, dict[str, Any]], fresh: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Add fresh buckets to stored ones. A reported value is never replaced by an empty one."""
    merged = {stamp: dict(values) for stamp, values in stored.items()}
    for stamp, values in fresh.items():
        bucket = merged.setdefault(stamp, {})
        for name, value in values.items():
            if value is not None or name not in bucket:
                bucket[name] = value
    return dict(sorted(merged.items()))


def reported_days(days: dict[str, dict[str, Any]]) -> list[str]:
    """Bucket timestamps that carry at least one reported value, oldest first."""
    return sorted(s for s, values in days.items() if any(v is not None for v in values.values()))


def latest_reported(days: dict[str, dict[str, Any]]) -> tuple[str | None, dict[str, Any]]:
    """The most recent bucket that has at least one reported value."""
    reported = reported_days(days)
    return (reported[-1], days[reported[-1]]) if reported else (None, {})


def choose_tracked(
    rankings: dict[str, dict[str, Any]],
    islands: dict[str, dict[str, Any]],
    today: date,
    top: int,
) -> list[str]:
    """Today's top islands per genre, then recently ranked ones, best rank first."""
    current: dict[str, int] = {}
    for genre in rankings.values():
        for position, code in enumerate(genre["codes"][:top], start=1):
            current[code] = min(position, current.get(code, position))
    chosen = sorted(current, key=lambda code: (current[code], code))
    cutoff = (today - timedelta(days=KEEP_TRACKING_DAYS)).isoformat()
    recent = [
        code
        for code, island in islands.items()
        if code not in current and (island.get("last_in_top") or "") >= cutoff
    ]
    recent.sort(key=lambda code: (islands[code].get("best_rank") or 10**6, code))
    return (chosen + recent)[:MAX_TRACKED]


def collect(
    fetch: Fetch, out: Path, *, now: datetime | None = None, top: int = DEFAULT_TOP
) -> dict[str, Any]:
    """Run one collection and write every output file. Returns the run report."""
    now = now or datetime.now(UTC)
    today = now.date()
    notes: list[str] = []

    genres = fetch_genres(fetch)
    rankings: dict[str, dict[str, Any]] = {}
    for genre in genres:
        try:
            ranked = fetch_rankings(fetch, genre["slug"])
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError) as err:
            notes.append(f"rankings for {genre['slug']} failed: {_status(err)}")
            continue
        rankings[genre["slug"]] = {"displayName": genre["displayName"], **ranked}
    if not rankings:
        raise RuntimeError("no genre rankings could be read: " + "; ".join(notes))
    _write(
        out / "rankings" / f"{today.isoformat()}.json",
        {"collected_at": now.isoformat(), "genres": rankings},
    )

    islands: dict[str, dict[str, Any]] = _read(out / "islands.json", {})
    for slug, genre in rankings.items():
        for position, code in enumerate(genre["codes"], start=1):
            island = islands.setdefault(code, {"first_seen": today.isoformat()})
            island["last_ranked"] = today.isoformat()
            seen = island.setdefault("genres", [])
            if slug not in seen:
                seen.append(slug)
            if position < (island.get("best_rank") or 10**6):
                island["best_rank"] = position
            if position <= top:
                island["last_in_top"] = today.isoformat()

    tracked = choose_tracked(rankings, islands, today, top)
    collected = failed = streak = 0
    # Ask for the full seven-day window. If the API refuses that form before it has ever
    # worked, use the plain call (its default window) for the rest of the run.
    window: bool | None = None
    for code in tracked:
        island = islands[code]
        try:
            details = fetch_island(fetch, code)
            old_tags = island.get("tags")
            if old_tags is not None and old_tags != details["tags"]:
                island.setdefault("tag_changes", []).append(
                    {"date": today.isoformat(), "from": old_tags, "to": details["tags"]}
                )
            island.update({key: value for key, value in details.items() if value is not None})
            try:
                payload = fetch(metrics_url(code, now, window=window is not False))
                window = window is not False
            except HTTPError as err:
                if window is not None:
                    raise
                # Undecided: the plain call tells a refused form apart from a bad island.
                payload = fetch(metrics_url(code, now, window=False))
                window = False
                notes.append(f"date-window request refused ({_status(err)}); using the default")
            fresh = parse_metrics(payload)
        except (HTTPError, URLError, TimeoutError, ValueError) as err:
            failed += 1
            streak += 1
            if failed <= 10:
                notes.append(f"island {code} failed: {_status(err)}")
            if streak >= FAILURE_LIMIT:
                notes.append(f"stopped after {streak} islands in a row failed")
                break
            continue
        streak = 0
        collected += 1
        path = out / "metrics" / f"{code}.json"
        stored = _read(path, {}).get("days", {})
        _write(path, {"code": code, "days": merge_days(stored, fresh)})

    _write(out / "islands.json", dict(sorted(islands.items())))
    summary = summarize(out, rankings, islands, now=now, top=top)
    _write(out / "summary.json", summary)

    report = {
        "ok": collected > 0 and streak < FAILURE_LIMIT,
        "collected_at": now.isoformat(),
        "genres": len(rankings),
        "islands_ranked": sum(len(genre["codes"]) for genre in rankings.values()),
        "islands_tracked": len(tracked),
        "islands_collected": collected,
        "islands_failed": failed,
        "metrics_request": {None: "none made", True: "seven-day window", False: "default"}[window],
        "islands_known": len(islands),
        "notes": notes,
    }
    _write(out / "last_run.json", report)
    return report


# ---------------------------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------------------------


def summarize(
    out: Path,
    rankings: dict[str, dict[str, Any]],
    islands: dict[str, dict[str, Any]],
    *,
    now: datetime,
    top: int,
) -> dict[str, Any]:
    """Join each genre's current top islands to their latest reported numbers."""
    genres: dict[str, Any] = {}
    longest = 0
    for slug, genre in rankings.items():
        rows = []
        for position, code in enumerate(genre["codes"][:top], start=1):
            island = islands.get(code, {})
            days = _read(out / "metrics" / f"{code}.json", {}).get("days", {})
            reported = reported_days(days)
            longest = max(longest, len(reported))
            stamp, numbers = latest_reported(days)
            rows.append(
                {
                    "rank": position,
                    "code": code,
                    "title": island.get("title"),
                    "creatorCode": island.get("creatorCode"),
                    "creator_tags": island.get("tags"),
                    "days_of_history": len(reported),
                    "latest_bucket": stamp,
                    "latest": numbers,
                }
            )
        genres[slug] = {
            "displayName": genre["displayName"],
            "ranking_snapshot": genre.get("snapshot"),
            "islands_in_genre": genre.get("total"),
            "top": rows,
        }
    return {
        "generated_at": now.isoformat(),
        "source": "Epic's public Fortnite Data API (api.fortnite.com/ecosystem/v1)",
        "note": (
            "Genre and tags are the creator's own choices. Empty numbers mean not reported, "
            "not zero. Bucket timestamps are stored exactly as the API gives them."
        ),
        "top_per_genre": top,
        "longest_history_days": longest,
        "genres": genres,
    }


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------


def _read(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("run",))
    parser.add_argument("--out", type=Path, required=True, help="data directory")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP, help="islands per genre")
    parser.add_argument("--delay", type=float, default=0.4, help="seconds between requests")
    args = parser.parse_args(argv)

    try:
        report = collect(polite(http_json, args.delay), args.out, top=args.top)
    except Exception as err:  # the failure is written where the next session can read it
        _write(
            args.out / "last_run.json",
            {
                "ok": False,
                "collected_at": datetime.now(UTC).isoformat(),
                "error": f"{type(err).__name__}: {err}",
                "trace": traceback.format_exc()[-2000:],
            },
        )
        raise
    print(
        f"ranked {report['islands_ranked']} islands in {report['genres']} genres; "
        f"numbers for {report['islands_collected']} of {report['islands_tracked']} "
        f"({report['islands_failed']} failed); notes: {report['notes'] or 'none'}"
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
