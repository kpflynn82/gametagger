"""Report adapters reuse the evidence-supported metrics; never manufacture labels."""

from gametagger.evaluation.metrics import genre_metrics, measure, tag_metrics
from gametagger.taxonomy import load_taxonomy


def quality_comparison(a, b, reason):
    rows = [a.case_measurements, b.case_measurements]
    result = {
        "available": False,
        "reason": reason,
        "tags": [],
        "headline": {},
        "paired_games": 0,
        "assigned_games": len(a.case_ids),
        "target": "four-state evidence-supported human judgments",
        "uncertainty": "No independent tag-sample inference; intervals must cluster by game",
    }
    if reason:
        return result
    ids = set(a.case_ids)
    if any(len(r) != len(ids) or {x.case_id for x in r} != ids for r in rows):
        result["reason"] = "Complete paired case measurements unavailable"
        return result
    left, right = [{r.case_id: r for r in rs} for rs in rows]
    for case in ids:
        x, y = left[case], right[case]
        if (
            x.reference != y.reference
            or x.identity_eligible != y.identity_eligible
            or x.platform != y.platform
            or x.mode != y.mode
        ):
            result["reason"] = "Paired reference, identity, platform or input mode mismatch"
            return result
    taxonomy = load_taxonomy()
    result.update(
        available=True,
        reason=None,
        paired_games=sum(
            r.identity_eligible and r.reference.origin == "human_review" for r in rows[0]
        ),
        identity_excluded_games=sum(not r.identity_eligible for r in rows[0]),
        pending_reference_games=sum(r.reference.origin != "human_review" for r in rows[0]),
    )
    summaries = [{t.id: tag_metrics(rs, t.id) for t in taxonomy.tags} for rs in rows]
    for t in taxonomy.tags:
        ma, mb = [s[t.id] for s in summaries]

        def delta(key, left=ma, right=mb):
            x, y = left[key]["value"], right[key]["value"]
            return 100 * (y - x) if x is not None and y is not None else None

        result["tags"].append(
            {
                "id": t.id,
                "label": t.label,
                "category": t.category,
                "baseline": ma,
                "candidate": mb,
                "precision_change_pp": delta("accepted_precision"),
                "recall_change_pp": delta("end_to_end_positive_recovery"),
                "warning": "Sparse descriptive slice; counts are not an independent sample per tag"
                if min(ma["human_supported_labels"], mb["human_supported_labels"]) < 20
                else "Game-clustered uncertainty not estimated",
            }
        )
    for label, key in (
        ("Accepted attribute precision", "accepted_precision"),
        ("End-to-end recall", "end_to_end_positive_recovery"),
    ):
        result["headline"][label] = [
            measure(
                sum(s[t.id][key]["numerator"] for t in taxonomy.tags),
                sum(s[t.id][key]["denominator"] for t in taxonomy.tags),
            )
            for s in summaries
        ]
    genres = [genre_metrics(rs, set(taxonomy.genres_by_id)) for rs in rows]
    result["genre"] = dict(zip(("baseline", "candidate"), genres, strict=True))
    result["headline"]["Actual primary correctness"] = [
        g["actual_primary_correctness"] for g in genres
    ]
    result["headline"]["Accepted-primary precision"] = [g["publishable_precision"] for g in genres]
    # Keep all assigned cases visible, but use the predeclared identity-eligible coverage cohort.
    eligible_genres = [
        genre_metrics([r for r in rs if r.identity_eligible], set(taxonomy.genres_by_id))
        for rs in rows
    ]
    result["headline"]["Useful coverage"] = [g["publication_coverage"] for g in eligible_genres]
    result["headline"]["Execution error rate"] = [
        measure(
            sum(
                r.status == "error"
                or r.genre_execution == "error"
                or genre_metrics([r], set(taxonomy.genres_by_id))["invalid_distributions"] > 0
                or any(tag_metrics([r], tid)["errors"] > 0 for tid in r.tags)
                for r in rs
            ),
            len(rs),
        )
        for rs in rows
    ]
    result["headline"]["Partial-output rate"] = [
        measure(sum(r.status == "partial" for r in rs), len(rs)) for rs in rows
    ]
    result["macro"] = {}
    for label, key in (
        ("Accepted attribute precision", "accepted_precision"),
        ("End-to-end recall", "end_to_end_positive_recovery"),
    ):
        result["macro"][label] = []
        for summary in summaries:
            defined = [s[key]["value"] for s in summary.values() if s[key]["value"] is not None]
            result["macro"][label].append(measure(sum(defined), len(defined)))
    result["cases"] = [
        {
            "case_id": case,
            "platform": left[case].platform,
            "mode": left[case].mode,
            "identity_eligible": left[case].identity_eligible,
            "reference_origin": left[case].reference.origin,
            "reference_primary": left[case].reference.primary_genre,
            "baseline_status": left[case].status,
            "candidate_status": right[case].status,
            "baseline_primary": left[case].primary_genre,
            "candidate_primary": right[case].primary_genre,
        }
        for case in a.case_ids
    ]
    return result
