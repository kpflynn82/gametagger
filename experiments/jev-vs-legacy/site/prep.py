"""Build data.json for the benchmark pages: headline figures, per-game rows, the Haiku
readability check (needs the git-ignored raw responses in benchmark-runs/) and the tag glossary.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments/jev-vs-legacy/linkedin"))
from build import figures  # noqa: E402

from gametagger.comparison.crosswalk import load_crosswalks  # noqa: E402
from gametagger.comparison.scoring import normalize, steam_positives  # noqa: E402
from gametagger.genome.vocabulary import load_vocabulary  # noqa: E402
from gametagger.taxonomy import load_taxonomy  # noqa: E402

EXP = ROOT / "experiments/jev-vs-legacy"
taxonomy = load_taxonomy()
vocabulary = load_vocabulary(taxonomy)
cw = load_crosswalks(taxonomy, vocabulary)
names = {g.id: g.display_name for g in taxonomy.genres_by_id.values()}
summary = json.loads((EXP / "results/summary.json").read_text())
cohort = json.loads((EXP / "cohort.json").read_text())
key = json.loads((EXP / "answer-key-steam-tags.json").read_text())["games"]
records = {}
for line in (EXP / "results/per-game.jsonl").read_text().splitlines():
    r = json.loads(line)
    records[(r["game_id"], r["arm"])] = r

games = []
for g in cohort["games"]:
    row = {"id": g["game_id"], "title": g["title"], "list": g["list"], "rank": g["rank"]}
    entry = key.get(g["game_id"])
    positives = steam_positives(entry, cw)[0] if entry and entry.get("status") == "ok" else None
    for arm in ("rich", "legacy-deep", "legacy-standard"):
        r = records.get((g["game_id"], arm))
        if not r:
            row[arm] = None
            continue
        p = normalize(r, cw, names)
        recall = len(positives & p.present) / len(positives) if positives else None
        row[arm] = {
            "status": r["status"],
            "genre": p.genre_label,
            "p": r.get("primary_genre_probability"),
            "present": len(p.present),
            "recall": recall,
            "cost": r["cost_usd"]["total"],
            "sec": r["wall_ms"] / 1000,
        }
    # Library detail: every decided attribute, the genre distribution, what the old method said,
    # and the game's top Steam player tags. Third-party store text is never included.
    rich = records.get((g["game_id"], "rich")) or {}
    detail = {
        "developers": g.get("developers") or [],
        "jev": {
            t: [v["tier"], v.get("p_present")]
            for t, v in (rich.get("tags") or {}).items()
            if v["tier"] in ("strong", "likely", "absent", "conflicting")
        },
        "genres": [[gid, p] for gid, p in rich.get("top_genres") or [] if p and p >= 0.01],
        "secondary": rich.get("secondary_genres") or [],
        "steam": [t["name"] for t in (entry or {}).get("tags") or [] if t["rank"] <= 20],
    }
    for arm in ("legacy-deep", "legacy-standard"):
        r = records.get((g["game_id"], arm))
        if not r:
            continue
        mapped = sorted(normalize(r, cw, names).present)
        unmapped = sorted(
            k
            for k, v in (r.get("tags") or {}).items()
            if v is True and not cw.legacy_tag_target(k)[0]
        )
        detail[arm] = {
            "present": mapped,
            "unmapped": unmapped,
            "genre": r.get("primary_genre"),
            "secondary": r.get("secondary_genres") or [],
            "unreadable": r["status"] == "valid" and not r.get("tags"),
        }
    row["detail"] = detail
    games.append(row)

# Sensitivity: the original parser only unpacks nested groups named "*_tags". How many old
# answers did it read as empty, and what would recall be if every nested group were unpacked?
from gametagger.decisions.legacy import boolean_tags, parse_response  # noqa: E402


def flatten_all(d):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten_all(v))
        else:
            out[k] = v
    return out


RAW = ROOT / "benchmark-runs/jev-vs-legacy/raw"
sensitivity = {}
for arm in ("legacy-deep", "legacy-standard"):
    unreadable, hit_f, hit_r, pos = 0, 0, 0, 0
    answered = 0
    for g in cohort["games"]:
        r = records.get((g["game_id"], arm))
        raw_path = RAW / g["game_id"] / f"{arm}.json"
        if not r or not raw_path.exists():
            continue
        raw = json.loads(raw_path.read_text())
        if r["status"] == "valid":
            answered += 1
            if (raw.get("audit") or {}).get("true_tag_count") == 0:
                unreadable += 1
        entry = key.get(g["game_id"])
        if not (entry and entry.get("status") == "ok"):
            continue
        positives = steam_positives(entry, cw)[0]
        if not positives:
            continue
        faithful = normalize(r, cw, names).present
        parsed = parse_response(raw.get("raw_text") or "")
        readable = normalize({**r, "tags": boolean_tags(flatten_all(parsed))}, cw, names).present
        pos += len(positives)
        hit_f += len(positives & faithful)
        hit_r += len(positives & readable)
    sensitivity[arm] = {
        "answered": answered,
        "unreadable": unreadable,
        "recall_faithful": hit_f / pos if pos else None,
        "recall_if_readable": hit_r / pos if pos else None,
    }
print(json.dumps(sensitivity, indent=1))
f = figures(summary)
f["sensitivity"] = sensitivity
import yaml  # noqa: E402

CW = ROOT / "taxonomy/crosswalks"
legacy_tags = yaml.safe_load((CW / "legacy_tags_to_genome.yaml").read_text())["tags"]
steam_map = yaml.safe_load((CW / "steam_tags_to_genome.yaml").read_text())["tags"]
legacy_genres = yaml.safe_load((CW / "legacy59_to_v4.yaml").read_text())["genres"]
EVIDENCE = {
    "gameplay_image": "screenshots",
    "gameplay_clip": "trailer clips",
    "store_description": "store text",
    "developer_documentation": "developer text",
    "encyclopedia": "Wikipedia",
    "metadata": "store fields",
    "wikipedia": "Wikipedia",
    "store_metadata": "store fields",
}
old_for, steam_for, oldg_for = {}, {}, {}
for key, v in legacy_tags.items():
    if v and v.get("genome"):
        old_for.setdefault(v["genome"], []).append(
            key + (" (close)" if v.get("relation") == "close" else "")
        )
for name, v in steam_map.items():
    for tid in (v or {}).get("genome") or []:
        steam_for.setdefault(tid, []).append(name)
for name, v in legacy_genres.items():
    for gid in (v or {}).get("v4") or []:
        oldg_for.setdefault(gid, []).append(name)
glossary = {
    "version": vocabulary.version,
    "categories": [
        {"id": c.id, "label": c.label, "description": c.description} for c in vocabulary.categories
    ],
    "tags": [
        {
            "id": tg.id,
            "label": tg.label,
            "category": tg.category,
            "definition": tg.definition,
            "evidence": [EVIDENCE.get(e, e.replace("_", " ")) for e in tg.allowed_evidence],
            "old": old_for.get(tg.id, []),
            "steam": steam_for.get(tg.id, []),
        }
        for tg in (*vocabulary.pilot_tags, *vocabulary.extended_tags)
    ],
    "old_unmapped": sorted(k for k, v in legacy_tags.items() if not (v or {}).get("genome")),
    "families": {fid: fam.display_name for fid, fam in taxonomy.families_by_id.items()},
    "genres": [
        {
            "id": g.id,
            "name": g.display_name,
            "family": g.family,
            "definition": g.definition,
            "old": oldg_for.get(g.id, []),
            "examples": list(g.example_games),
        }
        for g in taxonomy.genres_by_id.values()
    ],
}
print(len(glossary["tags"]), "tags,", len(glossary["genres"]), "genres")
out = {"figures": f, "games": games, "measured": summary["measured"], "glossary": glossary}
Path(sys.argv[1]).write_text(json.dumps(out, separators=(",", ":"), default=str))
print(len(games), "games")
