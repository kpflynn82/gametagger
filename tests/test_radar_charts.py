"""Multi-region chart reading: Apple RSS parsing and graceful source skipping."""

from __future__ import annotations

from gametagger.radar.charts_multi import (
    parse_apple_rss,
    read_apple_chart,
    read_test_market_charts,
)

APPLE_SAMPLE = {
    "feed": {
        "updated": {"label": "2026-10-14T12:00:00-07:00"},
        "entry": [
            {
                "im:name": {"label": "Dragon Siege"},
                "id": {"attributes": {"im:id": "111222333"}},
                "im:artist": {"label": "Mythic Co"},
            },
            {
                "im:name": {"label": "Merge Harbor"},
                "id": {"attributes": {"im:id": "444555666"}},
                "im:artist": {"label": "Harbor Studio"},
            },
        ],
    }
}


def test_parse_apple_rss_ranks_in_order():
    updated, rows = parse_apple_rss(APPLE_SAMPLE)
    assert updated.startswith("2026-10-14")
    assert rows[0] == (1, "111222333", "Dragon Siege", "Mythic Co")
    assert rows[1][0] == 2


def test_parse_apple_rss_single_entry_object():
    one = {"feed": {"entry": APPLE_SAMPLE["feed"]["entry"][0]}}
    _, rows = parse_apple_rss(one)
    assert len(rows) == 1


def test_read_apple_chart_uses_injected_fetch():
    chart = read_apple_chart("NZ", "grossing", fetch=lambda url: APPLE_SAMPLE)
    assert chart.region == "NZ"
    assert chart.store == "app_store"
    assert chart.rows["111222333"][1] == "Dragon Siege"


def test_read_test_markets_skips_unavailable_sources_via_on_error():
    errors = []

    def bad_fetch(url):
        raise RuntimeError("blocked")

    charts = read_test_market_charts(
        regions=("NZ",),
        kinds=("grossing",),
        play=False,  # NZ has no AppBrain page anyway
        fetch=bad_fetch,
        on_error=lambda where, exc: errors.append(where),
    )
    assert charts == []
    assert errors and "App Store NZ grossing" in errors[0]


def test_nz_has_no_appbrain_but_apple_still_read():
    # NZ is not an AppBrain country, so only the App Store reading should be attempted.
    calls = []

    def fetch(url):
        calls.append(url)
        return APPLE_SAMPLE

    charts = read_test_market_charts(regions=("NZ",), kinds=("grossing",), play=True, fetch=fetch)
    assert len(charts) == 1 and charts[0].store == "app_store"
