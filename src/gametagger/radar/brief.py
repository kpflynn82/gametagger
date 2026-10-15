"""Turn scored candidates into the morning brief: a push line, a shortlist, and a build proposal.

The build proposal is the north-star output -- the "there's a new game X doing Y; here's how we'd
differentiate it; should I build a prototype?" card. The structure here is deterministic so it can
be tested and so a scheduled run always produces something sane. When the radar runs with the
weekly digest and a live model, the model fills ``opportunity`` and ``differentiation`` with richer,
cited reasoning; without it, the rule-based fallback below keeps the card honest and useful.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gametagger.radar.candidate import Candidate
from gametagger.radar.signals import Signals

# Grounded in docs/game knowledge and the weekly digest: per family, the themes that already
# crowd the genre (so a game using them does not stand out) and under-used themes that have sold
# well recently, plus mechanics the digest currently flags as hot. Data, easy to extend.
GENRE_PLAYBOOK: dict[str, dict[str, tuple[str, ...]]] = {
    "role_playing": {
        "crowded_themes": ("anime", "fantasy medieval", "military sci-fi", "cultivation"),
        "fresh_themes": ("dragons", "mythic beasts", "cozy folklore", "steampunk"),
        "hot_mechanics": ("social tournaments", "gacha", "collection albums", "idle progress"),
    },
    "strategy": {
        "crowded_themes": ("war/military", "zombie survival", "kingdom medieval"),
        "fresh_themes": ("dragons", "mythology", "nature/ecology"),
        "hot_mechanics": ("alliance events", "merge", "collection albums", "season pass"),
    },
    "puzzle": {
        "crowded_themes": ("candy/sweets", "home renovation", "garden"),
        "fresh_themes": ("dragons", "space", "cozy animals"),
        "hot_mechanics": ("merge", "collection albums", "narrative chapters", "limited events"),
    },
    "casual_idle": {
        "crowded_themes": ("tycoon/business", "farm", "restaurant"),
        "fresh_themes": ("dragons", "mythic", "deep sea"),
        "hot_mechanics": ("merge", "prestige", "collection albums", "rewarded-ad boosts"),
    },
    "simulation_management": {
        "crowded_themes": ("farm", "city", "restaurant", "home design"),
        "fresh_themes": ("dragons", "wildlife sanctuary", "space colony"),
        "hot_mechanics": ("merge", "story chapters", "decorating meta", "social visits"),
    },
}
DEFAULT_PLAYBOOK = {
    "crowded_themes": (),
    "fresh_themes": ("dragons",),
    "hot_mechanics": ("collection albums", "social tournaments", "season pass"),
}


@dataclass
class Differentiation:
    """A concrete, buildable change set for a clone -- the 'here's the opportunity' part."""

    keep: str  # the standout system worth cloning faithfully
    theme_from: str  # the target's theme
    theme_to: str  # the fresh theme we'd use instead
    add_mechanic: str  # one hot mechanic to layer in
    rationale: str


@dataclass
class BuildProposal:
    candidate_title: str
    game_id: str
    priority: float
    what_it_is: str
    whats_working: str
    differentiation: Differentiation
    question: str = "Should I build a prototype with these changes?"


@dataclass
class BriefedCandidate:
    candidate: Candidate
    signals: Signals
    proposal: BuildProposal


# Common store/genre phrases -> the playbook family, longest phrase first so "action rpg" maps to
# role_playing (rpg), not action. Extended as new genre words show up in hints.
GENRE_ALIASES: tuple[tuple[str, str], ...] = (
    ("rpg", "role_playing"),
    ("role playing", "role_playing"),
    ("4x", "strategy"),
    ("strategy", "strategy"),
    ("war", "strategy"),
    ("tower defense", "strategy"),
    ("match", "puzzle"),
    ("puzzle", "puzzle"),
    ("sort", "puzzle"),
    ("merge", "simulation_management"),
    ("tycoon", "simulation_management"),
    ("management", "simulation_management"),
    ("builder", "simulation_management"),
    ("simulation", "simulation_management"),
    ("farm", "simulation_management"),
    ("idle", "casual_idle"),
    ("clicker", "casual_idle"),
    ("casual", "casual_idle"),
)


