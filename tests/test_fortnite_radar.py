"""Offline tests for the Fortnite Radar collector (no network)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError

from gametagger import fortnite_radar as fr

NOW = datetime(2026, 11, 12, 21, 0, tzinfo=UTC)


def _stamp(day: int) -> str:
    return f"2026-11-{day:02d}T00:00:00.000Z"


def _metrics(days: dict[int, float | None], *, d7: float | None = 0.4) -> dict:
    payload = {
        name: [{"value": value, "timestamp": _stamp(day)} for day, value in days.items()]
        for name in fr.VALUE_METRICS
    }
    payload["retention"] = [
        {
            "d1": None if value is None else 0.5,
            "d7": None if value is None else d7,
            "timestamp": _stamp(day),
        }
        for day, value in days.items()
    ]
    return payload


class FakeFortnite:
    """Answers the URLs the collector asks for; records what was asked."""

    def __init__(self, ranks: dict[str, list[str]], *, refuse_window: bool = False):
        self.ranks = ranks
        self.refuse_window = refuse_window
        self.tags: dict[str, list[str]] = {}
        self.metrics: dict[str, dict] = {}
        self.broken: set[str] = set()
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        path = url.removeprefix(fr.API)
        if path == "/genres":
            return {"data": [{"slug": slug, "displayName": slug.title()} for slug in self.ranks]}
        if path.endswith("/rankings"):
            slug = path.split("/")[2]
            codes = self.ranks[slug]
            return {
                "meta": {"total": 6695, "snapshot": "2026-11-12T17:00:00.000Z"},
                # Deliberately out of order: the collector must sort by rank.
                "data": [
                    {"islandCode": code, "rank": rank}
                    for rank, code in reversed(list(enumerate(codes, start=1)))
                ],
            }
        code = path.split("/")[2].split("?")[0]
        if code in self.broken:
            raise HTTPError(url, 404, "not found", None, None)
        if "/metrics/day" in path:
            if "?" in path and self.refuse_window:
                raise HTTPError(url, 400, "bad request", None, None)
            return self.metrics.get(code, _metrics({10: None, 11: 100.0, 12: 40.0}))
        return {
            "code": code,
            "creatorCode": "maker",
            "title": f"Island {code}",
            "createdIn": "UEFN",
            "tags": self.tags.get(code, ["tycoon"]),
        }


def _load(path):
    return json.loads(path.read_text())


def test_collects_ranks_details_and_numbers(tmp_path):
    api = FakeFortnite({"horror": ["A", "B", "C"], "shooter": ["D"]})
    report = fr.collect(api, tmp_path, now=NOW, top=2)

    assert report["ok"] and report["genres"] == 2
    assert report["islands_ranked"] == 4 and report["islands_collected"] == 3  # C is below top 2
    assert report["metrics_request"] == "seven-day window"

    ranks = _load(tmp_path / "rankings" / "2026-11-12.json")
    assert ranks["genres"]["horror"]["codes"] == ["A", "B", "C"]
    assert ranks["genres"]["horror"]["total"] == 6695

    islands = _load(tmp_path / "islands.json")
    assert islands["A"]["title"] == "Island A" and islands["A"]["tags"] == ["tycoon"]
    assert islands["A"]["best_rank"] == 1 and islands["A"]["genres"] == ["horror"]
    assert "title" not in islands["C"] and islands["C"]["best_rank"] == 3

    assert not (tmp_path / "metrics" / "C.json").exists()
    summary = _load(tmp_path / "summary.json")
    row = summary["genres"]["horror"]["top"][0]
    assert row["code"] == "A" and row["creator_tags"] == ["tycoon"]
    # The 12th is today and still filling, so the 11th is the latest finished day.
    assert row["latest_complete_day"] == _stamp(11) and row["latest"]["plays"] == 100.0
    assert (
        row["latest"]["d1"] == 0.5 and row["days_of_history"] == 2
    )  # the empty day is not counted
    assert (
        _load(tmp_path / "metrics" / "A.json")["days"][_stamp(12)]["plays"] == 40.0
    )  # still stored


def test_history_accumulates_and_empty_values_never_erase_reported_ones(tmp_path):
    api = FakeFortnite({"horror": ["A"]})
    api.metrics["A"] = _metrics({11: 80.0, 12: 100.0})
    fr.collect(api, tmp_path, now=NOW, top=1)

    # Next day: the window has moved on, the 12th is revised, and the 11th comes back empty.
    api.metrics["A"] = _metrics({11: None, 12: 110.0, 13: 120.0})
    fr.collect(api, tmp_path, now=NOW + timedelta(days=1), top=1)

    days = _load(tmp_path / "metrics" / "A.json")["days"]
    assert list(days) == [_stamp(11), _stamp(12), _stamp(13)]
    assert days[_stamp(11)]["plays"] == 80.0  # kept
    assert days[_stamp(12)]["plays"] == 110.0  # revised
    assert days[_stamp(13)]["plays"] == 120.0  # new
    assert _load(tmp_path / "summary.json")["longest_history_days"] == 3
    assert (tmp_path / "rankings" / "2026-11-13.json").exists()


def test_not_reported_stays_null_not_zero(tmp_path):
    api = FakeFortnite({"horror": ["A"]})
    api.metrics["A"] = _metrics({12: 100.0}, d7=None)
    fr.collect(api, tmp_path, now=NOW, top=1)
    bucket = _load(tmp_path / "metrics" / "A.json")["days"][_stamp(12)]
    assert bucket["d7"] is None and bucket["d1"] == 0.5


def test_falls_back_when_the_date_window_is_refused(tmp_path):
    api = FakeFortnite({"horror": ["A", "B"]}, refuse_window=True)
    report = fr.collect(api, tmp_path, now=NOW, top=2)
    assert report["ok"] and report["islands_collected"] == 2
    assert report["metrics_request"] == "default"
    windowed = [url for url in api.calls if "/metrics/day?" in url]
    assert len(windowed) == 1  # asked once, then stopped asking that way
    assert "from=2026-11-05" in windowed[0]


def test_one_bad_island_does_not_stop_the_run_or_change_the_request_form(tmp_path):
    api = FakeFortnite({"horror": ["A", "B", "C"]})
    api.broken.add("A")  # the very first island fails outright
    report = fr.collect(api, tmp_path, now=NOW, top=3)
    assert report["ok"] and report["islands_failed"] == 1 and report["islands_collected"] == 2
    assert report["metrics_request"] == "seven-day window"
    assert any("island A failed: HTTP 404" in note for note in report["notes"])


def test_stops_asking_after_a_long_run_of_failures(tmp_path):
    codes = [f"X{i:02d}" for i in range(40)]
    api = FakeFortnite({"horror": codes})
    api.broken.update(codes)
    report = fr.collect(api, tmp_path, now=NOW, top=40)
    assert not report["ok"] and report["islands_failed"] == fr.FAILURE_LIMIT
    assert _load(tmp_path / "last_run.json")["ok"] is False


def test_tag_changes_are_recorded_and_dropped_islands_stay_tracked(tmp_path):
    api = FakeFortnite({"horror": ["A", "B"]})
    fr.collect(api, tmp_path, now=NOW, top=2)

    api.ranks["horror"] = ["B", "Z"]  # A falls out of the ranking entirely
    api.tags["A"] = ["horror", "co-op"]
    later = NOW + timedelta(days=3)
    report = fr.collect(api, tmp_path, now=later, top=2)
    assert report["islands_tracked"] == 3  # B, Z and the recently ranked A

    islands = _load(tmp_path / "islands.json")
    assert islands["A"]["tag_changes"] == [
        {"date": "2026-11-15", "from": ["tycoon"], "to": ["horror", "co-op"]}
    ]
    assert islands["A"]["last_ranked"] == "2026-11-12" and islands["B"]["best_rank"] == 1

    # After the keep-tracking period, A is no longer collected.
    much_later = NOW + timedelta(days=fr.KEEP_TRACKING_DAYS + 1)
    assert fr.collect(api, tmp_path, now=much_later, top=2)["islands_tracked"] == 2
