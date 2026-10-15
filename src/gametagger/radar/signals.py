"""Transparent scoring for radar candidates.

Every candidate gets four signals in 0..1 and a weighted priority in 0..100. Each signal keeps a
plain-language reason, so the morning brief can explain *why* a game surfaced rather than showing a
bare number. The weights are data, not magic: the owner can retune them without touching the logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from gametagger.radar.candidate import Candidate

# A game ranked at or below this on a free (download) chart counts as "barely downloaded" when it
# is simultaneously grossing well -- the monetization-strength fingerprint.
LOW_DOWNLOAD_RANK = 60
# A grossing rank at or above this is "earning well" for a test market.
STRONG_GROSSING_RANK = 100


@dataclass(frozen=True)
class SignalWeights:
    """How much each signal counts toward the 0..100 priority. Need not sum to 1."""

    monetization: float = 0.40
    soft_launch: float = 0.25
    novelty: float = 0.20
    trend_fit: float = 0.15


@dataclass(frozen=True)
class Signal:
    value: float  # 0..1
    reason: str


@dataclass(frozen=True)
class Signals:
    monetization: Signal
    soft_launch: Signal
    novelty: Signal
    trend_fit: Signal
    priority: float  # 0..100
    headline: str  # the one-line "why this game" summary

    def as_dict(self) -> dict:
        return {
            "priority": round(self.priority, 1),
            "headline": self.headline,
            "signals": {
                "monetization": {
                    "value": round(self.monetization.value, 3),
                    "reason": self.monetization.reason,
                },
                "soft_launch": {
                    "value": round(self.soft_launch.value, 3),
                    "reason": self.soft_launch.reason,
                },
                "novelty": {"value": round(self.novelty.value, 3), "reason": self.novelty.reason},
                "trend_fit": {
                    "value": round(self.trend_fit.value, 3),
                    "reason": self.trend_fit.reason,
                },
            },
        }


def _rank_quality(rank: int, floor: int) -> float:
    """1.0 at rank 1, fading to 0 at ``floor``. Linear and easy to reason about."""
    if rank <= 0:
        return 0.0
    return max(0.0, min(1.0, (floor - rank + 1) / floor))


def monetization_signal(cand: Candidate) -> Signal:
    """High grossing rank + weak/absent download rank = strong per-player monetization."""

    gross = cand.best_rank("grossing")
    if gross is None:
        return Signal(0.0, "not on any top-grossing chart")
    free = cand.best_rank("free")
    gross_q = _rank_quality(gross.rank, STRONG_GROSSING_RANK)

    if free is None:
        # Grossing well while absent from the download charts entirely: the clearest signal.
        value = min(1.0, 0.6 + 0.4 * gross_q)
        reason = (
            f"#{gross.rank} grossing in {gross.region} but not in that market's top "
            f"{free_floor(cand)} downloads: strong monetization on few installs"
        )
        return Signal(round(value, 3), reason)

    gap = free.rank - gross.rank  # positive = grosses higher than it downloads
    if gap <= 0:
        value = 0.15 * gross_q
        return Signal(
            round(value, 3),
            f"#{gross.rank} grossing, #{free.rank} downloads: earning tracks its install volume",
        )
    gap_q = min(1.0, gap / LOW_DOWNLOAD_RANK)
    value = min(1.0, 0.5 * gross_q + 0.5 * gap_q)
    reason = (
        f"#{gross.rank} grossing vs #{free.rank} downloads in {gross.region}: "
        f"out-earns its install rank by {gap} places"
    )
    return Signal(round(value, 3), reason)


def free_floor(cand: Candidate) -> int:
    """The size of the largest free-chart reading we have, for phrasing 'not in top N'."""
    sizes = [e.chart_size for e in cand.entries if e.kind == "free"]
    return max(sizes) if sizes else LOW_DOWNLOAD_RANK


def soft_launch_signal(cand: Candidate, *, us_game_ids: frozenset[str]) -> Signal:
    """Present in test markets, absent from the US, and spread across more than one test market."""

    test_regions = [r for r in cand.regions("grossing") if r in ("CA", "AU", "NZ")]
    if not test_regions:
        test_regions = [r for r in cand.regions("free") if r in ("CA", "AU", "NZ")]
    if not test_regions:
        return Signal(0.0, "not ranked in a test market (CA/AU/NZ)")

    in_us = cand.game_id in us_game_ids
    coverage = min(1.0, len(test_regions) / 3)  # all three test markets = full coverage
    value = 0.4 + 0.6 * coverage
    if in_us:
        value *= 0.3  # already live in the US: much less likely a fresh soft launch
        tail = "; already in the US catalogue, so probably already launched"
    else:
        tail = "; not in the US top-grosser catalogue"
    reason = f"ranked in {', '.join(test_regions)}{tail}"
    return Signal(round(min(1.0, value), 3), reason)


def novelty_signal(cand: Candidate) -> Signal:
    """New to us: not already tagged in GameTagger's catalogue of established US top grossers."""

    if cand.known_genome is not None:
        return Signal(0.1, "already tagged in GameTagger's catalogue")
    if cand.developer:
        return Signal(
            0.9, f"not in our catalogue; published by {cand.developer} (a studio worth watching)"
        )
    return Signal(0.75, "not in our catalogue")


