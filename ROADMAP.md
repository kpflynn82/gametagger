# GameTagger roadmap

## Milestone 1 — Platform-neutral vertical slice

Implemented: canonical taxonomy, image evidence hashing, structured Anthropic observer,
deterministic mocks, Jev contract validation, policy, complete JSON results, single-case CLI,
provenance, offline tests, and an environment-gated live test.

Authenticated Jev validation passes. Anthropic validation awaits workspace configuration; see
[validation status](docs/JEV_INTEGRATION.md). No older repository or production service is changed.

## PR 3 — Jev shadow experiment
- Run legacy and observer→Jev in parallel
- Persist full Jev probability distributions
- Compare 25 pilot tags + 59-way genre
- Do not alter user-facing production answers yet

## PR 4 — Benchmark v1
- 100–200 deliberately varied games
- Human-reviewed tag truth and asset-supported truth
- Catalog and blind-media evaluation modes
- Measure precision, recall, FPR, abstention, Brier/calibration, genre accuracy, cost, latency

## PR 5 — Calibrated production policy
- Per-tag thresholds rather than a single global confidence threshold
- Accept / target-more-evidence / deep-model / human-review routing
- Remove all forced genre fallbacks

## PR 6 — Media ingest v2
- Publisher image/video upload
- Full-timeline scene detection
- Gameplay vs cinematic/menu/title-card separation
- Deduplication and representative sampling
- Short ordered clips for temporal mechanics

## PR 7 — Adaptive evidence acquisition
- Use unresolved Jev decisions to identify which scenes/evidence to inspect next
- Stop analysis early for already-resolved dimensions
- Measure incremental value of each added evidence pass

## PR 8 — Reviewer UI
- Per-tag probabilities
- Evidence clips/timestamps
- Approve / reject / needs-more-evidence
- Preserve human corrections across re-analysis

## Later product opportunities
- Genome completeness score
- Mode-specific Genomes
- Catalog update / patch-note watchdog
- Versioned Genome history
- Natural-language discovery and reranking
- Evidence-backed recommendation explanations
- Taxonomy linting and active-learning queues
