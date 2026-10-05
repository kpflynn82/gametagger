"""Summarize the Google Play top-50 retag with vocabulary v2 (store pages only).

Reads the compact results of ``gametagger-compare run --vocabulary v2`` from the work directory
(git-ignored) and writes shareable files next to this script: tag states and counts only, no store
text or images.

    uv run python experiments/mobile-retag-v2/summarize.py \\
        --workdir benchmark-runs/mobile-retag-v2

Outputs:
* ``summary.json``: per new tag, how many games came back strong, likely, absent, not enough
  evidence, conflicting or not evaluated; the umbrella-tag comparison for owner decision 2; costs.
* ``per-game.jsonl``: one compact record per game (as in ``experiments/jev-vs-legacy/results``).
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEPTEMBER = HERE.parent / "jev-vs-legacy" / "results" / "per-game.jsonl"
TIERS = ("strong", "likely", "absent", "conflicting", "unknown", "not_evaluated", "error")
NEW_CATEGORIES = ("meta", "liveops", "ads", "depth")
# Owner decision 2: do mobile games still need the broad v1 tags next to the specific v2 ones?
UMBRELLAS = {
    "engagement_daily_rewards": ["liveops_login_calendar", "liveops_daily_missions"],
    "engagement_auto_play": ["meta_offline_earnings"],
    "monetization_ads": [
        "ads_rewarded_video",
        "ads_interstitials",
        "ads_banners",
        "ads_removal_purchase",
        "ads_offerwall",
    ],
}


def present(tag: dict | None) -> bool:
    return bool(tag) and tag.get("tier") in ("strong", "likely")


def load(workdir: Path) -> list[dict]:
    records = []
    for path in sorted((workdir / "results").glob("*/rich.json")):
        record = json.loads(path.read_text())
        if record.get("list") == "mobile":
            records.append(record)
    return records


def summarize(records: list[dict], vocabulary) -> dict:
    by_id = vocabulary.tags_by_id
    new = [t for t in vocabulary.tags if t.category in NEW_CATEGORIES]
    finished = [r for r in records if r.get("tags")]
    per_tag = {}
    for tag in new:
        tiers = Counter(r["tags"].get(tag.id, {}).get("tier", "missing") for r in finished)
        per_tag[tag.id] = {
            "label": tag.label,
            "category": tag.category,
            "requires": vocabulary.requires.get(tag.id),
            **{tier: tiers.get(tier, 0) for tier in TIERS},
        }
    answers = Counter(r["tags"].get(t.id, {}).get("tier", "missing") for r in finished for t in new)
    asked = sum(answers[t] for t in TIERS if t != "not_evaluated")
    decided = answers["strong"] + answers["likely"] + answers["absent"]
    umbrellas = {}
    for broad, specific in UMBRELLAS.items():
        broad_yes = [r for r in finished if present(r["tags"].get(broad))]
        any_specific = [r for r in finished if any(present(r["tags"].get(s)) for s in specific)]
        umbrellas[broad] = {
            "label": by_id[broad].label,
            "specific_tags": specific,
            "broad_present": len(broad_yes),
            "any_specific_present": len(any_specific),
            "broad_present_without_any_specific": sum(
                not any(present(r["tags"].get(s)) for s in specific) for r in broad_yes
            ),
            "specific_present_without_broad": sum(
                not present(r["tags"].get(broad)) for r in any_specific
            ),
        }
    september = {}
    if SEPTEMBER.exists():
        for line in SEPTEMBER.read_text().splitlines():
            row = json.loads(line)
            if row.get("arm") == "rich" and row.get("list") == "mobile":
                september[row["game_id"]] = row
    v1_ids = [t.id for t in vocabulary.tags if t.category not in NEW_CATEGORIES]
    same, changed = 0, 0
    for r in finished:
        old = september.get(r["game_id"])
        if not old:
            continue
        for tid in v1_ids:
            if tid in old["tags"]:
                if present(old["tags"][tid]) == present(r["tags"].get(tid)):
                    same += 1
                else:
                    changed += 1

    def money(key: str) -> float:
        return round(sum(r.get("cost_usd", {}).get(key) or 0.0 for r in records), 4)

    return {
        "vocabulary_version": vocabulary.version,
        "games": len(records),
        "games_with_tags": len(finished),
        "status": dict(Counter(r.get("status") for r in records)),
        "evidence": {
            "games_with_video": sum(
                ((r.get("evidence") or {}).get("videos") or 0) > 0 for r in records
            ),
            "median_images": statistics.median(
                [(r.get("evidence") or {}).get("images") or 0 for r in records] or [0]
            ),
        },
        "new_tags": {
            "count": len(new),
            "answers": {tier: answers.get(tier, 0) for tier in TIERS},
            "asked": asked,
            "decided_share_of_asked": round(decided / asked, 3) if asked else None,
            "present_per_game_median": statistics.median(
                [sum(present(r["tags"].get(t.id)) for t in new) for r in finished] or [0]
            ),
            "followups_asked_per_game_median": statistics.median(
                [r.get("followups_asked") or 0 for r in finished] or [0]
            ),
        },
        "per_tag": per_tag,
        "umbrella_tags": umbrellas,
        "v1_tags_vs_september": {
            "games_compared": sum(1 for r in finished if r["game_id"] in september),
            "same_present_or_not": same,
            "changed": changed,
            "note": "September used the same method on the store pages of that week.",
        },
        "cost_usd": {
            "jev_typesafe": money("typesafe"),
            "claude_api": money("anthropic"),
            "claude_on_plan_api_equivalent": money("anthropic_on_subscription_api_equivalent"),
        },
        "median_seconds_per_game": round(
            statistics.median([(r.get("wall_ms") or 0) / 1000 for r in records] or [0]), 1
        ),
    }


def main() -> None:
    from gametagger.genome.vocabulary import default_vocabulary_path, load_vocabulary
    from gametagger.taxonomy import load_taxonomy

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workdir", type=Path, default=Path("benchmark-runs/mobile-retag-v2"))
    parser.add_argument("--out", type=Path, default=HERE)
    args = parser.parse_args()
    vocabulary = load_vocabulary(load_taxonomy(), default_vocabulary_path("v2"))
    records = load(args.workdir)
    if not records:
        raise SystemExit(f"No mobile results in {args.workdir}/results")
    summary = summarize(records, vocabulary)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    compact = [{k: v for k, v in r.items() if k != "warnings"} for r in records]
    (args.out / "per-game.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in compact)
    )
    new = summary["new_tags"]
    print(
        f"{summary['games_with_tags']} of {summary['games']} games tagged. New tags: "
        f"{new['decided_share_of_asked']:.0%} of questions asked were decided; median "
        f"{new['present_per_game_median']} present per game. "
        f"Jev ${summary['cost_usd']['jev_typesafe']:.2f}; "
        f"Claude on the plan (API equivalent) "
        f"${summary['cost_usd']['claude_on_plan_api_equivalent']:.2f}."
    )


if __name__ == "__main__":
    main()
