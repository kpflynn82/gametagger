"""Build cohort.json from a Google Play Top grossing chart read on the Android emulator.

    uv run python experiments/mobile-top100/play_cohort.py

Top-grossing games (segment ``grossing``) come from
``experiments/play-chart/<date>-android15.json``.
Games the emulator cannot show are added at the rank another chart gives them (``INSERTED``),
and the list is cut at 100. The top-free games from October 8 (``cohort-2026-10-08.json``, segment
``rising``) are kept, except any that are now in the top-grossing list. Each top-grossing game
gets its September 24 rank (``experiments/jev-vs-legacy/cohort.json``) for chart movers.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHART = ROOT / "experiments" / "play-chart" / "2026-10-09-android15.json"
RISING_FROM = HERE / "cohort-2026-10-08.json"
PREVIOUS = ROOT / "experiments" / "jev-vs-legacy" / "cohort.json"
TOP = 100
# Hidden on the emulator; rank from Appfigures' Google Play US grossing chart, 2026-10-09 12:50 PT.
INSERTED = [{"rank": 9, "google_play": "com.playrix.township", "source": "Appfigures"}]


def main() -> None:
    chart = json.loads(CHART.read_text())
    old = json.loads(RISING_FROM.read_text())
    previous = json.loads(PREVIOUS.read_text())
    before = {
        g["ids"]["google_play"]: g
        for g in previous["games"]
        if g.get("list") == "mobile" and (g.get("ids") or {}).get("google_play")
    }
    known = {g["ids"]["google_play"]: g for g in old["games"]} | before

    rows = [dict(r) for r in chart["rows"] if r.get("google_play")]
    for ins in sorted(INSERTED, key=lambda i: i["rank"]):
        game = known[ins["google_play"]]
        rows.insert(
            ins["rank"] - 1,
            {
                "title": game["title"],
                "google_play": ins["google_play"],
                "developer": (game.get("developers") or [None])[0],
                "rank_source": ins["source"],
            },
        )
    games = []
    for rank, row in enumerate(rows[:TOP], 1):
        pkg = row["google_play"]
        dev = row.get("developer") or ((known.get(pkg) or {}).get("developers") or [None])[0]
        chart_info = {
            "previous_rank": (before.get(pkg) or {}).get("rank"),
            "play_rank": row.get("rank"),
        }
        if row.get("rank_source"):
            chart_info["rank_source"] = row["rank_source"]
        games.append(
            {
                "game_id": f"gp-{pkg}",
                "list": "mobile",
                "segment": "grossing",
                "rank": rank,
                "title": row["title"],
                "developers": [dev] if dev else [],
                "ids": {"google_play": pkg},
                "chart": chart_info,
            }
        )
    taken = {g["ids"]["google_play"] for g in games}
    rising = [
        g for g in old["games"] if g["segment"] == "rising" and g["ids"]["google_play"] not in taken
    ]
    hidden = [h for h in chart["hidden_as_incompatible"] if h["google_play"] not in taken]
    cohort = {
        "schema_version": old["schema_version"],
        "created_at": "2026-10-09T20:00:00+00:00",
        "charts": {
            "mobile": {
                "source": "Google Play app on an Android emulator: Games > Top charts > "
                "Top grossing",
                "url": None,
                "chart_date": chart["read_at"][:10],
                "read_at": chart["read_at"],
                "ranked_by": "grossing (Google Play's own top-grossing chart, as the Play "
                "Store app shows it)",
                "region": "US",
                "platform": "Android (Google Play)",
                "rows": len(games),
                "previous_chart_date": previous["charts"]["mobile"]["chart_date"],
                "inserted": INSERTED,
                "hidden": hidden,
                "note": chart["incomplete"],
            },
            "rising": {**old["charts"]["rising"], "rows": len(rising)},
        },
        "rules": old["rules"]
        + [
            "The emulator hides games that refuse emulators; a hidden game with a rank on another "
            "public chart is inserted at that rank, the rest are listed under "
            "charts.mobile.hidden.",
        ],
        "games": games + rising,
        "skipped": [s for s in old.get("skipped") or [] if s["list"] == "rising"],
    }
    (HERE / "cohort.json").write_text(json.dumps(cohort, indent=1, ensure_ascii=False) + "\n")
    print(
        f"{len(games)} top-grossing games (chart of {cohort['charts']['mobile']['chart_date']}), "
        f"{len(rising)} top-free games; hidden and unranked: "
        + ", ".join(h["title"] or h["google_play"] for h in cohort["charts"]["mobile"]["hidden"])
    )


if __name__ == "__main__":
    main()
