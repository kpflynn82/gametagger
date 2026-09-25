"""Compare cheaper image-description variants with the benchmark's rich mode on the same games.

    uv run python experiments/jev-vs-legacy/cost-test/compare.py

Reads the git-ignored results in ``benchmark-runs/jev-vs-legacy/results`` for the games where
every compared arm finished, and writes ``summary.json`` beside this file. It reports, per arm:
recall and contradiction against Steam players' top 20 tags (Steam games only), agreement with
the baseline's present and absent attributes, primary-genre agreement, statements quarantined
for breaking the Observer's rules, and cost per game split into image description and Jev.
Variants described their images through the Message Batches API at half price; the list-price
equivalent is shown too so that the model and prompt effects are separable from the discount.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from gametagger.comparison.crosswalk import load_crosswalks
from gametagger.comparison.scoring import normalize, steam_positives
from gametagger.genome.vocabulary import load_vocabulary
from gametagger.taxonomy import load_taxonomy

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ROOT = EXP.parents[1]
RESULTS = ROOT / "benchmark-runs/jev-vs-legacy/results"
BASELINE = "rich"
VARIANTS = ("rich-haiku", "rich-lean")
LABEL = {
    "rich": "Sonnet 5, full descriptions (benchmark)",
    "rich-haiku": "Haiku 4.5 describes",
    "rich-lean": "Sonnet 5, brief descriptions, duplicates skipped",
}


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def main() -> None:
    taxonomy = load_taxonomy()
    crosswalks = load_crosswalks(taxonomy, load_vocabulary(taxonomy))
    names = {g.id: g.display_name for g in taxonomy.genres_by_id.values()}
    cohort = json.loads((EXP / "cohort.json").read_text())
    key = json.loads((EXP / "answer-key-steam-tags.json").read_text())["games"]
    arms = (BASELINE, *VARIANTS)
    games = []
    for g in cohort["games"]:
        folder = RESULTS / g["game_id"]
        if all((folder / f"{a}.json").exists() for a in arms):
            games.append((g, {a: json.loads((folder / f"{a}.json").read_text()) for a in arms}))

    out = {"games": len(games), "steam_games": 0, "arms": {}}
    steam_sets = {}
    for g, _ in games:
        entry = key.get(g["game_id"])
        if entry and entry.get("status") == "ok":
            steam_sets[g["game_id"]] = steam_positives(entry, crosswalks)[0]
    out["steam_games"] = sum(1 for g, _ in games if g["game_id"] in steam_sets)

    for arm in arms:
        hits = positives = contradicted = 0
        agree_present, agree_absent, flips, genre_same = [], [], 0, []
        quarantined, tags, cost_img, cost_jev, observe_s, reused = [], [], [], [], [], []
        for g, recs in games:
            rec, base = recs[arm], recs[BASELINE]
            pred, ref = normalize(rec, crosswalks, names), normalize(base, crosswalks, names)
            tags.append(len(pred.present))
            quarantined.append(rec.get("quarantined_observations") or 0)
            cost_img.append(rec["cost_usd"]["anthropic"])
            cost_jev.append(rec["cost_usd"]["typesafe"])
            observe_s.append((rec.get("stage_ms") or {}).get("observe", 0) / 1000)
            reused.append(rec.get("descriptions_reused") or 0)
            if arm != BASELINE:
                if ref.present:
                    agree_present.append(len(pred.present & ref.present) / len(ref.present))
                if ref.absent:
                    agree_absent.append(len(pred.absent & ref.absent) / len(ref.absent))
                flips += len(pred.present & ref.absent) + len(pred.absent & ref.present)
                genre_same.append(rec.get("primary_genre") == base.get("primary_genre"))
            positives_here = steam_sets.get(g["game_id"])
            if positives_here:
                positives += len(positives_here)
                hits += len(positives_here & pred.present)
                contradicted += len(positives_here & pred.absent)
        batch = arm != BASELINE
        img = mean(cost_img)
        out["arms"][arm] = {
            "label": LABEL[arm],
            "recall_vs_steam": hits / positives if positives else None,
            "said_absent_vs_steam": contradicted / positives if positives else None,
            "attributes_present_mean": mean(tags),
            "keeps_baseline_present": mean(agree_present),
            "keeps_baseline_absent": mean(agree_absent),
            "present_absent_flips_per_game": flips / len(games) if batch and games else None,
            "same_primary_genre": mean([float(x) for x in genre_same]) if batch else None,
            "quarantined_statements_per_game": mean(quarantined),
            "image_cost_per_game": img,
            "image_cost_per_game_at_list_price": img * 2 if batch and img is not None else img,
            "jev_cost_per_game": mean(cost_jev),
            "total_cost_per_game": mean([a + b for a, b in zip(cost_img, cost_jev, strict=True)]),
            "described_in_batch": batch,
            "descriptions_reused_per_game": mean(reused),
            "observe_seconds_per_game": mean(observe_s),
        }
    (HERE / "summary.json").write_text(json.dumps(out, indent=2) + "\n")
    for arm, a in out["arms"].items():
        cells = [
            f"recall {a['recall_vs_steam']:.3f}",
            f"absent {a['said_absent_vs_steam']:.3f}",
            f"tags {a['attributes_present_mean']:.1f}",
            f"keep+ {a['keeps_baseline_present'] or 0:.2f}",
            f"genre= {a['same_primary_genre'] or 0:.2f}",
            f"quarantined {a['quarantined_statements_per_game']:.1f}",
            f"images ${a['image_cost_per_game']:.4f}",
            f"(list ${a['image_cost_per_game_at_list_price']:.4f})",
            f"jev ${a['jev_cost_per_game']:.4f}",
        ]
        print(f"{arm:11} " + "  ".join(cells))
    print(f"{out['games']} games, {out['steam_games']} with Steam tags")


if __name__ == "__main__":
    main()