def trend_fit_signal(cand: Candidate, *, hot_terms: dict[str, float]) -> Signal:
    """Does the game's apparent genre/mechanics match what the weekly digest says is hot?

    ``hot_terms`` maps a lowercased keyword (e.g. "merge", "collection album", "hybrid-casual")
    to a weight in 0..1 drawn from the digest. We match against the candidate's title and any
    hints gathered from its store listing, plus its genome genre if we already know the game.
    """

    if not hot_terms:
        return Signal(0.0, "no digest trends supplied")
    haystack = " ".join([cand.title.lower(), *[h.lower() for h in cand.hints]])
    if cand.known_genome:
        genre = str(cand.known_genome.get("primary_genre") or "").replace("_", " ")
        haystack += " " + genre.lower()
    hits = {term: w for term, w in hot_terms.items() if term in haystack}
    if not hits:
        return Signal(0.0, "no current digest trend detected from chart data alone")
    value = min(1.0, max(hits.values()) * 0.7 + 0.3 * min(1.0, len(hits) / 3))
    matched = ", ".join(sorted(hits, key=lambda t: -hits[t]))
    return Signal(round(value, 3), f"matches current digest trends: {matched}")


def score_candidate(
    cand: Candidate,
    *,
    us_game_ids: frozenset[str],
    hot_terms: dict[str, float] | None = None,
    weights: SignalWeights | None = None,
) -> Signals:
    weights = weights or SignalWeights()
    hot_terms = hot_terms or {}
    mon = monetization_signal(cand)
    soft = soft_launch_signal(cand, us_game_ids=us_game_ids)
    nov = novelty_signal(cand)
    trend = trend_fit_signal(cand, hot_terms=hot_terms)

    total_w = weights.monetization + weights.soft_launch + weights.novelty + weights.trend_fit
    priority = (
        100
        * (
            weights.monetization * mon.value
            + weights.soft_launch * soft.value
            + weights.novelty * nov.value
            + weights.trend_fit * trend.value
        )
        / total_w
    )

    # Headline leads with the strongest contributing signal.
    contributions = {
        mon.reason: weights.monetization * mon.value,
        soft.reason: weights.soft_launch * soft.value,
        trend.reason: weights.trend_fit * trend.value,
    }
    headline = max(contributions, key=contributions.get)
    return Signals(
        monetization=mon,
        soft_launch=soft,
        novelty=nov,
        trend_fit=trend,
        priority=round(priority, 1),
        headline=headline,
    )
