# Jev Experiment 001 — Shadow decision layer

## Question

Does `observer → Jev → policy` make better, more useful Genome decisions than the frozen legacy classifier?

## First experiment

Use the 25 pilot tags and v4.1 hierarchical primary genre using the same existing screenshots/descriptions before changing the media pipeline. This isolates the decision-layer change.

### Pipelines

1. **legacy_v1** — current production-style multimodal classifier.
2. **observer_llm** — factual observer followed by a generative structured classifier.
3. **observer_jev** — the same factual observations followed by Jev.
4. **observer_jev_escalate** — Jev plus targeted escalation when policy says evidence is insufficient, conflicting, or ambiguous.

## Required metrics

Per tag:
- precision
- recall
- false-positive rate
- abstention rate
- Brier score
- calibration by probability bucket
- reviewer correction rate

System-level:
- primary-genre top-1 accuracy
- primary-genre top-2 coverage
- average latency
- estimated model cost
- percentage of tags auto-accepted
- percentage requiring more evidence / deeper model / human review

## Two evaluation modes

### Catalog
Game identity and authorized metadata may be provided.

### Blind media
Hide the title, store genre labels, Wikipedia genre, and other identity cues where practical. This tests the capability needed for unknown/prerelease games.

## Decision rule

Do not promote Jev to the user-facing path based on aggregate accuracy alone. The target is a useful precision/coverage frontier: high precision for automatically accepted tags, with explicit abstention where evidence is weak.

## Live validation status

See [Milestone 1 findings](JEV_INTEGRATION.md). Authenticated execution requires a key.

## First live call

```bash
pip install -e '.[dev]'
export TYPESAFE_API_KEY='...'
python scripts/jev_smoke.py
```

The smoke fixture deliberately contains only a short observation of first-person gunplay. Good behavior should strongly support first-person/ranged/shooter traits while leaving unrelated system-level tags unresolved rather than confidently absent.
