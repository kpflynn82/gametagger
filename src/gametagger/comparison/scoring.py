"""Score the compared methods: speed, tokens, cost, output volume and accuracy.

Answer keys and what each can measure:
* Steam user tags (games with a Steam listing): a tag among a game's most-voted tags is evidence
  the mapped attribute is present. That measures *recall* (share of player-confirmed attributes
  a method reported present) and *contradiction* (share it explicitly called absent). It cannot
  measure precision, because a missing Steam tag is not evidence of absence.
* The owner's blinded review (optional): verdicts on sampled proposed tags and genres measure
  *precision* and primary-genre correctness.
Old-method outputs are compared in the Genome vocabulary through the draft crosswalks; a head-to-
head restricted to attributes both vocabularies can express is always reported alongside.
"""

from __future__ import annotations

import csv
import json
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gametagger.comparison.crosswalk import Crosswalks
from gametagger.comparison.dossiers import safe_id

ARM_LABELS = {
    "rich": "Jev rich mode",
    "legacy-standard": "Old method, Haiku 4.5",
    "legacy-deep": "Old method, Opus 4.8",
}
FAILED = {"failed", "provider_error", "parse_error", "not_evaluated"}


@dataclass
class Prediction:
    """One arm's output for one game, in the Genome and v4 vocabularies."""

    status: str
    present: set[str] = field(default_factory=set)
    absent: set[str] = field(default_factory=set)
    raw_positive_count: int = 0
    genre_v4: list[str] = field(default_factory=list)  # exact or compatible v4 genres
    genre_relation: str = "missing"
    genre_families: list[str] = field(default_factory=list)
    genre_label: str | None = None
    forced_genre: bool = False


def normalize(record: dict, crosswalks: Crosswalks, taxonomy_names: dict[str, str]) -> Prediction:
    status = record.get("status", "failed")
    if record["arm"] == "rich":
        tags = record.get("tags") or {}
        present = {t for t, v in tags.items() if v["tier"] in ("strong", "likely")}
        absent = {t for t, v in tags.items() if v["tier"] == "absent"}
        genre = record.get("primary_genre")
        return Prediction(
            status=status,
            present=present,
            absent=absent,
            raw_positive_count=len(present),
            genre_v4=[genre] if genre else [],
            genre_relation="exact" if genre else "missing",
            genre_families=[crosswalks.family_of[genre]] if genre else [],
            genre_label=taxonomy_names.get(genre) if genre else None,
        )
    tags = record.get("tags") or {}
    present, absent = set(), set()
    for key, value in tags.items():
        target, relation = crosswalks.legacy_tag_target(key)
        if target and relation in ("exact", "close"):
            (present if value is True else absent).add(target)
    absent -= present  # a key answered both ways through two old keys stays positive
    label = record.get("primary_genre")
    targets = crosswalks.legacy_genre_targets(label)
    return Prediction(
        status=status,
        present=present,
        absent=absent,
        raw_positive_count=sum(1 for v in tags.values() if v is True),
        genre_v4=targets["v4"],
        genre_relation=targets["relation"] if label else "missing",
        genre_families=targets["families"],
        genre_label=label,
        forced_genre=record.get("primary_genre_resolution") == "forced_fallback",
    )


def steam_positives(entry: dict, crosswalks: Crosswalks, top: int = 20):
    """Genome tags and v4 genres implied by a game's top-voted Steam user tags."""
    tags, genres = set(), set()
    for tag in entry.get("tags") or []:
        if tag["rank"] > top:
            continue
        target = crosswalks.steam_targets(tag["name"])
        if target:
            tags.update(target["genome"])
            genres.update(target["genres"])
    return tags, genres


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[index]


def _dist(values: list[float]) -> dict[str, Any]:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "p90": _pct(values, 0.9),
        "p95": _pct(values, 0.95),
        "min": min(values),
        "max": max(values),
    }


def bootstrap_diff(pairs: list[tuple[float, float, float, float]], *, seed: int = 20260924):
    """95% interval for (hits_a/total_a - hits_b/total_b), resampling games (paired)."""
    if not pairs:
        return None
    rng = random.Random(seed)

    def ratio(rows, i):
        total = sum(r[i + 1] for r in rows)
        return sum(r[i] for r in rows) / total if total else 0.0

    diffs = []
    for _ in range(2000):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        diffs.append(ratio(sample, 0) - ratio(sample, 2))
    diffs.sort()
    return {"low": diffs[int(0.025 * len(diffs))], "high": diffs[int(0.975 * len(diffs)) - 1]}


