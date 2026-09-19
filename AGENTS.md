# GameTagger architectural rules

- Observer describes evidence; it never assigns genres or Genome tags.
- Jev interprets observations against the canonical taxonomy.
- “Not observed” must never mean “absent.”
- `present`, `absent`, `insufficient_evidence`, and `conflicting_evidence` are distinct states.
- No forced fallback genres.
- Preserve complete Jev probability distributions.
- Every classification should retain evidence provenance.
- No credentials or secrets in source.
- GameTagger must remain platform-neutral across PC, console, and mobile.

## Development

Use the `gametagger` package. Run `pytest`, `ruff check .`, and `ruff format --check .`.
Live tests require both `GAMETAGGER_RUN_LIVE=1` and `TYPESAFE_API_KEY`; otherwise they skip.
Keep the observer and decision-provider interfaces injectable for offline tests.

## Bounded product build

Read [the owner build brief](docs/CODEX_BUILD_PLAN.md) and [current execution status](docs/EXECUTION_STATUS.md) before product work. Keep live inference budget-disabled without a numeric authorization. The local workspace is not a production deployment.
