"""Plain-text summaries of a rich-mode plan or profile for people reading a terminal."""

from __future__ import annotations

from collections import Counter

from gametagger.genome.engine import GENRE_QUESTION, GenomePlan, GenomeProfile
from gametagger.genome.vocabulary import GenomeVocabulary


def _pct(p: float) -> str:
    return f"{round(p * 100)}%"


def render_plan(plan: GenomePlan, estimate: dict, *, dossier, claims, vocabulary, tags) -> str:
    per_source = Counter(c.evidence_id for c in claims)
    tag_ids = {t.id for t in tags}
    asked = [k for k in plan.specs if k in tag_ids]
    lines = [
        "DRY RUN: nothing was sent to any model.",
        f"Game: {dossier.title or '(untitled)'}  [{dossier.game_id}]",
        "Evidence: "
        + (
            ", ".join(
                f"{s.id} ({s.type.value}, {per_source[s.id]} claims)" for s in dossier.sources
            )
            or "no text sources"
        ),
    ]
    if dossier.images:
        lines.append(
            f"Screenshots: {len(dossier.images)} (a live run describes them first; "
            "their statements are not in this estimate)"
        )
    lines.append(
        f"Tag questions: {len(asked)} of {len(tags)} would be asked"
        + (" plus the genre hierarchy" if GENRE_QUESTION in plan.specs else "")
    )
    skipped = [k for k in plan.skipped if k in tag_ids]
    if skipped:
        lines.append(f"Not asked (no allowed evidence type): {', '.join(skipped)}")
    by_category = Counter(vocabulary.tags_by_id[k].category for k in asked)
    labels = {c.id: c.label for c in vocabulary.categories}
    lines.append("By category: " + ", ".join(f"{labels[c]} {n}" for c, n in by_category.items()))
    lines.append(
        f"Requests: {len(estimate['requests'])}, about "
        f"{estimate['approx_input_tokens_total']:,} input tokens (rough estimate; "
        "excludes retries and screenshot description)"
    )
    lines.append("Use --format json to see the exact questions and evidence Jev would receive.")
    return "\n".join(lines)


def render_profile(profile: GenomeProfile, vocabulary: GenomeVocabulary) -> str:
    p = profile.provenance
    mode = "OFFLINE MOCK (pipeline check only, not inference)" if profile.offline else "LIVE"
    usage = p["usage"].get("input_tokens")
    lines = [
        f"{profile.title or '(untitled)'}  [{profile.game_id}]",
        f"Run: {mode} | model {p['returned_decision_model'] or 'none'} | status {profile.status}"
        f" | {p['requests']} requests"
        + (f" | {usage:,} input tokens" if isinstance(usage, int) else ""),
        "Evidence: "
        + ", ".join(
            f"{s.id} ({s.type.value}, {sum(c.evidence_id == s.id for c in profile.claims)} claims)"
            for s in profile.sources
        ),
        "",
    ]
    if profile.primary_genre:
        g = profile.primary_genre
        lines.append(f"Primary genre: {g.name} ({_pct(g.probability)})")
        if profile.secondary_genres:
            lines.append(
                "Alternatives:  "
                + ", ".join(f"{s.name} ({_pct(s.probability)})" for s in profile.secondary_genres)
            )
    elif profile.genre is not None:
        lines.append("Primary genre: not established (insufficient evidence)")
    else:
        code = profile.genre_execution.error.code if profile.genre_execution.error else "unknown"
        lines.append(f"Primary genre: not computed ({code})")
    c = profile.counts
    lines += [
        "",
        f"Genome: {c['strong'] + c['likely']} present ({c['strong']} strong, {c['likely']} likely)"
        f" | {c['absent']} absent | {c['conflicting']} conflicting | {c['unknown']} unknown"
        f" | {c['not_evaluated']} not asked | {c['error']} errors",
    ]
    for category in vocabulary.categories:
        tags = [t for t in profile.tags if t.category == category.id]
        shown = [t for t in tags if t.tier in {"strong", "likely", "absent", "conflicting"}]
        if not shown:
            continue
        unknown = sum(t.tier == "unknown" for t in tags)
        lines.append(f"\n{category.label}" + (f"  ({unknown} unknown)" if unknown else ""))
        for tier in ("strong", "likely", "absent", "conflicting"):
            items = [t for t in shown if t.tier == tier]
            if items:
                lines.append(
                    f"  {tier:<11} "
                    + ", ".join(f"{t.label} ({_pct(t.probabilities[t.state])})" for t in items)
                )
    notes = list(profile.warnings)
    if profile.quarantined_observations:
        notes.append(
            f"{len(profile.quarantined_observations)} screenshot statement(s) were set aside by "
            "the Observer word filter and not shown to Jev."
        )
    if any(profile.claims_dropped.values()):
        notes.append(f"Claims over the per-source cap were not sent: {profile.claims_dropped}")
    notes += [
        "Percentages are Jev's raw probability for the chosen state, not measured accuracy.",
        "Nothing here is publishable until a person reviews it.",
    ]
    lines.append("\nNotes")
    lines += [f"  - {n}" for n in notes]
    return "\n".join(lines)
