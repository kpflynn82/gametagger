"""Public chart readers and the frozen, dated benchmark cohort.

* Steam: the official most-played chart (``ISteamChartsService/GetMostPlayedGames``), in Steam's
  own rank order. Software is skipped and listed with the reason: entries whose store ``type``
  is not ``game``, and entries Steam files under its software genres (Wallpaper Engine is typed
  ``game`` but listed under Animation & Modeling, Photo Editing and Utilities).
* Mobile: AppBrain's Google Play top-grossing games chart for the United States.

Games are identified by exact store IDs (Steam app ID, Google Play package). A game listed
twice (on both charts, or as two editions such as "Legacy" and "Enhanced") is kept once, at its
higher rank, and the next chart entry takes the freed place.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from gametagger.genome.net import SourceError, fetch_json, fetch_text
from gametagger.genome.sources import normal_title

STEAM_CHART_URL = "https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails?"
APPBRAIN_URL = "https://www.appbrain.com/stats/google-play-rankings/top_grossing/game/us"
COHORT_SCHEMA = "jev-vs-legacy-cohort-v1"
# Steam's software genres. Education (54) is left out: it also labels educational games.
SOFTWARE_GENRES = {
    "51": "Animation & Modeling",
    "52": "Audio Production",
    "53": "Design & Illustration",
    "55": "Photo Editing",
    "56": "Software Training",
    "57": "Utilities",
    "58": "Video Production",
    "59": "Web Publishing",
    "60": "Game Development",
}


EDITION = re.compile(
    r"\s*[-:(]?\s*\b(legacy|enhanced|remastered|definitive edition|game of the year edition|"
    r"goty edition|complete edition)\b\)?\s*$",
    re.I,
)


def base_title(title: str) -> str:
    """Normalized title without a trailing edition word, to spot one game listed twice."""
    return normal_title(EDITION.sub("", title))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_steam_chart(payload: Any) -> tuple[str | None, list[dict[str, int]]]:
    response = (payload or {}).get("response") or {}
    rollup = response.get("rollup_date")
    date = (
        datetime.fromtimestamp(int(rollup), timezone.utc).date().isoformat()
        if str(rollup).isdigit()
        else None
    )
    ranks = [
        {
            "rank": int(r["rank"]),
            "appid": int(r["appid"]),
            "peak_in_game": int(r.get("peak_in_game") or 0),
            "last_week_rank": int(r.get("last_week_rank") or 0),
        }
        for r in response.get("ranks") or []
        if isinstance(r, dict) and str(r.get("rank")).isdigit() and str(r.get("appid")).isdigit()
    ]
    if not ranks:
        raise SourceError("The Steam chart returned no ranked apps")
    return date, sorted(ranks, key=lambda r: r["rank"])


ROW = re.compile(
    r'<td class="ranking-rank">\s*(\d+)\s*</td>.*?'
    r'<td class="ranking-app-cell">\s*<a href="/app/[^/"]+/([A-Za-z0-9_.]+)">([^<]+)</a>'
    r'(?:.*?class="ranking-app-cell-creator">\s*by\s*<a[^>]*>([^<]+)</a>)?',
    re.S,
)


def parse_appbrain(page: str) -> tuple[str | None, list[dict[str, Any]]]:
    """Rank, title, package and developer from AppBrain's ranking table, in rank order."""
    updated = re.search(r"Last updated:\s*<time>([^<]+)</time>", page)
    date = None
    if updated:
        try:
            date = datetime.strptime(updated.group(1).strip(), "%B %d, %Y").date().isoformat()
        except ValueError:
            date = updated.group(1).strip()
    rows, seen = [], set()
    for rank, package, title, developer in ROW.findall(page):
        if package in seen:
            continue
        seen.add(package)
        rows.append(
            {
                "rank": int(rank),
                "package": package,
                "title": html.unescape(title).strip(),
                "developer": html.unescape(developer).strip() if developer else None,
            }
        )
    if not rows:
        raise SourceError("AppBrain returned no ranked games")
    return date, sorted(rows, key=lambda r: r["rank"])


