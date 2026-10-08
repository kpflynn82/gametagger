"""Make the site's game data mobile-first.

Today's Google Play top-grossing games and the rising games in ``cohort.json`` replace the
September 24 top 50; Steam's 50 most-played games stay as they are. Tags come from this run
(``new-run/per-game.jsonl``) or, for games already tagged on October 5, from
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
    (HERE / "new-run" / "per-game.jsonl", "2026-10-08"),
    (ROOT / "experiments" / "mobile-retag-v2" / "per-game.jsonl", "2026-10-05"),
)
DATA_RE = re.compile(r"const DATA = (\{.*?\});\n", re.S)
DECIDED = ("strong", "likely", "absent", "conflicting")


def load_records() -> dict[str, tuple[dict, str]]:
    records: dict[str, tuple[dict, str]] = {}
    for path, tagged in SOURCES:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("arm") == "rich" and r.get("tags") and r["game_id"] not in records:
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
    now = {c["ids"]["google_play"] for c in cohort["games"] if c.get("ids", {}).get("google_play")}
    dropped = [
        {"id": g["id"], "title": g["title"], "prev": g["rank"]}
        for g in data["games"]
        if g["list"] == "mobile" and g["id"].removeprefix("gp-") not in now
    ]
    charts = cohort["charts"]
    rising = charts.get("rising") or {}
    data["games"] = steam + games
    data["mobile"] = {
        "chart_date": charts["mobile"].get("chart_date"),
        "previous_chart_date": charts["mobile"].get("previous_chart_date"),
        "grossing": sum(g["list"] == "mobile" for g in games),
        "rising": sum(g["list"] == "rising" for g in games),
        "rising_source": rising.get("source"),
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
        f"{len(m['missing'])} games without tags yet"
        + (f": {', '.join(m['missing'])}" if m["missing"] else ".")
    )


if __name__ == "__main__":
    sys.exit(main())
