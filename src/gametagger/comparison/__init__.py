"""Jev versus the previous single-call method, on identical dossiers.

Stages: cohort (public charts) -> identity (exact store IDs) -> dossiers (shared evidence) ->
answer key (Steam user tags) -> paid run (budget-capped) -> owner review -> scoring -> report.
Nothing here calls a model except ``runner`` and only with an explicit ``--live`` and a budget.
"""