def steam_basics(appid: int, *, fetch: Callable[[str], Any] = fetch_json) -> dict[str, Any]:
    """Name, store type and developers for one Steam app (no screenshots, cheap)."""
    url = STEAM_DETAILS_URL + urlencode({"appids": appid, "l": "english", "cc": "us"})
    entry = (fetch(url) or {}).get(str(appid)) or {}
    data = entry.get("data") if entry.get("success") else None
    if not isinstance(data, dict):
        return {"available": False}
    return {
        "available": True,
        "name": str(data.get("name") or ""),
        "type": str(data.get("type") or ""),
        "developers": [str(d) for d in data.get("developers") or []],
        "is_free": bool(data.get("is_free")),
        "genre_ids": [str(g.get("id")) for g in data.get("genres") or [] if isinstance(g, dict)],
    }


def build_cohort(
    *,
    steam_count: int = 50,
    mobile_count: int = 50,
    fetch: Callable[[str], Any] = fetch_json,
    fetch_page: Callable[[str], str] = fetch_text,
) -> dict[str, Any]:
    steam_date, steam_ranks = parse_steam_chart(fetch(STEAM_CHART_URL))
    games, skipped, seen = [], [], {}
    for entry in steam_ranks:
        if len([g for g in games if g["list"] == "steam"]) >= steam_count:
            break
        basics = steam_basics(entry["appid"], fetch=fetch)
        if not basics["available"]:
            skipped.append({"list": "steam", **entry, "reason": "no public US store listing"})
            continue
        software = [SOFTWARE_GENRES[g] for g in basics["genre_ids"] if g in SOFTWARE_GENRES]
        if basics["type"] != "game" or software:
            reason = (
                f"store type is '{basics['type']}', not a game"
                if basics["type"] != "game"
                else "Steam lists it under software genres: " + ", ".join(software)
            )
            skipped.append({"list": "steam", **entry, "title": basics["name"], "reason": reason})
            continue
        if (twin := seen.get(base_title(basics["name"]))) is not None:
            skipped.append(
                {
                    "list": "steam",
                    **entry,
                    "title": basics["name"],
                    "reason": f"another edition of {twin} (kept at its higher rank)",
                }
            )
            continue
        seen[base_title(basics["name"])] = f"steam-{entry['appid']}"
        games.append(
            {
                "game_id": f"steam-{entry['appid']}",
                "list": "steam",
                "rank": entry["rank"],
                "title": basics["name"],
                "developers": basics["developers"],
                "ids": {"steam_app": str(entry["appid"])},
                "chart": {k: entry[k] for k in ("peak_in_game", "last_week_rank")},
            }
        )
    mobile_date, mobile_rows = parse_appbrain(fetch_page(APPBRAIN_URL))
    steam_titles = {base_title(g["title"]): g["game_id"] for g in games}
    mobile = []
    for row in mobile_rows:
        if len(mobile) >= mobile_count:
            break
        duplicate = steam_titles.get(base_title(row["title"]))
        if duplicate:
            skipped.append(
                {"list": "mobile", **row, "reason": f"same game as {duplicate} on the Steam list"}
            )
            continue
        mobile.append(
            {
                "game_id": f"gp-{row['package']}",
                "list": "mobile",
                "rank": row["rank"],
                "title": row["title"],
                "developers": [row["developer"]] if row["developer"] else [],
                "ids": {"google_play": row["package"]},
            }
        )
    return {
        "schema_version": COHORT_SCHEMA,
        "created_at": _now(),
        "charts": {
            "steam": {
                "source": "Steam most-played chart (ISteamChartsService/GetMostPlayedGames)",
                "url": STEAM_CHART_URL,
                "chart_date": steam_date,
                "ranked_by": "Steam's own rank order (daily peak concurrent players)",
                "region": "global",
                "platform": "PC (Steam)",
            },
            "mobile": {
                "source": "AppBrain Google Play ranking: top grossing games, United States",
                "url": APPBRAIN_URL,
                "chart_date": mobile_date,
                "ranked_by": "grossing (AppBrain's Google Play top-grossing list)",
                "region": "US",
                "platform": "Android (Google Play)",
            },
        },
        "rules": [
            "Steam entries whose store type is not 'game', or that Steam files under software "
            "genres, are skipped.",
            "A game on both charts is kept once, on the Steam list.",
            "Two editions of one game (e.g. Legacy and Enhanced) are kept once, at the higher "
            "rank.",
            "Store IDs are exact; titles are for display only.",
        ],
        "games": games + mobile,
        "skipped": skipped,
    }
