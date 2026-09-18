# GenomeTagger v2 Architecture

## Target flow

```text
Steam / Xbox / Wikipedia / publisher uploads / video
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

Every screenshot, clip, metadata record, or document becomes an `EvidenceItem` with a source, stable identifier/hash, and optional timestamps. Results must be reproducible against the exact evidence available at analysis time.

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

Primary genre is a separate Choice across 59 allowed genres plus `insufficient_evidence`.

## 4. Code owns policy

Jev provides judgment; application code owns operational rules. Initial thresholds are placeholders to be calibrated on GenomeTagger's own benchmark.

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
