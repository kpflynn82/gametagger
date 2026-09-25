"""A blinded review sheet for the owner, and its separate key.

For a random, stratified sample of games, the sheet lists every primary genre any method chose
and a random sample of the attributes any method reported present, pooled and shuffled, with no
hint of which method proposed what. The owner marks each row yes / no / unsure. Because rows are
sampled uniformly from the pooled proposals, each method's reviewed rows are a fair sample of
its own proposals, so per-method precision is unbiased. The key (row -> methods) lives in a
separate file and is only read by scoring.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any

from gametagger.comparison.crosswalk import Crosswalks
from gametagger.comparison.scoring import FAILED, normalize

SHEET_COLUMNS = [
    "item",
    "game",
    "store_page",
    "kind",
    "label",
    "definition",
    "your_verdict",
    "note",
]
STORE_PAGE = {
    "steam_app": "https://store.steampowered.com/app/{}",
    "google_play": "https://play.google.com/store/apps/details?id={}",
}


def _store_link(game: dict) -> str:
    for key, template in STORE_PAGE.items():
        if game["ids"].get(key):
            return template.format(game["ids"][key])
    return ""


def sample_games(cohort: dict, n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    lists = {}
    for game in cohort["games"]:
        lists.setdefault(game["list"], []).append(game)
    chosen = []
    for name in sorted(lists):
        pool = lists[name]
        chosen += rng.sample(pool, min(len(pool), n // len(lists) or 1))
    return chosen


def build_review(
    cohort: dict,
    results: dict[str, dict[str, dict]],
    crosswalks: Crosswalks,
    vocabulary,
    taxonomy,
    *,
    games: int = 30,
    tags_per_game: int = 15,
    seed: int = 20260924,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    rng = random.Random(seed + 1)
    names = {g.id: g.display_name for g in taxonomy.genres_by_id.values()}
    definitions = {g.id: g.definition for g in taxonomy.genres_by_id.values()}
    tags = vocabulary.tags_by_id
    arms = [a for a in results if results[a]]
    rows, key = [], {"seed": seed, "items": {}}
    n = 0
    for game in sample_games(cohort, games, seed):
        gid = game["game_id"]
        preds = {
            a: normalize(results[a][gid], crosswalks, names)
            for a in arms
            if gid in results[a] and results[a][gid].get("status") not in FAILED
        }
        if not preds:
            continue
        genres: dict[str, dict] = {}
        for arm, p in preds.items():
            if not p.genre_label:
                continue
            # Show every method's genre in the v4 wording where an exact match exists, so the
            # wording does not reveal which vocabulary (method) proposed it.
            label = names[p.genre_v4[0]] if p.genre_relation == "exact" else p.genre_label
            definition = definitions.get(p.genre_v4[0], "") if p.genre_relation == "exact" else ""
            entry = genres.setdefault(label, {"arms": [], "definition": definition})
            entry["arms"].append(arm)
        attrs: dict[str, list[str]] = {}
        for arm, p in preds.items():
            for tag_id in p.present:
                attrs.setdefault(tag_id, []).append(arm)
        sampled = rng.sample(sorted(attrs), min(len(attrs), tags_per_game))
        items = [
            ("primary genre", label, g["definition"], g["arms"]) for label, g in genres.items()
        ]
        items += [("attribute", tags[t].label, tags[t].definition, attrs[t]) for t in sampled]
        rng.shuffle(items)
        for kind, label, definition, proposing in items:
            n += 1
            item = f"R{n:04d}"
            rows.append(
                {
                    "item": item,
                    "game": game["title"],
                    "store_page": _store_link(game),
                    "kind": kind,
                    "label": label,
                    "definition": definition,
                    "your_verdict": "",
                    "note": "",
                }
            )
            key["items"][item] = {
                "game_id": gid,
                "kind": "genre" if kind == "primary genre" else "tag",
                "label": label,
                "arms": sorted(proposing),
            }
    return rows, key


def write_sheet(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
