"""Candidate games assembled from several regional charts.

A candidate is one game seen across one or more test-market charts. Each chart reading contributes
a region, a store, a chart kind (grossing or free) and a rank. ``merge_candidates`` folds every
reading of the same game (matched by store ID) into one candidate, so the signal layer can reason
about the whole picture: "top-30 grossing in Canada and Australia, nowhere in the free charts, and
not in our US catalogue."
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from gametagger.genome.sources import normal_title

Store = Literal["google_play", "app_store"]
ChartKind = Literal["grossing", "free"]
# The common mobile soft-launch test markets. Order is the reporting order.
TEST_MARKETS = ("CA", "AU", "NZ")


@dataclass(frozen=True)
class ChartEntry:
    """One game's placement on one regional chart reading."""

    region: str  # ISO country code, e.g. "CA"
    store: Store
    kind: ChartKind
    rank: int
    chart_size: int  # how many ranks that reading covered, so "absent" is meaningful


@dataclass
class RegionChart:
    """A single chart reading: every ranked row for one region/store/kind on one day."""

    region: str
    store: Store
    kind: ChartKind
    chart_date: str | None
    # store ID (package or App Store numeric id) -> (rank, title, developer)
    rows: dict[str, tuple[int, str, str | None]] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.rows)


@dataclass
class Candidate:
    """One game, with everything the radar knows about it before any teardown."""

    store: Store
    store_id: str  # package name or App Store numeric id
    title: str
    developer: str | None = None
    entries: list[ChartEntry] = field(default_factory=list)
    # Filled by the caller from the tagged catalogue, if the game is already known.
    known_genome: dict | None = None
    # Apparent genre/mechanic keywords for trend matching, from the store listing if gathered.
    hints: tuple[str, ...] = ()
    # The same game's IDs on other stores (store -> id), when merged across stores by title.
    alt_ids: dict[str, str] = field(default_factory=dict)

    @property
    def game_id(self) -> str:
        prefix = "gp" if self.store == "google_play" else "ios"
        return f"{prefix}-{self.store_id}"

    def best_rank(self, kind: ChartKind) -> ChartEntry | None:
        matching = [e for e in self.entries if e.kind == kind]
        return min(matching, key=lambda e: e.rank) if matching else None

    def regions(self, kind: ChartKind) -> list[str]:
        """Test markets, in reporting order, where the game is ranked on the given chart kind."""
        seen = {e.region for e in self.entries if e.kind == kind}
        ordered = [r for r in TEST_MARKETS if r in seen]
        return ordered + sorted(seen - set(TEST_MARKETS))


def merge_candidates(
    charts: Iterable[RegionChart],
    *,
    known_genomes: dict[str, dict] | None = None,
) -> list[Candidate]:
    """Fold many regional chart readings into one candidate per game.

    ``known_genomes`` maps ``game_id`` (e.g. ``gp-com.king.candycrushsaga``) to its tagged record,
    so a candidate already in GameTagger's catalogue carries its genome and is not treated as new.
    """

    known_genomes = known_genomes or {}
    by_game: dict[tuple[str, str], Candidate] = {}
    for chart in charts:
        for store_id, (rank, title, developer) in chart.rows.items():
            key = (chart.store, store_id)
            cand = by_game.get(key)
            if cand is None:
                cand = Candidate(store=chart.store, store_id=store_id, title=title)
                by_game[key] = cand
            # Prefer a non-empty developer / title if a later reading has one.
            if developer and not cand.developer:
                cand.developer = developer
            if title and (not cand.title or len(title) > len(cand.title)):
                cand.title = title
            cand.entries.append(
                ChartEntry(
                    region=chart.region,
                    store=chart.store,
                    kind=chart.kind,
                    rank=rank,
                    chart_size=chart.size,
                )
            )
    for cand in by_game.values():
        cand.known_genome = known_genomes.get(cand.game_id)

    # Fold the same game seen on different stores into one candidate, matched by normalized title.
    # Google Play is kept as the primary identity because the teardown tooling uses packages.
    # (Title matching is a heuristic; a rare same-title collision across stores merges wrongly.)
    merged: dict[str, Candidate] = {}
    for cand in by_game.values():
        key = normal_title(cand.title)
        existing = merged.get(key)
        if existing is None:
            merged[key] = cand
            continue
        primary, other = existing, cand
        if primary.store != "google_play" and other.store == "google_play":
            primary, other = other, existing
            merged[key] = primary
        primary.entries.extend(other.entries)
        primary.developer = primary.developer or other.developer
        primary.hints = primary.hints or other.hints
        primary.known_genome = primary.known_genome or other.known_genome
        primary.alt_ids[other.store] = other.store_id
    return list(merged.values())
