# GenomeTagger v2

GenomeTagger v2 is an evidence-backed game classification system designed around a strict separation of concerns:

**Media / metadata → observations → Jev decisions → deterministic policy → escalation / review**

The v2 goal is not merely to output plausible tags. It is to produce a reproducible game Genome in which every tag can be traced to evidence, uncertainty is explicit, and automation thresholds can be calibrated against human-reviewed results.

## Why a new project?

The existing GenomeTagger/GameTagger repositories remain untouched and serve as the `legacy_v1` baseline. V2 is intentionally clean so we can measure whether each architectural change improves quality rather than mixing multiple changes into one moving target.

## First milestone

The pilot implements:

- One machine-readable VGMS taxonomy (`taxonomy/vgms_v4.yaml`)
- 25 pilot Genome tags spanning visual, combat/mechanics, structure, and gameplay
- The existing 59-way primary genre vocabulary plus `insufficient_evidence`
- Evidence-aware domain models
- A Jev decision engine that uses four states per tag:
  - `present`
  - `absent`
  - `insufficient_evidence`
  - `conflicting_evidence`
- A deterministic policy engine for accept/review/escalate decisions
- Shadow-mode configuration so Jev can be benchmarked without replacing production results
- An evaluation harness for precision, recall, false-positive rate, abstention, Brier score, latency, and cost

## Jev

The integration uses TypeSafe's official Python SDK (`typesafe-sdk`). The client reads `TYPESAFE_API_KEY` from the environment and defaults to `jev-latest`.

```bash
export TYPESAFE_API_KEY=...
```

Never put the key in source code, fixtures, logs, screenshots, or committed `.env` files.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
pytest
uvicorn genometagger_v2.api.main:app --reload
```

## Design rule

The observer says **what the evidence shows**. Jev decides **what those observations mean under VGMS**. Application code decides **whether the evidence is strong enough to act**.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [ROADMAP.md](ROADMAP.md).

## First live Jev smoke test

Once `TYPESAFE_API_KEY` is set:

```bash
python scripts/jev_smoke.py
```

The smoke test runs a blind-media observation through all pilot Jev questions and prints a few representative decisions plus the genre distribution/policy result. It does not contact any existing GenomeTagger production service.
