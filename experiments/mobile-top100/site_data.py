"""Make the site's game data mobile-first.

The Google Play top-grossing games and the top-free games in ``cohort.json`` replace the
September 24 top 50; Steam's 50 most-played games stay as they are. Tags come from the Mac runs
(``new-run/per-game.jsonl``: October 8, and October 9 for games not in
``new-run/tagged-2026-10-08.txt``) or, for games tagged on October 5, from
``experiments/mobile-retag-v2/per-game.jsonl`` (same method: vocabulary v2, store pages). The
site shows the 189 v1 tags, so only those are kept. Games that were in the September data keep
their old-method answers for the game profile.

    uv run python experiments/mobile-top100/site_data.py
    uv run python experiments/jev-vs-legacy/site/refresh_web.py

The first command rewrites the data inside ``web/index.html``; the second applies the template.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WEB = ROOT / "web" / "index.html"
SOURCES = (  # newest first: a game tagged in both keeps the newer answers
    (HERE / "new-run" / "per-game.jsonl", None),  # October 8 or 9, see tagged_on()
    (ROOT / "experiments" / "mobile-retag-v2" / "per-game.jsonl", "2026-10-05"),
)
OCT8 = HERE / "new-run" / "tagged-2026-10-08.txt"
SEPTEMBER = ROOT / "experiments" / "jev-vs-legacy" / "cohort.json"
DATA_RE = re.compile(r"const DATA = (\{.*?\});\n", re.S)
DECIDED = ("strong", "likely", "absent", "conflicting")


def load_records() -> dict[str, tuple[dict, str]]:
    oct8 = set(OCT8.read_text().split()) if OCT8.exists() else set()
    records: dict[str, tuple[dict, str]] = {}
    for path, date in SOURCES:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("arm") == "rich" and r.get("tags") and r["game_id"] not in records:
                    tagged = date or ("2026-10-08" if r["game_id"] in oct8 else "2026-10-09")
                    records[r["game_id"]] = (r, tagged)
    return records


def build(data: dict, cohort: dict, records: dict, taxonomy) -> dict:
    tag_ids = {t["id"] for t in data["glossary"]["tags"]}
    old = {g["id"]: g for g in data["games"]}
    steam = [g for g in data["games"] if g["list"] == "steam"]
    games, missing = [], []
    for c in cohort["games"]:
        found = records.get(c["game_id"])
        if not found:
            missing.append(c["title"])
            continue
        r, tagged = found
        tags = r.get("tags") or {}
        jev = {
            t: [v["tier"], v.get("p_present")]
            for t, v in tags.items()
            if t in tag_ids and v.get("tier") in DECIDED
        }
        gid = r.get("primary_genre")
        genre = taxonomy.genres_by_id.get(gid) if gid else None
        prev = old.get(c["game_id"]) or {}
        detail = {
            "developers": c.get("developers") or (prev.get("detail") or {}).get("developers") or [],
            "jev": jev,
            "genres": [[g, p] for g, p in r.get("top_genres") or [] if p and p >= 0.01],
            "secondary": r.get("secondary_genres") or [],
            "steam": [],
        }
        for arm in ("legacy-deep", "legacy-standard"):
            if (prev.get("detail") or {}).get(arm):
                detail[arm] = prev["detail"][arm]
        row = {
            "id": c["game_id"],
            "title": c["title"],
            "list": "rising" if c.get("segment") == "rising" else "mobile",
            "rank": c["rank"],
            "rich": {
                "status": r.get("status"),
                "genre": genre.display_name if genre else None,
                "p": r.get("primary_genre_probability"),
                "present": sum(v[0] in ("strong", "likely") for v in jev.values()),
                "recall": None,
                "cost": (r.get("cost_usd") or {}).get("total"),
                "sec": (r.get("wall_ms") or 0) / 1000,
            },
            "legacy-deep": prev.get("legacy-deep"),
            "legacy-standard": prev.get("legacy-standard"),
            "detail": detail,
            "peak": None,
            "last_week": None,
            "genre_id": genre.id if genre else None,
            "family": genre.family if genre else None,
            "tagged": tagged,
        }
        if row["list"] == "mobile":
            row["prev"] = (c.get("chart") or {}).get("previous_rank")
        games.append(row)
    charts = cohort["charts"]
    mobile = charts["mobile"]
    hidden = mobile.get("hidden") or []
    now = {c["ids"]["google_play"] for c in cohort["games"] if c.get("ids", {}).get("google_play")}
    # A game the emulator hides has not left the chart; it just cannot be ranked.
    now |= {h["google_play"] for h in hidden}
    # Compare with the September 24 top 50 (not the page's current data), so a rerun is stable.
    september = json.loads(SEPTEMBER.read_text())["games"]
    dropped = [
        {"id": f"gp-{g['ids']['google_play']}", "title": g["title"], "prev": g["rank"]}
        for g in september
        if g.get("list") == "mobile" and g["ids"]["google_play"] not in now
    ]
    rising = charts.get("rising") or {}
    from_app = "Play Store app" in (mobile.get("source") or "") or "Google Play app" in (
        mobile.get("source") or ""
    )
    data["games"] = steam + games
    data["mobile"] = {
        "chart_date": mobile.get("chart_date"),
        "previous_chart_date": mobile.get("previous_chart_date"),
        # The October 9 chart was read in the Play Store app and September 24's came from
        # AppBrain. A game missing from one source may not be new, so the site shows only games
        # ranked in both.
        "grossing_source": "app" if from_app else "appbrain",
        "cross_source": from_app,
        "inserted": [
            {
                "title": next(
                    c["title"]
                    for c in cohort["games"]
                    if c["ids"]["google_play"] == i["google_play"]
                ),
                "rank": i["rank"],
                "source": i["source"],
            }
            for i in mobile.get("inserted") or []
        ],
        "hidden": [h["title"] for h in hidden],
        "grossing": sum(g["list"] == "mobile" for g in games),
        "rising": sum(g["list"] == "rising" for g in games),
        "rising_source": rising.get("source"),
        # When AppBrain's new-games chart is empty the extra games come from its top-free chart;
        # the site then calls them "Top free" rather than "Rising".
        "rising_label": "Top free"
        if "top free games" in (rising.get("source") or "")
        else "Rising",
        "grossing_fallback": bool(mobile.get("fallback")),
        "rising_chart_date": rising.get("chart_date"),
        "dropped": dropped,
        "missing": missing,
        "tagged": sorted({g["tagged"] for g in games}),
    }
    return data


def main() -> None:
    from gametagger.taxonomy import load_taxonomy

    cohort = json.loads((HERE / "cohort.json").read_text())
    page = WEB.read_text()
    match = DATA_RE.search(page)
    if not match:
        raise SystemExit("No DATA block in web/index.html")
    data = build(json.loads(match.group(1)), cohort, load_records(), load_taxonomy())
    blob = json.dumps(data, separators=(",", ":"), default=str)
    WEB.write_text(page[: match.start(1)] + blob + page[match.end(1) :])
    m = data["mobile"]
    print(
        f"{m['grossing']} top-grossing and {m['rising']} rising games on the site; "
        f"{len(m['dropped'])} of September's top 50 left the top 100; "
        f"{len(m['hidden'])} hidden by the emulator; "
        f"{len(m['missing'])} games without tags yet"
        + (f": {', '.join(m['missing'])}" if m["missing"] else ".")
    )


if __name__ == "__main__":
    sys.exit(main())
