"""Load GameTagger's existing tagged catalogue, so the radar knows what is already known.

The catalogue is the set of US top grossers already tagged in the ``mobile-top100`` and
``mobile-retag-v2`` experiments. Their ``game_id``s tell the novelty signal "we have seen this
one", and their genomes let the trend-fit signal read a real genre instead of guessing from a
title. This reads only committed, derived tag records -- never game media.
"""

from __future__ import annotations

import json
from pathlib import Path

# Newest first; a game tagged more than once keeps its first (newest) record here.
DEFAULT_SOURCES = (
    Path("experiments/mobile-top100/new-run/per-game.jsonl"),
    Path("experiments/mobile-retag-v2/per-game.jsonl"),
)


def load_catalogue(
    root: Path | None = None, sources: tuple[Path, ...] = DEFAULT_SOURCES
) -> dict[str, dict]:
    """Map ``game_id`` -> its tagged record, for every game already in the catalogue."""

    root = root or Path.cwd()
    catalogue: dict[str, dict] = {}
    for rel in sources:
        path = root / rel
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            gid = rec.get("game_id")
            if gid and rec.get("arm") == "rich" and gid not in catalogue:
                catalogue[gid] = rec
    return catalogue
