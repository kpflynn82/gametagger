"""Hierarchical genre aggregation; never calls an observer or infers labels from titles."""

from __future__ import annotations

from typesafe_sdk import ChoiceAnswer, SystemOneResponse

from gametagger.domain import GenreDecision
from gametagger.taxonomy import Taxonomy

INSUFFICIENT = "insufficient_evidence"


def select_families(taxonomy: Taxonomy, probabilities: dict[str, float]) -> list[str]:
    """Keep the top two AND every other positive-mass branch; no lost probability mass."""
    ranked = sorted(taxonomy.families_by_id, key=lambda fid: (-probabilities[fid], fid))
    return [fid for i, fid in enumerate(ranked) if i < 2 or probabilities[fid] > 0]


def aggregate_genres(
    taxonomy: Taxonomy,
    family_answer: ChoiceAnswer,
    conditional: SystemOneResponse,
    *,
    family_model: str,
    evidence_ids: list[str],
) -> GenreDecision:
    """Derive a normalized joint distribution without changing saved provider distributions.

    P(g) = P(family(g)) * P(g | family(g)). Global unknown includes Stage A unknown
    plus each branch's weighted conditional unknown. Only zero-mass branches may be omitted.
    """
    family_raw = dict(family_answer.probabilities)
    selected = select_families(taxonomy, family_raw)
    if set(conditional.answers) != {f"genre:{fid}" for fid in selected}:
        raise ValueError("Conditional answers must cover every selected family")
    family_total = sum(family_raw.values())
    family = {k: v / family_total for k, v in family_raw.items()}
    global_probs = {g.id: 0.0 for g in taxonomy.genres_by_id.values() if g.primary_eligible}
    unknown = family[INSUFFICIENT]
    raw, choices, confidences = {}, {}, {}
    for fid in selected:
        answer = conditional.answers[f"genre:{fid}"]
        if not isinstance(answer, ChoiceAnswer):
            raise ValueError("Expected conditional Choice answer")
        raw[fid] = dict(answer.probabilities)
        choices[fid] = answer.choice
        confidences[fid] = answer.confidence
        total = sum(answer.probabilities.values())
        for genre in taxonomy.families_by_id[fid].eligible_genres:
            global_probs[genre.id] = family[fid] * answer.probabilities[genre.id] / total
        unknown += family[fid] * answer.probabilities[INSUFFICIENT] / total
    global_probs[INSUFFICIENT] = unknown
    # Normalize derived scores only; raw Jev values remain intact in the result.
    total = sum(global_probs.values())
    global_probs = {k: v / total for k, v in global_probs.items()}
    ranked = sorted(
        (g for g in global_probs if g != INSUFFICIENT), key=lambda gid: (-global_probs[gid], gid)
    )
    winner = ranked[0]
    primary = winner if global_probs[winner] > global_probs[INSUFFICIENT] else None
    # A secondary is another supported candidate, not a second store-listing primary.
    secondary = (
        [
            g
            for g in ranked[1:]
            if global_probs[g] >= 0.1 and global_probs[g] > global_probs[INSUFFICIENT]
        ][:2]
        if primary
        else []
    )
    return GenreDecision(
        primary_genre=primary,
        secondary_genres=secondary,
        confidence=global_probs[primary or INSUFFICIENT],
        family_probabilities=family_raw,
        family_choice=family_answer.choice,
        family_confidence=family_answer.confidence,
        conditional_genre_probabilities=raw,
        conditional_choices=choices,
        conditional_confidences=confidences,
        global_genre_probabilities=global_probs,
        evaluated_families=selected,
        evidence_ids=evidence_ids,
        family_model=family_model,
        decision_model=conditional.model,
        conditional_models={fid: conditional.model for fid in selected},
    )