def load_results(workdir: Path, cohort: dict, arms: list[str]) -> dict[str, dict[str, dict]]:
    results: dict[str, dict[str, dict]] = {arm: {} for arm in arms}
    for game in cohort["games"]:
        for arm in arms:
            path = workdir / "results" / safe_id(game["game_id"]) / f"{arm}.json"
            if path.exists():
                results[arm][game["game_id"]] = json.loads(path.read_text())
    return results


def score(
    cohort: dict,
    answer_key: dict | None,
    results: dict[str, dict[str, dict]],
    crosswalks: Crosswalks,
    taxonomy_names: dict[str, str],
    *,
    review: dict | None = None,
    top_steam_tags: int = 20,
) -> dict[str, Any]:
    arms = [a for a in results if results[a]]
    # Only games every arm finished (or failed) are compared, so arms see the same sample.
    common = [g for g in cohort["games"] if all(g["game_id"] in results[a] for a in arms)]
    shared_vocab = {
        e["genome"] for e in crosswalks.legacy_tags.values() if e.get("relation") != "none"
    }
    preds = {
        a: {
            g["game_id"]: normalize(results[a][g["game_id"]], crosswalks, taxonomy_names)
            for g in common
        }
        for a in arms
    }
    out: dict[str, Any] = {
        "sample": {
            "games_compared": len(common),
            "steam_games": sum(g["list"] == "steam" for g in common),
            "mobile_games": sum(g["list"] == "mobile" for g in common),
            "chart_dates": {k: v["chart_date"] for k, v in cohort["charts"].items()},
        },
        "crosswalks": crosswalks.versions,
        "arms": {},
    }
    key_games = (answer_key or {}).get("games") or {}
    steam_sets = {
        gid: steam_positives(entry, crosswalks, top_steam_tags)
        for gid, entry in key_games.items()
        if entry.get("status") == "ok"
    }
    keyed = [g["game_id"] for g in common if steam_sets.get(g["game_id"], (set(), set()))[0]]
    out["sample"]["games_with_steam_answer_key"] = len(keyed)
    for arm in arms:
        records = [results[arm][g["game_id"]] for g in common]
        p = preds[arm]
        ok = [r for r in records if r.get("status") not in FAILED]
        stage_keys = sorted({k for r in ok for k in (r.get("stage_ms") or {})})
        arm_out: dict[str, Any] = {
            "label": ARM_LABELS.get(arm, arm),
            "games": len(records),
            "completed": len(ok),
            "retried_after_provider_errors": sum(1 for r in records if r.get("attempt", 1) > 1),
            "provider_errors_in_final_results": sum(
                1 for r in records for c in r.get("requests") or [] if c.get("status") == "error"
            ),
            "failure_rate": 1 - len(ok) / len(records) if records else None,
            "latency_ms": {
                "method": _dist([r.get("wall_ms") for r in ok]),
                "with_evidence_gathering": _dist(
                    [(r.get("wall_ms") or 0) + (r.get("evidence_gather_ms") or 0) for r in ok]
                ),
                "stages": {
                    k: _dist([(r.get("stage_ms") or {}).get(k) for r in ok]) for k in stage_keys
                },
            },
            "tokens": {
                provider: {
                    kind: _dist([r["usage"][provider][kind] for r in records if "usage" in r])
                    for kind in ("input_tokens", "output_tokens", "requests")
                }
                for provider in ("anthropic", "typesafe")
            },
            "cost_usd": {
                "total": sum(r.get("cost_usd", {}).get("total", 0.0) for r in records),
                "per_game": _dist([r.get("cost_usd", {}).get("total") for r in records]),
                "anthropic_total": sum(
                    r.get("cost_usd", {}).get("anthropic", 0.0) for r in records
                ),
                "typesafe_total": sum(r.get("cost_usd", {}).get("typesafe", 0.0) for r in records),
            },
            "tags_per_game": {
                "positive_in_genome_vocabulary": _dist(
                    [
                        len(p[g["game_id"]].present)
                        for g in common
                        if p[g["game_id"]].status not in FAILED
                    ]
                ),
                "positive_raw": _dist(
                    [
                        p[g["game_id"]].raw_positive_count
                        for g in common
                        if p[g["game_id"]].status not in FAILED
                    ]
                ),
            },
            "genre": {
                "with_primary_genre": sum(1 for x in p.values() if x.genre_label),
                "forced_fallback": sum(1 for x in p.values() if x.forced_genre),
                "relations": {
                    rel: sum(1 for x in p.values() if x.genre_relation == rel)
                    for rel in ("exact", "one_of", "family", "none", "unmapped", "missing")
                },
            },
        }
        if arm == "rich":
            tiers: dict[str, list[int]] = {}
            for r in ok:
                for tier, n in (r.get("counts") or {}).items():
                    tiers.setdefault(tier, []).append(n)
            arm_out["rich_tiers_per_game"] = {t: _dist(v) for t, v in tiers.items()}
        # Recall and contradiction against Steam user tags.
        for scope, limit in (("all_mapped", None), ("shared_vocabulary", shared_vocab)):
            hits = total = contradicted = 0
            per_game = []
            for gid in keyed:
                positives = steam_sets[gid][0]
                if limit is not None:
                    positives = positives & limit
                if not positives:
                    continue
                found = len(positives & p[gid].present)
                said_no = len(positives & p[gid].absent)
                hits, total, contradicted = (
                    hits + found,
                    total + len(positives),
                    contradicted + said_no,
                )
                per_game.append(found / len(positives))
            arm_out.setdefault("steam_tags", {})[scope] = {
                "games": len(per_game),
                "attributes": total,
                "recall_pooled": hits / total if total else None,
                "recall_mean_per_game": statistics.fmean(per_game) if per_game else None,
                "contradiction_rate": contradicted / total if total else None,
            }
        consistent = family = considered = 0
        for gid in keyed:
            steam_genres = steam_sets[gid][1]
            if not steam_genres or not p[gid].genre_label:
                continue
            considered += 1
            consistent += bool(set(p[gid].genre_v4) & steam_genres)
            steam_families = {crosswalks.family_of[g] for g in steam_genres}
            family += bool(set(p[gid].genre_families) & steam_families)
        arm_out["genre_vs_steam_tags"] = {
            "games": considered,
            "consistent_genre": consistent / considered if considered else None,
            "consistent_family": family / considered if considered else None,
            "note": "Weak signal: Steam tags list many genres a game touches, not its primary one.",
        }
        out["arms"][arm] = arm_out
    # Paired recall differences with bootstrap intervals, rich versus each old arm.
    if "rich" in arms:
        for other in [a for a in arms if a != "rich"]:
            for scope, limit in (("all_mapped", None), ("shared_vocabulary", shared_vocab)):
                pairs = []
                for gid in keyed:
                    positives = steam_sets[gid][0] if limit is None else steam_sets[gid][0] & limit
                    if positives:
                        pairs.append(
                            (
                                len(positives & preds["rich"][gid].present),
                                len(positives),
                                len(positives & preds[other][gid].present),
                                len(positives),
                            )
                        )
                rich = out["arms"]["rich"]["steam_tags"][scope]["recall_pooled"]
                old = out["arms"][other]["steam_tags"][scope]["recall_pooled"]
                out.setdefault("recall_difference_vs_rich", {}).setdefault(other, {})[scope] = {
                    "rich_minus_old_points": (rich - old) * 100
                    if None not in (rich, old)
                    else None,
                    "ci95_points": (
                        {k: v * 100 for k, v in ci.items()}
                        if (ci := bootstrap_diff(pairs))
                        else None
                    ),
                    "games": len(pairs),
                }
    if review:
        out["owner_review"] = score_review(review)
    return out


# --------------------------------------------------------------------------- owner review

VERDICTS = {"yes": True, "y": True, "correct": True, "no": False, "n": False, "wrong": False}


def read_review(csv_path: Path, key_path: Path) -> dict:
    key = json.loads(key_path.read_text())
    verdicts = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            verdict = VERDICTS.get((row.get("your_verdict") or "").strip().lower())
            if verdict is not None:
                verdicts[row["item"]] = verdict
    return {"key": key, "verdicts": verdicts}


def score_review(review: dict) -> dict[str, Any]:
    by_arm: dict[str, dict[str, dict[str, int]]] = {}
    for item, info in review["key"]["items"].items():
        verdict = review["verdicts"].get(item)
        if verdict is None:
            continue
        for arm in info["arms"]:
            bucket = by_arm.setdefault(arm, {}).setdefault(info["kind"], {"yes": 0, "no": 0})
            bucket["yes" if verdict else "no"] += 1
    return {
        arm: {
            kind: {**counts, "precision": counts["yes"] / (counts["yes"] + counts["no"])}
            for kind, counts in kinds.items()
        }
        for arm, kinds in by_arm.items()
    }
