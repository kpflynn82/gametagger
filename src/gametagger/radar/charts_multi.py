"""Read top-grossing and top-free charts across the mobile test markets.

Two public sources, both already on the ``genome.net`` allowlist:

* **Google Play** via AppBrain's per-country ranking pages (``.../top_grossing/game/ca``,
  ``.../top_free/game/au``). AppBrain covers Canada and Australia but not New Zealand.
* **App Store** via Apple's free RSS feed
  (``itunes.apple.com/{cc}/rss/topgrossingapplications/limit=N/genre=6014/json``), which covers
  Canada, Australia and New Zealand.

Every reading returns a ``RegionChart``. Network calls go through ``genome.net`` (fixed hosts,
size caps, no URL echoed in errors). All readers take an injectable ``fetch`` so tests never hit
the network.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gametagger.comparison.charts import parse_appbrain
from gametagger.genome.net import fetch_json, fetch_text
from gametagger.radar.candidate import ChartKind, RegionChart

APPBRAIN_PLAY = "https://www.appbrain.com/stats/google-play-rankings/{kind}/game/{cc}"
APPLE_RSS = "https://itunes.apple.com/{cc}/rss/{chart}applications/limit={limit}/genre=6014/json"
# AppBrain country pages exist for these; New Zealand is not among them.
APPBRAIN_COUNTRIES = frozenset({"CA", "AU", "US", "GB", "DE", "FR", "JP", "BR", "KR"})
APPBRAIN_KIND = {"grossing": "top_grossing", "free": "top_free"}
APPLE_CHART = {"grossing": "topgrossing", "free": "topfree"}


def parse_apple_rss(payload: Any) -> tuple[str | None, list[tuple[int, str, str, str | None]]]:
    """Return (updated_date, rows) from Apple's RSS JSON. Rows: (rank, app_id, name, artist)."""

    feed = (payload or {}).get("feed") or {}
    updated = ((feed.get("updated") or {}).get("label")) if isinstance(feed, dict) else None
    entries = feed.get("entry") or []
    if isinstance(entries, dict):  # a one-entry feed is an object, not a list
        entries = [entries]
    rows: list[tuple[int, str, str, str | None]] = []
    for rank, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            continue
        app_id = str((entry.get("id") or {}).get("attributes", {}).get("im:id") or "").strip()
        name = str((entry.get("im:name") or {}).get("label") or "").strip()
        artist = str((entry.get("im:artist") or {}).get("label") or "").strip() or None
        if app_id and name:
            rows.append((rank, app_id, name, artist))
    return updated, rows


def read_play_chart(
    region: str, kind: ChartKind, *, fetch_page: Callable[[str], str] = fetch_text
) -> RegionChart:
    url = APPBRAIN_PLAY.format(kind=APPBRAIN_KIND[kind], cc=region.lower())
    date, rows = parse_appbrain(fetch_page(url))
    return RegionChart(
        region=region,
        store="google_play",
        kind=kind,
        chart_date=date,
        rows={r["package"]: (r["rank"], r["title"], r.get("developer")) for r in rows},
    )


def read_apple_chart(
    region: str, kind: ChartKind, *, limit: int = 100, fetch: Callable[[str], Any] = fetch_json
) -> RegionChart:
    url = APPLE_RSS.format(cc=region.lower(), chart=APPLE_CHART[kind], limit=limit)
    date, rows = parse_apple_rss(fetch(url))
    return RegionChart(
        region=region,
        store="app_store",
        kind=kind,
        chart_date=date,
        rows={app_id: (rank, name, artist) for rank, app_id, name, artist in rows},
    )


def read_test_market_charts(
    *,
    regions: tuple[str, ...] = ("CA", "AU", "NZ"),
    kinds: tuple[ChartKind, ...] = ("grossing", "free"),
    apple: bool = True,
    play: bool = True,
    limit: int = 100,
    fetch: Callable[[str], Any] = fetch_json,
    fetch_page: Callable[[str], str] = fetch_text,
    on_error: Callable[[str, Exception], None] | None = None,
) -> list[RegionChart]:
    """Read every available (region, store, kind) chart. Skips what a source cannot serve.

    A failed reading is reported through ``on_error`` and skipped, so one dead source never sinks
    the run -- the signal layer treats a missing chart as "absent", which is itself informative.
    """

    charts: list[RegionChart] = []
    for region in regions:
        for kind in kinds:
            if apple:
                try:
                    charts.append(read_apple_chart(region, kind, limit=limit, fetch=fetch))
                except Exception as exc:  # noqa: BLE001 -- one source failing is expected
                    if on_error:
                        on_error(f"App Store {region} {kind}", exc)
            if play and region in APPBRAIN_COUNTRIES:
                try:
                    charts.append(read_play_chart(region, kind, fetch_page=fetch_page))
                except Exception as exc:  # noqa: BLE001
                    if on_error:
                        on_error(f"Google Play {region} {kind}", exc)
    return charts
