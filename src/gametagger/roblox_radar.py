"""Roblox Radar: collect public Roblox chart and game data, and summarize what is rising.

Standard library only, so the scheduled GitHub workflow runs it without installing the package:

    PYTHONPATH=src python -m gametagger.roblox_radar run --out <data-dir>

Every source is a public, unauthenticated Roblox web API (the same calls roblox.com makes):

- explore-api get-sorts / get-sort-content: the Charts page (Top Trending, Up-and-Coming, ...)
- games.roblox.com v1/games and v1/games/votes: players online, visits, favorites, likes
- game-passes (apis.roblox.com, with the older games.roblox.com list as a fallback): pass prices
- badges.roblox.com v1/universes/{id}/badges: award counts, a progression-funnel signal
- thumbnails.roblox.com v1/games/icons: icon image URLs

What these numbers are and are not: players online, visits and badge counts are observations.
Revenue is never published per game. The revenue band in the summary is an estimate scaled from
Roblox's platform-wide averages (see REVENUE_BASIS) and is labeled as an estimate everywhere.

Outputs in the data directory:
- latest.json            the full most recent snapshot (charts, game details, passes, badges)
- history/YYYY-MM-DD.json one file per UTC day: every players-online sample taken that day,
                          plus that day's last visits / favorites / new-player counts
- radar.json             the summary the dashboard reads: growth, flags, monetization, estimates
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "gametagger-roblox-radar/1.0 (+https://github.com/kpflynn82/gametagger)"
EXPLORE = "https://apis.roblox.com/explore-api/v1"
GAMES = "https://games.roblox.com/v1"
BADGES = "https://badges.roblox.com/v1"
THUMBS = "https://thumbnails.roblox.com/v1"
PASSES = "https://apis.roblox.com/game-passes/v1"

# Charts that the default get-sorts call may not return. Each is tried on its own; a missing one
# is recorded in the snapshot, never fatal.
EXTRA_SORT_IDS = (
    "top-earning",
    "top-revisited",
    "top-paid-access",
    "fun-with-friends",
    "most-engaging",
    "top-rated",
)
SORT_DEPTH = {"top-playing-now": 300}
DEFAULT_SORT_DEPTH = 120
DETAIL_LIMIT = 220  # games that also get passes + badges (busiest first, all risers included)
BADGE_LIMIT = 100

# Platform averages used only for the labeled revenue estimate. Update these from Roblox's latest
# quarterly results (shareholder letter): bookings, developer exchange fees, engagement hours.
REVENUE_BASIS = {
    "quarter": "Q2 2026",
    "bookings_usd": None,  # set by the dashboard build; None disables the estimate
    "devex_usd": None,
    "engagement_hours": None,
    "source": "",
}
ESTIMATE_LOW, ESTIMATE_HIGH = 0.5, 2.0  # genre spread around the platform average

Fetch = Callable[[str], Any]


# ---------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------


def http_json(url: str, *, retries: int = 4, pause: float = 1.5) -> Any:
    """GET a JSON document, backing off on rate limits and transient errors."""
    last: Exception | None = None
    for attempt in range(retries):
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as err:
            last = err
            if err.code not in (429, 500, 502, 503, 504):
                raise
        except (URLError, TimeoutError) as err:
            last = err
        time.sleep(pause * (2**attempt))
    assert last is not None
    raise last


def polite(fetch: Fetch, delay: float) -> Fetch:
    """Wrap a fetcher so consecutive calls are spaced out."""

    def wrapped(url: str) -> Any:
        if delay:
            time.sleep(delay)
        return fetch(url)

    return wrapped


def _token(payload: Any) -> str | None:
    """Find a next-page token whatever Roblox calls it this month."""
    if not isinstance(payload, dict):
        return None
    for key, value in payload.items():
        lowered = key.lower()
        if ("pagetoken" in lowered or "pagecursor" in lowered) and isinstance(value, str):
            if value and "previous" not in lowered:
                return value
    return None


def _chunks(items: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


# ---------------------------------------------------------------------------------------------
# Collect
# ---------------------------------------------------------------------------------------------


def _game_entry(raw: dict[str, Any]) -> dict[str, Any] | None:
    universe = raw.get("universeId")
    if not isinstance(universe, int):
        return None
    return {
        "universeId": universe,
        "rootPlaceId": raw.get("rootPlaceId"),
        "name": raw.get("name") or "",
        "playerCount": raw.get("playerCount"),
        "upVotes": raw.get("totalUpVotes"),
        "downVotes": raw.get("totalDownVotes"),
        "sponsored": bool(raw.get("isSponsored")),
        "maturity": raw.get("contentMaturity") or "",
        "minimumAge": raw.get("minimumAge"),
        "genre": raw.get("genreL1") or "",
    }


def _sort_page_url(session: str, sort_id: str, token: str | None) -> str:
    query = {"sessionId": session, "sortId": sort_id, "device": "computer", "country": "all"}
    if token:
        query["pageToken"] = token
    return f"{EXPLORE}/get-sort-content?{urlencode(query)}"


def fetch_charts(fetch: Fetch, session: str) -> tuple[dict[str, Any], list[str]]:
    """Return {sortId: {name, games:[entries in chart order]}} and a list of notes."""
    notes: list[str] = []
    charts: dict[str, Any] = {}
    sorts_token: str | None = None
    for _ in range(6):
        query = {"sessionId": session, "device": "computer", "country": "all"}
        if sorts_token:
            query["sortsPageToken"] = sorts_token
        payload = fetch(f"{EXPLORE}/get-sorts?{urlencode(query)}")
        for sort in payload.get("sorts", []) if isinstance(payload, dict) else []:
            games = sort.get("games")
            sort_id = sort.get("sortId")
            if not sort_id or not isinstance(games, list):
                continue
            entries = [e for e in (_game_entry(g) for g in games) if e]
            charts[sort_id] = {
                "name": sort.get("sortDisplayName") or sort_id,
                "games": entries,
                "token": _token(sort),
            }
        sorts_token = _token(payload)
        if not sorts_token:
            break

    for sort_id in EXTRA_SORT_IDS:
        if sort_id in charts:
            continue
        try:
            payload = fetch(_sort_page_url(session, sort_id, None))
        except Exception as err:  # noqa: BLE001 - a missing chart is information, not failure
            notes.append(f"chart {sort_id} unavailable: {type(err).__name__}")
            continue
        games = payload.get("games") if isinstance(payload, dict) else None
        if not games:
            notes.append(f"chart {sort_id} returned no games")
            continue
        charts[sort_id] = {
            "name": sort_id.replace("-", " ").title(),
            "games": [e for e in (_game_entry(g) for g in games) if e],
            "token": _token(payload),
        }

    # Page deeper into each chart.
    for sort_id, chart in charts.items():
        depth = SORT_DEPTH.get(sort_id, DEFAULT_SORT_DEPTH)
        token = chart.pop("token", None)
        seen = {g["universeId"] for g in chart["games"]}
        pages = 0
        while token and len(chart["games"]) < depth and pages < 10:
            pages += 1
            try:
                payload = fetch(_sort_page_url(session, sort_id, token))
            except Exception as err:  # noqa: BLE001
                notes.append(f"chart {sort_id} page {pages} failed: {type(err).__name__}")
                break
            for raw in payload.get("games", []) if isinstance(payload, dict) else []:
                entry = _game_entry(raw)
                if entry and entry["universeId"] not in seen:
                    seen.add(entry["universeId"])
                    chart["games"].append(entry)
            token = _token(payload)
        del chart["games"][depth:]
    return charts, notes


def fetch_details(fetch: Fetch, universe_ids: list[int]) -> dict[int, dict[str, Any]]:
    details: dict[int, dict[str, Any]] = {}
    for batch in _chunks(universe_ids, 50):
        ids = ",".join(str(i) for i in batch)
        payload = fetch(f"{GAMES}/games?universeIds={ids}")
        for game in payload.get("data", []):
            creator = game.get("creator") or {}
            details[game["id"]] = {
                "name": game.get("name") or "",
                "rootPlaceId": game.get("rootPlaceId"),
                "description": (game.get("description") or "")[:1500],
                "creator": creator.get("name") or "",
                "creatorType": creator.get("type") or "",
                "creatorVerified": bool(creator.get("hasVerifiedBadge")),
                "playing": game.get("playing"),
                "visits": game.get("visits"),
                "favorites": game.get("favoritedCount"),
                "maxPlayers": game.get("maxPlayers"),
                "created": game.get("created"),
                "updated": game.get("updated"),
                "price": game.get("price"),
                "privateServers": game.get("createVipServersAllowed"),
                "genre": game.get("genre_l1") or game.get("genre") or "",
                "subgenre": game.get("genre_l2") or "",
            }
        try:
            votes = fetch(f"{GAMES}/games/votes?universeIds={ids}")
        except Exception:  # noqa: BLE001 - likes are optional; chart entries carry them too
            votes = {}
        for row in votes.get("data", []):
            if row.get("id") in details:
                details[row["id"]]["upVotes"] = row.get("upVotes")
                details[row["id"]]["downVotes"] = row.get("downVotes")
        try:
            icons = fetch(
                f"{THUMBS}/games/icons?universeIds={ids}&returnPolicy=PlaceHolder"
                "&size=150x150&format=Png&isCircular=false"
            )
        except Exception:  # noqa: BLE001 - icons are cosmetic
            icons = {}
        for row in icons.get("data", []):
            if row.get("targetId") in details and row.get("state") == "Completed":
                details[row["targetId"]]["icon"] = row.get("imageUrl")
    return details


def fetch_passes(fetch: Fetch, universe_id: int) -> list[dict[str, Any]] | None:
    """Game passes with prices. None means both endpoints failed (unknown, not 'no passes')."""
    urls = (
        f"{PASSES}/universes/{universe_id}/game-passes?passView=Full&pageSize=100",
        f"{GAMES}/games/{universe_id}/game-passes?limit=100&sortOrder=Asc",
    )
    for url in urls:
        try:
            payload = fetch(url)
        except Exception:  # noqa: BLE001
            continue
        rows = None
        if isinstance(payload, dict):
            rows = payload.get("gamePasses", payload.get("data"))
        if isinstance(rows, list):
            passes = []
            for row in rows:
                price = row.get("price")
                if price is None and isinstance(row.get("priceInformation"), dict):
                    price = row["priceInformation"].get("defaultPriceInRobux")
                passes.append(
                    {
                        "name": row.get("displayName") or row.get("name") or "",
                        "price": price,
                        "forSale": row.get("isForSale", price is not None),
                    }
                )
            return passes
    return None


def fetch_badges(fetch: Fetch, universe_id: int) -> list[dict[str, Any]] | None:
    try:
        payload = fetch(
            f"{BADGES}/universes/{universe_id}/badges?limit={BADGE_LIMIT}&sortOrder=Asc"
        )
    except Exception:  # noqa: BLE001
        return None
    badges = []
    for row in payload.get("data", []) if isinstance(payload, dict) else []:
        stats = row.get("statistics") or {}
        badges.append(
            {
                "name": row.get("displayName") or row.get("name") or "",
                "description": (row.get("displayDescription") or row.get("description") or "")[
                    :200
                ],
                "enabled": row.get("enabled", True),
                "created": row.get("created"),
                "awarded": stats.get("awardedCount"),
                "pastDay": stats.get("pastDayAwardedCount"),
                "winRate": stats.get("winRatePercentage"),
            }
        )
    return badges


def collect(fetch: Fetch, *, now: datetime | None = None) -> dict[str, Any]:
    """Take one snapshot of the charts and the games on them."""
    now = now or datetime.now(UTC)
    session = str(uuid.uuid4())
    charts, notes = fetch_charts(fetch, session)

    ordered: list[int] = []
    for chart in charts.values():
        for entry in chart["games"]:
            if not entry["sponsored"] and entry["universeId"] not in ordered:
                ordered.append(entry["universeId"])
    details = fetch_details(fetch, ordered)

    def busy(uid: int) -> int:
        return (details.get(uid) or {}).get("playing") or 0

    risers = set()
    for sort_id in ("up-and-coming", "top-trending"):
        risers.update(e["universeId"] for e in charts.get(sort_id, {}).get("games", [])[:60])
    deep = sorted(ordered, key=busy, reverse=True)[:DETAIL_LIMIT]
    deep += [uid for uid in ordered if uid in risers and uid not in deep]
    for uid in deep:
        if uid in details:
            details[uid]["passes"] = fetch_passes(fetch, uid)
            details[uid]["badges"] = fetch_badges(fetch, uid)

    return {
        "taken_at": now.isoformat(timespec="seconds"),
        "charts": {
            sort_id: {
                "name": chart["name"],
                "order": [e["universeId"] for e in chart["games"] if not e["sponsored"]],
                "sponsored": [e["universeId"] for e in chart["games"] if e["sponsored"]],
                "entries": {str(e["universeId"]): e for e in chart["games"]},
            }
            for sort_id, chart in charts.items()
        },
        "games": {str(uid): info for uid, info in details.items()},
        "notes": notes,
    }


# ---------------------------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------------------------


def new_players_per_day(badges: list[dict[str, Any]] | None) -> int | None:
    """Best proxy for daily new players: the largest past-day award count among early badges.

    Most games award a "welcome"/"joined" badge on first visit; its past-day count is roughly the
    number of new players that day. Games without such a badge understate this, so treat it as a
    floor, never an exact count.
    """
    if not badges:
        return None
    counts = [
        b["pastDay"] for b in badges[:15] if b.get("enabled") and isinstance(b.get("pastDay"), int)
    ]
    return max(counts) if counts else None


def record_history(snapshot: dict[str, Any], history_dir: Path) -> Path:
    """Append this snapshot's players-online sample to the day's history file."""
    taken = datetime.fromisoformat(snapshot["taken_at"])
    path = history_dir / f"{taken.date().isoformat()}.json"
    day: dict[str, Any] = {"date": taken.date().isoformat(), "samples": [], "games": {}}
    if path.exists():
        day = json.loads(path.read_text())
    ccu = {
        uid: info.get("playing")
        for uid, info in snapshot["games"].items()
        if isinstance(info.get("playing"), int)
    }
    day["samples"].append({"at": snapshot["taken_at"], "ccu": ccu})
    for uid, info in snapshot["games"].items():
        row = day["games"].setdefault(uid, {})
        row["name"] = info.get("name")
        for key in ("visits", "favorites", "upVotes", "downVotes"):
            if info.get(key) is not None:
                row[key] = info[key]
        npd = new_players_per_day(info.get("badges"))
        if npd is not None:
            row["newPlayers"] = npd
    ranks: dict[str, dict[str, int]] = {}
    for sort_id, chart in snapshot["charts"].items():
        ranks[sort_id] = {str(uid): i + 1 for i, uid in enumerate(chart["order"])}
    day["ranks"] = ranks
    history_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(day, separators=(",", ":"), sort_keys=True))
    return path


def load_history(history_dir: Path) -> dict[date, dict[str, Any]]:
    days: dict[date, dict[str, Any]] = {}
    if not history_dir.exists():
        return days
    for path in sorted(history_dir.glob("*.json")):
        try:
            days[date.fromisoformat(path.stem)] = json.loads(path.read_text())
        except (ValueError, json.JSONDecodeError):
            continue
    return days


def daily_average(day: dict[str, Any] | None, uid: str) -> float | None:
    if not day:
        return None
    values = [s["ccu"][uid] for s in day.get("samples", []) if uid in s.get("ccu", {})]
    return statistics.fmean(values) if values else None


# ---------------------------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------------------------


def _pct(now: float | None, then: float | None) -> float | None:
    if now is None or then is None or then <= 0:
        return None
    return round((now - then) / then * 100, 1)


def _days_since(stamp: str | None, today: datetime) -> int | None:
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0, (today - moment).days)


def pass_summary(passes: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if passes is None:
        return None
    prices = sorted(
        p["price"] for p in passes if isinstance(p.get("price"), int) and p["price"] > 0
    )
    return {
        "count": len(passes),
        "forSale": len(prices),
        "min": prices[0] if prices else None,
        "median": statistics.median(prices) if prices else None,
        "max": prices[-1] if prices else None,
        "top": [
            {"name": p["name"], "price": p["price"]}
            for p in sorted(
                (p for p in passes if isinstance(p.get("price"), int)),
                key=lambda p: p["price"],
                reverse=True,
            )[:8]
        ],
    }


def badge_funnel(badges: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Badges ordered by how many players earned them: a rough progression funnel."""
    if not badges:
        return None
    rows = [b for b in badges if isinstance(b.get("awarded"), int) and b["awarded"] > 0]
    rows.sort(key=lambda b: b["awarded"], reverse=True)
    if not rows:
        return None
    top = rows[0]["awarded"]
    return [
        {
            "name": b["name"],
            "awarded": b["awarded"],
            "share": round(b["awarded"] / top * 100, 2),
            "pastDay": b.get("pastDay"),
        }
        for b in rows[:12]
    ]


