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
from gametagger.genome.sources import normal_title, steam_app_entry

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
        if re.search(r'id="rankings-table".*?<tbody>\s*</tbody>', page, re.S):
            raise SourceError(
                "AppBrain's page loaded, but its ranking table is empty: AppBrain is not "
                "publishing this chart right now (it is not a block or a layout change)"
            )
        raise SourceError("AppBrain returned no ranked games")
    return date, sorted(rows, key=lambda r: r["rank"])


def steam_basics(appid: int, *, fetch: Callable[[str], Any] = fetch_json) -> dict[str, Any]:
    """Name, store type and developers for one Steam app (no screenshots, cheap)."""
    url = STEAM_DETAILS_URL + urlencode({"appids": appid, "l": "english", "cc": "us"})
    entry = steam_app_entry(fetch(url), str(appid))
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


# --- Mobile-first cohort: a deeper top-grossing list plus rising games -------------------------

APPBRAIN_RANKING = "https://www.appbrain.com/stats/google-play-rankings/{kind}/game/us"
# AppBrain's pages may hold fewer rows than asked for. These are tried, in order, for more rows;
# a page that ignores the parameter returns rows already seen, which are dropped.
APPBRAIN_MORE_PAGES = ("?page=2", "?o=100")
RISING_SOURCES = (
    ("top_new_free", "AppBrain Google Play ranking: top new free games, United States"),
    ("top_free", "AppBrain Google Play ranking: top free games, United States"),
)


def appbrain_ranking(
    kind: str, want: int, *, fetch_page: Callable[[str], str] = fetch_text
) -> tuple[str | None, list[dict[str, Any]], str]:
    """Up to ``want`` rows of one AppBrain games ranking (US), in rank order."""
    url = APPBRAIN_RANKING.format(kind=kind)
    date, rows = parse_appbrain(fetch_page(url))
    seen = {r["package"] for r in rows}
    for suffix in APPBRAIN_MORE_PAGES:
        if len(rows) >= want:
            break
        try:
            _, more = parse_appbrain(fetch_page(url + suffix))
        except SourceError:
            continue
        fresh = [r for r in more if r["package"] not in seen and r["rank"] > rows[-1]["rank"]]
        rows += fresh
        seen.update(r["package"] for r in fresh)
    return date, rows[:want], url


def build_mobile_cohort(
    *,
    grossing_count: int = 100,
    rising_count: int = 30,
    previous: dict[str, Any] | None = None,
    rising_if_no_grossing: int = 100,
    fetch_page: Callable[[str], str] = fetch_text,
) -> dict[str, Any]:
    """Today's Google Play top-grossing games plus rising games from a new-games chart.

    Every game has ``list`` "mobile" (so the runner treats it as a Google Play game) and a
    ``segment``: "grossing" or "rising". Rising games are the highest-ranked games on AppBrain's
    top-new-free chart (top-free if that chart cannot be read) that are not already in the
    top-grossing list. ``previous`` (an earlier cohort) adds each grossing game's earlier rank,
    for chart movers.

    If today's top-grossing chart cannot be read and ``previous`` is given, its top-grossing
    games are used instead (marked ``fallback``, with no chart movers), and up to
    ``rising_if_no_grossing`` games from the new-games or top-free chart are added, so the
    run still brings in today's games.
    """
    before, previous_rows = {}, []
    if previous:
        for g in previous.get("games") or []:
            if g.get("list") == "mobile" and (g.get("ids") or {}).get("google_play"):
                before[g["ids"]["google_play"]] = g["rank"]
                previous_rows.append(
                    {
                        "rank": g["rank"],
                        "package": g["ids"]["google_play"],
                        "title": g.get("title") or g["ids"]["google_play"],
                        "developer": (g.get("developers") or [None])[0],
                    }
                )
    fallback = None
    try:
        g_date, g_rows, g_url = appbrain_ranking(
            "top_grossing", grossing_count, fetch_page=fetch_page
        )
    except SourceError as exc:
        if not previous_rows:
            raise
        prev_date = ((previous.get("charts") or {}).get("mobile") or {}).get("chart_date")
        fallback = (
            f"Today's top-grossing chart could not be read ({exc}). The top-grossing games from "
            f"{prev_date} are used instead."
        )
        g_date, g_url = prev_date, APPBRAIN_URL
        g_rows = sorted(previous_rows, key=lambda r: r["rank"])[:grossing_count]
        before = {}
        rising_count = max(rising_count, rising_if_no_grossing)
    games = [
        {
            "game_id": f"gp-{row['package']}",
            "list": "mobile",
            "segment": "grossing",
            "rank": row["rank"],
            "title": row["title"],
            "developers": [row["developer"]] if row["developer"] else [],
            "ids": {"google_play": row["package"]},
            "chart": {"previous_rank": before.get(row["package"])},
        }
        for row in g_rows
    ]
    charts: dict[str, Any] = {
        "mobile": {
            "source": "AppBrain Google Play ranking: top grossing games, United States",
            "url": g_url,
            "chart_date": g_date,
            "ranked_by": "grossing (AppBrain's Google Play top-grossing list)",
            "region": "US",
            "platform": "Android (Google Play)",
            "rows": len(g_rows),
        }
    }
    if fallback:
        charts["mobile"]["fallback"] = fallback
    elif previous:
        charts["mobile"]["previous_chart_date"] = (
            (previous.get("charts") or {}).get("mobile") or {}
        ).get("chart_date")
    taken = {g["ids"]["google_play"] for g in games}
    rising_errors = []
    for kind, label in RISING_SOURCES:
        if rising_count <= 0:
            break
        try:
            r_date, r_rows, r_url = appbrain_ranking(
                kind, rising_count + len(taken), fetch_page=fetch_page
            )
        except SourceError as exc:
            rising_errors.append(f"{kind}: {exc}")
            continue
        picked = [r for r in r_rows if r["package"] not in taken][:rising_count]
        games += [
            {
                "game_id": f"gp-{row['package']}",
                "list": "mobile",
                "segment": "rising",
                "rank": row["rank"],
                "title": row["title"],
                "developers": [row["developer"]] if row["developer"] else [],
                "ids": {"google_play": row["package"]},
                "chart": {"chart": kind},
            }
            for row in picked
        ]
        charts["rising"] = {
            "source": label,
            "url": r_url,
            "chart_date": r_date,
            "ranked_by": f"rank on AppBrain's {kind.replace('_', ' ')} games chart, excluding "
            "games already in the top-grossing list",
            "region": "US",
            "platform": "Android (Google Play)",
            "rows": len(picked),
        }
        break
    return {
        "schema_version": COHORT_SCHEMA,
        "created_at": _now(),
        "charts": charts,
        "rules": [
            "Mobile only: Google Play top-grossing games (segment 'grossing') and rising games "
            "from a new-games chart (segment 'rising').",
            "A rising game already in the top-grossing list is kept once, as grossing.",
            "Store IDs are exact; titles are for display only.",
        ],
        "games": games,
        "skipped": [{"list": "rising", "reason": e} for e in rising_errors]
        + ([{"list": "mobile", "reason": fallback}] if fallback else []),
    }
