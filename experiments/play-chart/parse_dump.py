"""Turn the emulator's saved Play Store screens into one chart file.

    uv run python experiments/play-chart/parse_dump.py benchmark-runs/play-chart/20261009-1205

``scripts/mac/play-chart.sh`` saves each screenful of the Top grossing list as Android's
accessibility dump (``NN.xml``). In each dump a rank is a plain text node ("1", "2", ...) and the
next node with a multi-line description holds the game: title first, then Play's genre labels,
star rating and badges. The output is ``chart.json`` in the same folder. Package IDs are not on
screen, so they are matched later.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BADGES = {"Installed", "Event", "Editors' Choice", "Major Update", "New", "Pre-registration"}


def parse_dump(xml_text: str) -> dict[int, dict]:
    rows: dict[int, dict] = {}
    pending: int | None = None
    for node in ET.fromstring(xml_text).iter("node"):
        text = node.get("text") or ""
        desc = node.get("content-desc") or ""
        if text.isdigit() and not desc:
            pending = int(text)
            continue
        if pending is not None and "\n" in desc:
            parts = [p for p in desc.split("\n") if p]
            rating = next(
                (p.split(": ", 1)[1] for p in parts if p.startswith("Star rating: ")), None
            )
            rest = [p for p in parts[1:] if not p.startswith("Star rating")]
            badge = [p for p in rest if p in BADGES or p.startswith(("Ends ", "$"))]
            rows[pending] = {
                "rank": pending,
                "title": parts[0],
                "labels": [p for p in rest if p not in badge],
                "badges": badge,
                "rating": float(rating) if rating else None,
            }
            pending = None
    return rows


def parse_folder(folder: Path) -> dict:
    rows: dict[int, dict] = {}
    for path in sorted(folder.glob("*.xml")):
        for rank, row in parse_dump(path.read_text()).items():
            rows.setdefault(rank, row)
    ranks = sorted(rows)
    gaps = [r for r in range(1, ranks[-1] + 1) if r not in rows] if ranks else []
    log = folder / "log.txt"
    return {
        "source": "Google Play app on the Android emulator: Games > Top charts > Top grossing",
        "folder": folder.name,
        "device": log.read_text().splitlines()[:8] if log.exists() else [],
        "missing_ranks": gaps,
        "rows": [rows[r] for r in ranks],
    }


def main() -> None:
    folder = Path(sys.argv[1])
    chart = parse_folder(folder)
    (folder / "chart.json").write_text(json.dumps(chart, indent=1, ensure_ascii=False))
    print(f"{len(chart['rows'])} ranked games; missing ranks: {chart['missing_ranks'] or 'none'}")


if __name__ == "__main__":
    main()
