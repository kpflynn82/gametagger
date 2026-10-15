"""Turn the weekly mobile digest into the radar's trend map.

The weekly digest task writes ``trend-digest-YYYY-MM-DD.md`` -- cited prose about what is working in
casual and midcore mobile games this week. The radar's trend-fit signal needs a ``{term: weight}``
map instead. This reads the newest digest and scores a fixed vocabulary of mobile-game mechanics and
genres by how much the digest talks about each, so the wire works **deterministically with no model
call**. A scheduled run may still replace the map with a richer model extraction from the same
digest; this is the dependable floor that keeps the radar honest when run by hand.

Why a fixed vocabulary rather than free keyword mining: it never invents a "trend" out of a stray
word, it stays aligned with the terms the signal layer already matches against, and it is testable.

    from gametagger.radar.digest import load_digest_terms
    hot = load_digest_terms("~/intel/digests")      # newest trend-digest-*.md in that folder
    hot = load_digest_terms("trend-digest-2026-10-14.md")   # or one named digest
"""

from __future__ import annotations

import re
from pathlib import Path

from gametagger.radar.trends import DEFAULT_HOT_TERMS

# Canonical term -> the surface spellings that count as a mention of it. Canonical terms match the
# keys the trend-fit signal looks for (see trends.py); aliases fold common variants onto them so
# "sticker album", "albums" and "collection album" all feed the same trend. Lowercase substrings.
DIGEST_VOCAB: dict[str, tuple[str, ...]] = {
    "hybrid-casual": ("hybrid-casual", "hybrid casual"),
    "merge": ("merge",),
    "collection album": ("collection album", "sticker album", "album event", "collection event"),
    "collection": ("collection",),
    "social tournament": (
        "social tournament",
        "social-tournament",
        "tournament",
        "guild event",
        "pvp ladder",
    ),
    "alliance": ("alliance", "guild", "clan", "co-op event", "team event"),
    "gacha": ("gacha", "summon", "pity"),
    "season pass": ("season pass", "battle pass", "event pass"),
    "idle": ("idle", "incremental"),
    "roguelike": ("roguelike", "roguelite"),
    "cozy": ("cozy", "cosy", "wholesome"),
    "sort": ("sort puzzle", "sorting", "water sort", "pin puzzle"),
    "decorating meta": ("decorat", "renovation", "home design", "makeover"),
    "narrative chapters": ("narrative", "story chapter", "story mode", "chapters"),
    "live events": ("live event", "live-ops", "liveops", "live ops", "limited-time event"),
}

# One mention -> a modest weight; it climbs with how much the week's digest dwells on the term, so a
# theme the digest returns to repeatedly outranks one it names once. Capped at 1.0.
_BASE = 0.4
_PER_MENTION = 0.1


def extract_hot_terms(text: str) -> dict[str, float]:
    """Score the digest's text into ``{canonical_term: weight}`` over the fixed vocabulary.

    A term is counted once per non-overlapping surface occurrence (word-boundary matched, so
    "merge" does not fire on "emergency"). Terms the digest never mentions are omitted, not zeroed,
    so the map stays small and the signal's "no trend detected" branch still works.
    """

    low = text.lower()
    terms: dict[str, float] = {}
    for canonical, surfaces in DIGEST_VOCAB.items():
        count = 0
        for surface in surfaces:
            # Left word boundary, no right one: "decorat" catches "decorating"/"decoration" and
            # "merge" catches "merged"/"merges", while neither fires inside another word.
            count += len(re.findall(rf"\b{re.escape(surface)}", low))
        if count:
            terms[canonical] = round(min(1.0, _BASE + _PER_MENTION * count), 3)
    return terms


_DIGEST_GLOB = "trend-digest-*.md"
_DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")


def newest_digest(folder: Path) -> Path | None:
    """The ``trend-digest-*.md`` with the latest date in its name, or None if there is none."""

    folder = Path(folder)
    if not folder.is_dir():
        return None
    dated: list[tuple[str, Path]] = []
    for path in folder.glob(_DIGEST_GLOB):
        m = _DATE_IN_NAME.search(path.name)
        dated.append(((m.group(1) if m else ""), path))
    if not dated:
        return None
    # ISO dates sort lexically; the name itself breaks ties so the choice is deterministic.
    return max(dated, key=lambda t: (t[0], t[1].name))[1]


def load_digest_terms(path: str | Path, *, floor: int = 1) -> dict[str, float]:
    """Hot-terms map from a digest file, or from the newest digest in a folder.

    ``floor`` is the fewest terms worth trusting; below it the digest was probably not a real
    digest (or parsing missed), and the caller should fall back to the built-in defaults. Returns
    an empty dict in that case so the caller can choose the fallback explicitly.
    """

    p = Path(path).expanduser()
    digest = newest_digest(p) if p.is_dir() else (p if p.is_file() else None)
    if digest is None:
        return {}
    terms = extract_hot_terms(digest.read_text(encoding="utf-8", errors="ignore"))
    return terms if len(terms) >= floor else {}


def digest_terms_or_default(path: str | Path | None) -> dict[str, float]:
    """Terms from the digest if a usable one is found, else the dated built-in defaults."""

    if path:
        terms = load_digest_terms(path)
        if terms:
            return terms
    return dict(DEFAULT_HOT_TERMS)