def revenue_estimate(avg_ccu: float | None, basis: dict[str, Any]) -> dict[str, Any] | None:
    """Platform-average revenue band for a game with this average players-online count."""
    hours = basis.get("engagement_hours")
    if not avg_ccu or not hours or not basis.get("bookings_usd"):
        return None
    per_hour_spend = basis["bookings_usd"] / hours
    per_hour_creator = (basis.get("devex_usd") or 0) / hours
    daily_hours = avg_ccu * 24
    return {
        "dailyHours": round(daily_hours),
        "spendPerDay": [
            round(daily_hours * per_hour_spend * ESTIMATE_LOW),
            round(daily_hours * per_hour_spend * ESTIMATE_HIGH),
        ],
        "creatorCashPerDay": [
            round(daily_hours * per_hour_creator * ESTIMATE_LOW),
            round(daily_hours * per_hour_creator * ESTIMATE_HIGH),
        ],
        "basis": basis.get("quarter"),
    }


def summarize(
    snapshot: dict[str, Any],
    history: dict[date, dict[str, Any]],
    *,
    basis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    basis = basis or REVENUE_BASIS
    taken = datetime.fromisoformat(snapshot["taken_at"])
    today = taken.date()
    charts = snapshot["charts"]
    rank_of: dict[str, dict[str, int]] = {
        sort_id: {str(uid): i + 1 for i, uid in enumerate(chart["order"])}
        for sort_id, chart in charts.items()
    }

    games = []
    for uid, info in snapshot["games"].items():
        now_ccu = info.get("playing")
        avg_today = daily_average(history.get(today), uid) or now_ccu
        avg_1d = daily_average(history.get(today - timedelta(days=1)), uid)
        avg_7d = daily_average(history.get(today - timedelta(days=7)), uid)
        avg_28d = daily_average(history.get(today - timedelta(days=28)), uid)
        peak_seen = max(
            [
                v
                for d in history.values()
                for s in d.get("samples", [])
                for k, v in s["ccu"].items()
                if k == uid
            ]
            + ([now_ccu] if isinstance(now_ccu, int) else []),
            default=None,
        )
        age = _days_since(info.get("created"), taken)
        up, down = info.get("upVotes"), info.get("downVotes")
        like = round(up / (up + down) * 100, 1) if up and down is not None and (up + down) else None
        growth_7d = _pct(avg_today, avg_7d)
        chart_ranks = {s: r[uid] for s, r in rank_of.items() if uid in r}

        flags = []
        if age is not None and age <= 60 and (now_ccu or 0) >= 50_000:
            flags.append("breakout")
        if age is not None and age <= 120 and (now_ccu or 0) >= 10_000:
            flags.append("new-and-hot")
        if growth_7d is not None and growth_7d >= 30 and (now_ccu or 0) >= 5_000:
            flags.append("rising")
        if chart_ranks.get("up-and-coming", 999) <= 25:
            flags.append("up-and-coming")
        if growth_7d is not None and growth_7d <= -30:
            flags.append("falling")
        updated_days = _days_since(info.get("updated"), taken)
        if updated_days is not None and updated_days <= 7:
            flags.append("updated-this-week")

        games.append(
            {
                "universeId": int(uid),
                "placeId": info.get("rootPlaceId"),
                "name": info.get("name"),
                "creator": info.get("creator"),
                "creatorVerified": info.get("creatorVerified"),
                "genre": info.get("genre"),
                "subgenre": info.get("subgenre"),
                "icon": info.get("icon"),
                "ccu": now_ccu,
                "ccuAvgToday": round(avg_today) if avg_today else None,
                "growth1d": _pct(avg_today, avg_1d),
                "growth7d": growth_7d,
                "growth28d": _pct(avg_today, avg_28d),
                "peakSeen": peak_seen,
                "visits": info.get("visits"),
                "favorites": info.get("favorites"),
                "likePct": like,
                "ageDays": age,
                "created": info.get("created"),
                "updatedDaysAgo": updated_days,
                "newPlayersPerDay": new_players_per_day(info.get("badges")),
                "passes": pass_summary(info.get("passes")),
                "funnel": badge_funnel(info.get("badges")),
                "chartRanks": chart_ranks,
                "revenueEstimate": revenue_estimate(avg_today, basis),
                "flags": flags,
                "maxPlayers": info.get("maxPlayers"),
                "privateServers": info.get("privateServers"),
                "description": (info.get("description") or "")[:600],
            }
        )
    games.sort(key=lambda g: g["ccu"] or 0, reverse=True)
    total_ccu = sum(g["ccu"] or 0 for g in games)
    return {
        "generated_at": snapshot["taken_at"],
        "history_days": len(history),
        "games_tracked": len(games),
        "total_ccu_tracked": total_ccu,
        "charts": {
            sort_id: {"name": chart["name"], "order": chart["order"][:100]}
            for sort_id, chart in charts.items()
        },
        "notes": snapshot.get("notes", []),
        "method": {
            "ccu": "players online at collection time; daily figures average every sample that day",
            "growth": "today's average players online versus the same figure 1, 7 and 28 days ago",
            "newPlayersPerDay": "largest past-day award among early badges; a floor, not exact",
            "funnel": "badges by share of players who earned them (top badge = 100%)",
            "revenueEstimate": (
                "ESTIMATE ONLY: daily player-hours times Roblox's platform-average bookings and "
                f"developer-exchange per engagement hour ({basis.get('quarter')}), shown as a "
                f"{ESTIMATE_LOW}x-{ESTIMATE_HIGH}x band. Real games vary far more than this."
            ),
        },
        "games": games,
    }


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))


def load_basis(path: Path | None) -> dict[str, Any]:
    if path and path.exists():
        return {**REVENUE_BASIS, **json.loads(path.read_text())}
    return dict(REVENUE_BASIS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("collect", "summarize", "run"))
    parser.add_argument("--out", type=Path, required=True, help="data directory")
    parser.add_argument("--basis", type=Path, help="JSON file overriding REVENUE_BASIS")
    parser.add_argument("--delay", type=float, default=0.35, help="seconds between requests")
    args = parser.parse_args(argv)

    out: Path = args.out
    if args.command in ("collect", "run"):
        snapshot = collect(polite(http_json, args.delay))
        _write(out / "latest.json", snapshot)
        record_history(snapshot, out / "history")
        print(
            f"collected {len(snapshot['games'])} games across {len(snapshot['charts'])} charts; "
            f"notes: {snapshot['notes'] or 'none'}"
        )
    if args.command in ("summarize", "run"):
        snapshot = json.loads((out / "latest.json").read_text())
        basis = load_basis(args.basis or out / "revenue_basis.json")
        radar = summarize(snapshot, load_history(out / "history"), basis=basis)
        _write(out / "radar.json", radar)
        print(f"summarized {radar['games_tracked']} games over {radar['history_days']} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