def _word_tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens, naive-singularized, for punctuation-insensitive overlap."""
    return {
        t[:-1] if len(t) > 3 and t.endswith("s") else t
        for t in re.findall(r"[a-z0-9]+", text.lower())
    }


def _family(cand: Candidate) -> str:
    if cand.known_genome and cand.known_genome.get("primary_genre"):
        # Map a specific genre back to its family by its known family probabilities if present.
        fams = cand.known_genome.get("genre_family_probabilities") or {}
        if fams:
            return max(fams, key=fams.get)
    haystack = " ".join(t.lower() for t in cand.hints)
    for phrase, fam in GENRE_ALIASES:
        if phrase in haystack:
            return fam
    return "unknown"


def propose_differentiation(
    cand: Candidate,
    *,
    standout_mechanic: str | None = None,
    hot_terms: dict[str, float] | None = None,
) -> Differentiation:
    """Rule-based differentiation: keep the standout system, freshen the theme, add a hot mechanic.

    ``standout_mechanic`` is the system the teardown (or the chart hint) flags as the reason the
    game is working. ``hot_terms`` biases which fresh mechanic we add toward current digest trends.
    """

    fam = _family(cand)
    book = GENRE_PLAYBOOK.get(fam, DEFAULT_PLAYBOOK)
    theme_to = book["fresh_themes"][0] if book["fresh_themes"] else "dragons"

    # Pick an added mechanic the game does not already lean on, biased toward digest trends. The
    # overlap test is token-based (singular, punctuation-insensitive) so a "social-tournament
    # ladder" standout correctly rules out adding "social tournaments" -- it is already the hook.
    standout = standout_mechanic or "its core loop"
    standout_tokens = _word_tokens(standout)
    candidates = [m for m in book["hot_mechanics"] if not _word_tokens(m) <= standout_tokens]
    if hot_terms:
        candidates.sort(key=lambda m: -max((w for t, w in hot_terms.items() if t in m), default=0))
    add = candidates[0] if candidates else "collection albums"

    crowded = ", ".join(book["crowded_themes"]) if book["crowded_themes"] else "the usual themes"
    rationale = (
        f"{fam.replace('_', ' ').title()} is crowded with {crowded}; a {theme_to} theme is "
        f"under-used there and has sold well in recent hits. Keeping {standout} (the part that is "
        f"working) and adding {add} gives a familiar-but-fresh hook the store page can show."
    )
    return Differentiation(
        keep=standout_mechanic or "the core loop",
        theme_from="its current theme",
        theme_to=theme_to,
        add_mechanic=add,
        rationale=rationale,
    )


def build_proposal(
    briefed_signals: Signals,
    cand: Candidate,
    *,
    standout_mechanic: str | None = None,
    hot_terms: dict[str, float] | None = None,
    what_it_is: str | None = None,
) -> BuildProposal:
    fam = _family(cand).replace("_", " ")
    what_it_is = what_it_is or (
        f"{cand.title}"
        + (f", a {fam} game" if fam != "unknown" else "")
        + (f" from {cand.developer}" if cand.developer else "")
    )
    diff = propose_differentiation(cand, standout_mechanic=standout_mechanic, hot_terms=hot_terms)
    whats_working = standout_mechanic or briefed_signals.headline
    return BuildProposal(
        candidate_title=cand.title,
        game_id=cand.game_id,
        priority=briefed_signals.priority,
        what_it_is=what_it_is,
        whats_working=whats_working,
        differentiation=diff,
    )


def render_push(top: BriefedCandidate, n_more: int) -> str:
    """The one phone-banner sentence, wrapped by the caller in routine tags."""

    d = top.proposal.differentiation
    more = f" (+{n_more} more on the radar)" if n_more else ""
    return (
        f"New soft-launch find: {top.candidate.title} -- {top.proposal.whats_working}. "
        f"Opportunity: a {d.theme_to} take with {d.add_mechanic}. "
        f"Build a prototype?{more}"
    )


def render_shortlist_md(briefed: list[BriefedCandidate], *, chart_date: str | None = None) -> str:
    """The full shortlist, newest signal first, for the private repo / Drive."""

    lines = ["# Soft-launch radar shortlist", ""]
    if chart_date:
        lines.append(f"Charts read: {chart_date} (Canada, Australia, New Zealand).")
        lines.append("")
    if not briefed:
        lines.append("No candidate cleared the bar today.")
        return "\n".join(lines)
    for i, b in enumerate(briefed, 1):
        p, d, s = b.proposal, b.proposal.differentiation, b.signals
        lines += [
            f"## {i}. {b.candidate.title}  ·  priority {p.priority:.0f}/100",
            "",
            f"- **What it is:** {p.what_it_is}",
            f"- **What's working:** {p.whats_working}",
            f"- **Why it surfaced:** {s.headline}",
            f"- **Signals:** monetization {s.monetization.value:.2f} "
            f"({s.monetization.reason}); soft-launch {s.soft_launch.value:.2f} "
            f"({s.soft_launch.reason}); novelty {s.novelty.value:.2f}; "
            f"trend-fit {s.trend_fit.value:.2f} ({s.trend_fit.reason})",
            f"- **Proposed clone:** keep {d.keep}; reskin to **{d.theme_to}**; "
            f"add **{d.add_mechanic}**. {d.rationale}",
            f"- **Decision:** {p.question}  `gametagger-radar approve {p.game_id}`",
            "",
        ]
    return "\n".join(lines)
