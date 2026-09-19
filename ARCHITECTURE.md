# GameTagger v2 Architecture

## Target flow

```text
Store metadata / documentation / publisher images / video
                         |
                         v
                 Evidence acquisition
                         |
                         v
                 Multimodal Observer
              (facts, not Genome labels)
                         |
                         v
                  Jev Decision Engine
          (atomic typed probabilistic judgments)
                         |
                         v
                    Policy Engine
             /             |             \
          accept      get evidence      review/deep model
             \             |             /
                         Genome
```

## 1. Evidence is immutable input

In the target architecture, every screenshot, clip, metadata record, or document becomes an `EvidenceItem` with a source, stable identifier/hash, and optional timestamps. Results must be reproducible against the exact evidence available at analysis time.

## 2. Observation is separate from interpretation

A multimodal observer should produce statements such as:

> `clip_18`: Player raises a shield immediately before an enemy sword lands. A bright effect appears at contact and the enemy staggers.

It should **not** produce:

> `mechanic_parry=true` or `Souls-like`.

Those are ontology decisions.

## 3. Jev is the ontology decision layer

For each tag, Jev receives the same compact structured state and an atomic question derived from the taxonomy. The default tag decision is a four-way Choice:

1. `present` — evidence positively establishes the feature.
2. `absent` — evidence explicitly establishes the feature is absent. Lack of observation alone is not sufficient.
3. `insufficient_evidence` — available material cannot establish either presence or absence.
4. `conflicting_evidence` — credible evidence sources materially disagree.

We store the entire probability distribution.

Primary genre uses a 14-family Choice plus `insufficient_evidence`, followed by conditional genre Choices for at least the top two families and all other positive-probability families. Family × conditional probabilities produce the global ranking. Exactly one highest-supported eligible primary is retained when it outranks insufficient evidence; up to two secondary IDs remain separate. See [v4.1](docs/GENRE_TAXONOMY_V4_1.md).

## 4. Code owns policy

Jev provides judgment; application code owns operational rules. Initial thresholds are placeholders to be calibrated on GameTagger's own benchmark.

Examples:

- `present >= 0.95` → candidate for automatic acceptance.
- high `insufficient_evidence` → acquire targeted evidence.
- high `conflicting_evidence` → human review.
- close primary-genre probabilities → review or retain multiple candidates.

No model is allowed to invent a fallback genre merely because output is uncertain.

## 5. Escalation is selective

The eventual pipeline should spend expensive multimodal reasoning only where it changes a decision. Easy visual traits can close early; ambiguous temporal/system traits can trigger targeted clip analysis, metadata retrieval, or human review.

## 6. Two evaluation modes

### Catalog mode
Uses all authorized metadata and media. Goal: best available catalog Genome.

### Blind-media mode
Hides the title and existing genre metadata. Goal: measure whether the system can classify unfamiliar/prerelease material rather than rely on model memory.

Both are required before production claims are made.

## Milestone 1 implementation

`gametagger.pipeline.AnalysisPipeline` validates and hashes a local image once, passes those
same bytes to an injected `Observer`, validates observations through `ObservationBoundary`,
invokes `JevDecisionEngine`, and applies `DecisionPolicy`. CLI credentials come only from the
process environment. `MockObserver` and `MockJevGateway` support offline testing.

Only single-image ingestion is implemented. The provider prompt prohibits temporal inference
from a still. Visual facts cannot carry taxonomy labels; exact metadata quotations are kept as
attributed source claims. The lexical boundary is deliberately conservative and does not prove
arbitrary generated text is factual. See README for limits and the live-validation status.

The canonical taxonomy remains `taxonomy/vgms_v4.yaml`. Wheel builds bundle this same file under
`gametagger/data` so the installed CLI works outside the source checkout.

## Local product workspace

`gametagger.workspace` adds a loopback-only FastAPI application, schema-v1 SQLite store, one bounded worker, private media storage and versioned reviews. `frontend/` is a React/TypeScript workspace built with Vite. Core browser contracts are generated from OpenAPI. The existing taxonomy, identity gate, provider-neutral Observer and strict Jev decision engine remain intact. Website offline jobs prepare evidence and persist explicit partial/not-evaluated results; they never invoke provider clients. Experiment reports recompute matched effects and separate historical replay from checked comparisons. See [runbook](docs/LOCAL_WORKSPACE.md) for operational/security boundaries.
