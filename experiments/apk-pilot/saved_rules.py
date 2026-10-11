"""Live rules and downloaded content from MONOPOLY GO!'s saved data on the emulator.

    uv run python experiments/apk-pilot/saved_rules.py \
        benchmark-runs/apk-pilot/com.scopely.monopolygo/saved-data \
        experiments/apk-pilot/results/monopoly-go-saved-rules.json

The folder holds what ``mac/copy-saved-data.command`` copied from the game's shared-storage folder
(``/sdcard/Android/data/<package>``): ``files.txt`` (every file's size and path) and the small files
next to it. Three of them carry facts about how the live game is run:

* the in-app message list (Scopely's SDK): each pop-up's targeting rule, such as
  ``User:net_worth >= 15``, where it shows, how often, and any gift it carries;
* the cached remote settings: on/off switches and numbers only (strings can hold keys or IDs and
  are skipped);
* the names of the downloaded content bundles, which show which features this player has loaded.

Only derived facts are written. Player IDs, keys, URLs and the files themselves stay out.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

PERIOD = {"TOTAL": "ever", "SESSION": "session", "MINUTE": "min", "DAY": "day", "WEEK": "week"}


def day(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d") if ts else None


def caps(options: list[dict], operator: str) -> str:
    parts = []
    for o in options:
        unit, n = o["unit"], o["period"]
        if unit == "TOTAL":
            parts.append(f"{o['impressions']} ever")
        else:
            parts.append(f"{o['impressions']} per {n} {PERIOD.get(unit, unit.lower())}")
    return f" {operator.lower()} ".join(parts)


def messages(path: Path) -> list[dict]:
    out = []
    for m in json.loads(path.read_text())["messages"]:
        props = m.get("properties") or {}
        out.append(
            {
                "name": m["name"],
                "kind": m["templateId"],
                "shows_at": m["placements"],
                "rule": m.get("rules") or None,
                "cap": caps(m.get("freqOptions") or [], m.get("freqOperator") or "AND"),
                "runs": [day(m.get("startDate")), day(m.get("endDate"))],
                "about": props.get("ref_type") or props.get("trigger_key"),
                "gift": props.get("ad_hoc_iam_rewards"),
            }
        )
    return out


def number_or_switch(value):
    """The value if it is an on/off switch, a number or a list of numbers; else None."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if isinstance(value, dict):
        return {"enabled": value["enabled"]} if isinstance(value.get("enabled"), bool) else None
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, list) and value and all(isinstance(v, int | float) for v in value):
        return value
    return None


def settings(path: Path) -> dict:
    out: dict[str, dict] = {}
    for group, body in json.loads(path.read_text()).items():
        for p in body.get("properties") or []:
            if p["key"].endswith("_id"):
                continue
            value = number_or_switch(p.get("value"))
            if value is not None:
                out.setdefault(group, {"updated": body.get("timestamp", "")[:10]})[p["key"]] = value
    return out


def bundles(files: Path) -> dict:
    sizes: Counter[str] = Counter()
    for line in files.read_text().splitlines():
        size, path = line.split(" ", 1)
        m = re.search(r"/UnityCache/Shared/([^/]+)/", path)
        if m:
            name = re.sub(r"-(all|localizedui\.[a-z-]+)$", "", m.group(1))
            sizes[name] += int(size)
    families = Counter(n.split("-")[0] for n in sizes)
    dlc = Counter(n.split("-")[1] for n in sizes if n.startswith("dlc-"))
    return {
        "bundles": len(sizes),
        "megabytes": round(sum(sizes.values()) / 1e6),
        "by_family": dict(families.most_common()),
        "dlc_by_kind": dict(dlc.most_common()),
        "feature_bundles": sorted(
            n[len("features-") :] for n in sizes if n.startswith("features-")
        ),
    }


def main() -> None:
    folder, out = Path(sys.argv[1]), Path(sys.argv[2])
    found = {p.name: p for p in folder.rglob("*") if p.is_file()}
    result = {
        "game": "MONOPOLY GO!",
        "source": "shared-storage app folder on the Android 17 emulator after the teardown run",
        "in_app_messages": messages(found["InAppMessagesContent"]),
        "remote_settings": settings(found["dynamic_remote_config_cache.json"]),
        "downloaded_content": bundles(found["files.txt"]),
        "notes": [
            "Rules are the live targeting rules this player's copy held on 2026-10-10.",
            "Remote settings keep switches and numbers only; strings, keys and IDs are left out.",
        ],
    }
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(f"{len(result['in_app_messages'])} messages; settings {list(result['remote_settings'])}")
    for m in result["in_app_messages"]:
        print(f"  {m['name']}: {m['rule']} [{m['cap']}]")


if __name__ == "__main__":
    main()
