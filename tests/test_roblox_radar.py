"""Offline tests for the Roblox Radar collector and summary (no network)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError

from gametagger import roblox_radar as rr


def _game(uid: int, name: str, players: int, *, sponsored: bool = False) -> dict:
    return {
        "universeId": uid,
        "rootPlaceId": uid * 10,
        "name": name,
        "playerCount": players,
        "totalUpVotes": 900,
        "totalDownVotes": 100,
        "isSponsored": sponsored,
        "contentMaturity": "minimal",
        "genreL1": "Simulation",
    }


class FakeRoblox:
    """Answers the URLs the collector asks for; records what was asked."""

    def __init__(self, players: dict[int, int]):
        self.players = players
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        if "/get-sorts?" in url:
            return {
                "sorts": [
                    {"sortId": "filters_v5", "contentType": "Filters"},
                    {
                        "sortId": "top-playing-now",
                        "sortDisplayName": "Top Playing Now",
                        "games": [_game(1, "Steal A Thing", 500_000), _game(2, "Old Obby", 9_000)],
                        "nextPageToken": "page2",
                    },
                    {
                        "sortId": "up-and-coming",
                        "sortDisplayName": "Up-and-Coming",
                        "games": [
                            _game(3, "Chop A Forest", 41_000),
                            _game(9, "Ad", 1, sponsored=True),
                        ],
                    },
                ]
            }
        if "get-sort-content" in url and "pageToken=page2" in url:
            return {"games": [_game(4, "Late Find", 3_000)], "nextPageToken": ""}
        if "get-sort-content" in url and "top-earning" in url:
            return {"games": [_game(1, "Steal A Thing", 500_000)]}
        if "get-sort-content" in url:
            raise HTTPError(url, 404, "no such chart", None, None)
        if "/v1/games/votes" in url:
            ids = [int(i) for i in url.split("universeIds=")[1].split(",")]
            return {"data": [{"id": i, "upVotes": 90, "downVotes": 10} for i in ids]}
        if "/games/icons" in url:
            return {"data": []}
        if "/v1/games?universeIds=" in url:
            ids = [int(i) for i in url.split("universeIds=")[1].split(",")]
            created = {1: "2026-09-20T00:00:00Z", 3: "2026-10-01T00:00:00Z"}
            return {
                "data": [
                    {
                        "id": i,
                        "rootPlaceId": i * 10,
                        "name": f"Game {i}",
                        "creator": {"name": "Studio", "type": "Group", "hasVerifiedBadge": True},
                        "playing": self.players.get(i, 100),
                        "visits": 1_000_000,
                        "favoritedCount": 5_000,
                        "created": created.get(i, "2021-01-01T00:00:00Z"),
                        "updated": "2026-10-16T00:00:00Z",
                        "genre_l1": "Simulation",
                    }
                    for i in ids
                ]
            }
        if "game-passes/v1/universes/1/" in url:
            return {
                "gamePasses": [{"displayName": "VIP", "price": 499}, {"name": "2x", "price": 99}]
            }
        if "game-passes" in url:
            raise HTTPError(url, 404, "nope", None, None)
        if "/badges?" in url:
            return {
                "data": [
                    {
                        "name": "Welcome",
                        "enabled": True,
                        "statistics": {"awardedCount": 1000, "pastDayAwardedCount": 120},
                    },
                    {
                        "name": "Rebirth 1",
                        "enabled": True,
                        "statistics": {"awardedCount": 250, "pastDayAwardedCount": 30},
                    },
                ]
            }
        raise AssertionError(f"unexpected URL {url}")


NOW = datetime(2026, 10, 17, 18, 0, tzinfo=UTC)


def test_collect_reads_charts_pages_and_skips_sponsored():
    snapshot = rr.collect(FakeRoblox({1: 500_000, 3: 41_000}), now=NOW)
    charts = snapshot["charts"]
    assert charts["top-playing-now"]["order"] == [1, 2, 4]  # page 2 was followed
    assert charts["up-and-coming"]["order"] == [3]
    assert charts["up-and-coming"]["sponsored"] == [9]
    assert "top-earning" in charts
    assert any("top-revisited" in note for note in snapshot["notes"])
    assert "9" not in snapshot["games"]  # sponsored placements aren't tracked as games
    assert snapshot["games"]["1"]["passes"] == [
        {"name": "VIP", "price": 499, "forSale": True},
        {"name": "2x", "price": 99, "forSale": True},
    ]
    assert snapshot["games"]["2"]["passes"] is None  # unknown, not "no passes"


def test_history_and_summary_growth_flags(tmp_path):
    history_dir = tmp_path / "history"
    week_ago = rr.collect(FakeRoblox({1: 200_000, 3: 10_000}), now=NOW - timedelta(days=7))
    rr.record_history(week_ago, history_dir)
    today = rr.collect(FakeRoblox({1: 500_000, 3: 41_000}), now=NOW)
    rr.record_history(today, history_dir)
    basis = {"quarter": "QX", "bookings_usd": 2.4e9, "devex_usd": 4.8e8, "engagement_hours": 4.8e10}

    radar = rr.summarize(today, rr.load_history(history_dir), basis=basis)
    by_id = {g["universeId"]: g for g in radar["games"]}

    hit = by_id[1]
    assert hit["growth7d"] == 150.0
    assert {"breakout", "new-and-hot", "rising", "updated-this-week"} <= set(hit["flags"])
    assert hit["newPlayersPerDay"] == 120
    assert hit["funnel"][1] == {"name": "Rebirth 1", "awarded": 250, "share": 25.0, "pastDay": 30}
    assert hit["passes"]["median"] == 299
    # 500k players x 24h x $0.05/hour, shown as a 0.5x-2x band
    assert hit["revenueEstimate"]["spendPerDay"] == [300_000, 1_200_000]
    assert "up-and-coming" in by_id[3]["flags"]
    assert radar["history_days"] == 2
    assert radar["games"][0]["universeId"] == 1  # busiest first


def test_revenue_estimate_disabled_without_basis():
    assert rr.revenue_estimate(1000, {"quarter": "QX", "bookings_usd": None}) is None


def test_token_finder_ignores_previous_and_empty():
    assert rr._token({"previousPageToken": "a", "nextPageToken": "b"}) == "b"
    assert rr._token({"nextPageCursor": ""}) is None


def test_main_run_writes_files(tmp_path, monkeypatch):
    fake = FakeRoblox({1: 500_000})
    monkeypatch.setattr(rr, "http_json", fake)
    assert rr.main(["run", "--out", str(tmp_path), "--delay", "0"]) == 0
    radar = json.loads((tmp_path / "radar.json").read_text())
    assert radar["games_tracked"] == 4
    assert list((tmp_path / "history").glob("*.json"))


def test_export_dashboard_chunks_and_compacts(tmp_path):
    history_dir = tmp_path / "history"
    snap = rr.collect(FakeRoblox({1: 500_000, 3: 41_000}), now=NOW)
    rr.record_history(snap, history_dir)
    radar = rr.summarize(snap, rr.load_history(history_dir))
    paths = rr.export_dashboard(radar, tmp_path / "export")
    names = sorted(p.name for p in paths)
    assert names == ["radar-games-1.json", "radar-latest.json"]
    meta = json.loads((tmp_path / "export" / "radar-latest.json").read_text())
    assert meta["chunks"] == 1 and meta["gamesShown"] == 4
    chunk = json.loads((tmp_path / "export" / "radar-games-1.json").read_text())
    top = chunk["games"][0]
    assert top["id"] == 1 and top["ccu"] == 500_000
    assert top["passes"]["top"][0] == {"n": "VIP", "p": 499}
    assert top["funnel"][0]["s"] == 100.0
    assert top["rev"]["spend"][0] > 0  # the default Q2 2026 basis gives a labeled band
