"""What Candy Crush Saga introduces when, from the level data inside its APK.

    uv run python experiments/apk-pilot/candy_crush_levels.py \
        benchmark-runs/apk-pilot/com.king.candycrushsaga

The base APK ships every level: ``assets/res_output/bundled/ccsm_levels/assets/levels_batched/
levels_batched.db`` (SQLite, one JSON record per level) and ``.../levels.xml`` (King's binary
"BIN1" index with each level's hard-level label). Writes ``levels-summary.json`` next to the APK.
Only derived facts leave this script: first levels, counts and averages, never the level designs.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

DB = "assets/res_output/bundled/ccsm_levels/assets/levels_batched/levels_batched.db"
INDEX = "assets/res_output/bundled/ccsm_levels/assets/levels.xml"
BANDS = [
    (1, 20),
    (21, 50),
    (51, 100),
    (101, 200),
    (201, 500),
    (501, 1000),
    (1001, 2000),
    (2001, 5000),
    (5001, 10000),
    (10001, 15000),
    (15001, 20000),
    (20001, 25000),
]
# Level settings that only name a quantity, not a mechanic.
NOT_MECHANICS = {
    "protocolVersion",
    "numberOfColours",
    "preferredColors",
    "boardRows",
    "boardColumns",
    "randomSeed",
    "qa",
    "scoreTargets",
    "moveLimit",
    "gameModeName",
    "levelType",
    "tileMap",
    "levelDefinitionId_meta",
    "version_meta",
    "id_meta",
    "episodeId",
    "levelId",
    "name",
    "disablePreLevelBoosters",
    "tileGroups",
    "_itemsToOrder",
}


def used(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value not in (0, -1)
    return bool(value)


def hard_labels(index: bytes) -> list[int]:
    """Each level's hard-level label (0 = normal, 1-4 = harder tiers), in level order."""
    labels = []
    for record in re.split(rb"\x00\x00\x00+", index[4:])[1:]:
        parts = record.strip(b"\x00").split(b"\x00")
        if parts and parts[0] == b"Level":
            fields = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
            labels.append(int(fields.get(b"hll", b"0")))
    return labels


def band_of(level: int) -> str:
    return next(f"{a}-{b}" for a, b in BANDS if a <= level <= b)


def summarize(apk: Path) -> dict:
    with zipfile.ZipFile(apk) as z, tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "levels.db"
        db.write_bytes(z.read(DB))
        labels = hard_labels(z.read(INDEX))
        rows = (
            sqlite3.connect(db)
            .execute("select level_data from batched_levels order by ordinal")
            .fetchall()
        )
        levels = [json.loads(r[0]) for r in rows]

    first = {"game_mode": {}, "level_tag": {}, "setting": {}, "board_element": {}, "order_item": {}}
    count = {k: Counter() for k in first}
    band = defaultdict(lambda: defaultdict(list))
    for i, d in enumerate(levels):
        lv = d["id_meta"]
        seen = {
            "game_mode": {d.get("gameModeName")},
            "level_tag": set(d.get("levelType") or []),
            "setting": {k for k, v in d.items() if k not in NOT_MECHANICS and used(v)},
            "board_element": {
                cell[j : j + 3]
                for row in d.get("tileMap") or []
                for cell in row
                for j in range(0, len(cell), 3)
            },
            "order_item": {str(o["item"]) for o in d.get("_itemsToOrder") or []},
        }
        b = band[band_of(lv)]
        for kind, items in seen.items():
            for item in items:
                if item is None:
                    continue
                if item not in first[kind]:
                    first[kind][item] = lv
                    b["new_" + kind].append(item)
                count[kind][item] += 1
        b["moves"].append(d.get("moveLimit") or 0)
        b["colours"].append(d.get("numberOfColours") or 0)
        b["hard"].append(labels[i] if i < len(labels) else 0)
        b["mode"].append(d.get("gameModeName"))

    bands = []
    for a, z in BANDS:
        b = band.get(f"{a}-{z}")
        if not b:
            continue
        n = len(b["moves"])
        bands.append(
            {
                "levels": f"{a}-{z}",
                "count": n,
                "new_board_elements": len(b["new_board_element"]),
                "new_settings": sorted(b["new_setting"], key=lambda s: first["setting"][s]),
                "new_modes": b["new_game_mode"],
                "new_tags": b["new_level_tag"],
                "median_moves": statistics.median(b["moves"]),
                "mean_colours": round(statistics.mean(b["colours"]), 2),
                "hard_share": round(sum(1 for h in b["hard"] if h > 0) / n, 3),
                "top_tier_share": round(sum(1 for h in b["hard"] if h >= 4) / n, 3),
                "modes": dict(Counter(b["mode"]).most_common()),
            }
        )
    first_hard = {
        t: next((i + 1 for i, h in enumerate(labels) if h == t), None) for t in (1, 2, 3, 4)
    }
    return {
        "game": "Candy Crush Saga",
        "levels": len(levels),
        "first_level_with": {
            k: dict(sorted(v.items(), key=lambda x: x[1])) for k, v in first.items()
        },
        "levels_using": {k: dict(v.most_common()) for k, v in count.items()},
        "first_hard_label": first_hard,
        "bands": bands,
        "notes": [
            "Board elements and order items are King's numeric codes; the APK does not name them.",
            "A setting counts from the first level where it has a non-zero value.",
            "hard labels: 0 normal, 1-4 the game's harder tiers (its map pins name them).",
        ],
    }


def main() -> None:
    folder = Path(sys.argv[1])
    out = summarize(folder / "base.apk")
    (folder / "levels-summary.json").write_text(json.dumps(out, indent=1))
    print(f"{out['levels']} levels; first hard labels {out['first_hard_label']}")
    for b in out["bands"]:
        print(
            f"{b['levels']:>12}: {b['new_board_elements']:>3} new elements, "
            f"moves {b['median_moves']:>4}, colours {b['mean_colours']}, hard {b['hard_share']:.0%}"
            f"; new: {', '.join(b['new_modes'] + b['new_tags'] + b['new_settings'])[:150]}"
        )


if __name__ == "__main__":
    main()
