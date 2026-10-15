"""Current 'what's hot' keywords for the trend-fit signal.

In a scheduled run these come from the weekly mobile digest (the model reads the newest digest and
emits a ``{term: weight}`` map). This module ships a small, dated default drawn from the digest's
own knowledge base so the radar still works when run by hand without a fresh digest. Weights are
0..1; terms are lowercase substrings matched against a candidate's title, store hints and genre.
"""

from __future__ import annotations

import json
from pathlib import Path

# Dated default -- replace from the live digest. Grounded in the project's research doc:
# hybrid-casual growth, collection albums as the hottest 2025-26 retention feature, merge,
# social/alliance competition, season passes.
DEFAULT_HOT_TERMS: dict[str, float] = {
    "hybrid-casual": 0.9,
    "merge": 0.85,
    "collection album": 0.9,
    "collection": 0.7,
    "social tournament": 0.8,
    "alliance": 0.7,
    "gacha": 0.6,
    "season pass": 0.6,
    "idle": 0.6,
    "roguelike": 0.55,
    "cozy": 0.5,
    "sort": 0.6,
}
DEFAULT_AS_OF = "2026-07-22 digest knowledge base (replace with the latest digest)"


def load_hot_terms(path: Path | None = None) -> dict[str, float]:
    if path and path.exists():
        data = json.loads(path.read_text())
        # Accept either {term: weight} or {"terms": {term: weight}, "as_of": ...}.
        terms = data.get("terms", data) if isinstance(data, dict) else {}
        return {str(k).lower(): float(v) for k, v in terms.items()}
    return dict(DEFAULT_HOT_TERMS)
