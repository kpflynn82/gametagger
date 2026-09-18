# GameTagger v2

GameTagger classifies video game evidence across **PC, console, and mobile**. Milestone 1 provides a local, platform-neutral vertical slice:

```text
EvidenceItem → Observer → Observation[] → Jev → Policy → AnalysisResult
```

The observer describes visible facts. Jev interprets them against the canonical VGMS taxonomy. Application policy decides whether to accept a decision, acquire evidence, or request review. A feature that is not observed is never automatically marked absent.

## Setup

Python 3.11 or newer is required. The checked-in `uv.lock` records the tested dependencies.

```bash
uv sync --frozen --extra dev
source .venv/bin/activate
pytest
ruff check .
ruff format --check .
```

Alternatively, use `python -m venv .venv`, activate it, and run `pip install -e '.[dev]'`.

## Run one case without credentials

```bash
gametagger --image fixtures/sample.png --metadata fixtures/sample.metadata.json --offline
```

This prints the complete JSON result. Offline mode explicitly uses `mock-observer-v1` and `mock-jev-v1`, marks the run `offline: true`, and assigns all probability to `insufficient_evidence`. It exercises serialization, provenance, and policy; it is **not model inference**. The mock observer quotes supplied metadata and accepts injected visual facts in Python tests. It never invents image observations.

## Analyze a real image

Set `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY` in your process environment. Choose a vision-capable Claude model enabled for your account using `OBSERVER_MODEL` or `--observer-model`. No key is accepted as a CLI argument, and no credentials belong in source, fixtures, or results.

```bash
gametagger --image /path/to/screenshot.png \
  --metadata /path/to/metadata.json \
  --observer-model YOUR_CLAUDE_VISION_MODEL \
  --game-id case-001 --game-title "Example game"
```

Metadata is an optional JSON object with string values. The Anthropic adapter sends the image and metadata to Anthropic; factual observations are then sent to TypeSafe. Image input is a single local PNG, JPEG, WEBP, or nonanimated GIF, at most 5 MiB and 8000 pixels per side. Remote URLs and video analysis are future adapters.

`.env.example` is a template. Nothing loads `.env` implicitly. If you store credentials in an ignored local `.env`, explicitly load them into the command environment, for example `uv run --env-file .env gametagger ...`. The live integration test follows the same environment rule.

`--blind-media` removes title and metadata before observation and classification and uses a generic evidence-source label. Use opaque game/evidence IDs. Text visible in an image can still reveal identity; this is not an image-redaction feature. Local paths remain in the returned provenance but are not sent to either model.

## Result contract

Every successful run includes:

- All 25 pilot tags, each with its chosen state, **all four original probabilities**, Jev confidence, evidence IDs, decision model, and policy action.
- All 59 genre probabilities plus `insufficient_evidence`; the selected genre is `null` when that option wins. Genre decisions also include confidence, provenance, and policy action.
- Original evidence metadata, image SHA-256, factual observations, observer-returned model identifiers, requested observer/decision model, returned decision model, taxonomy/prompt versions, SDK versions, Jev token usage, and total/per-stage latency.

The four states are `present`, `absent`, `insufficient_evidence`, and `conflicting_evidence`. No fallback genre is injected. Invalid provider distributions fail explicitly; they are never filled, truncated, or normalized.

Decision `evidence_ids` identify the **complete evaluated context**, not provider-generated per-tag supporting citations. Each observation points to its source evidence. A `metadata_quote` additionally carries its exact source key; a quoted genre remains an attributed claim, not a confirmed visual fact.

## Observer boundary

The real provider uses a forced structured tool with separate `visual_fact` and `metadata_quote` kinds. Metadata quotations must exactly match the named source value. Known taxonomy labels, tag IDs, and common classification terms are rejected in visual facts, including when using an injected observer. Extra structured fields such as `genre` or `tags` are rejected.

This is a conservative lexical guard plus prompting, not a guarantee that every paraphrase is factual. Novel synonyms and subtle inference require benchmark review. Single-image prompting forbids temporal claims: one still cannot establish that a shield was raised immediately before a strike. Clip-based observations are a future milestone.

## Live Jev validation

```bash
python scripts/jev_smoke.py
pytest -m live -s
```

The smoke test runs all 26 questions against `jev-latest` and prints every distribution. The live test skips only when `TYPESAFE_API_KEY` is absent; with a key, API errors fail the test. Offline tests also execute the real SDK serialization and response parser with a mocked HTTP transport.

See [Jev integration findings](docs/JEV_INTEGRATION.md) for what was verified and what still needs authenticated validation. The initial implementation environment had no Jev or Anthropic credentials.

The development API still offers `/health` and `/taxonomy` (`uvicorn gametagger.api.main:app --reload`). Single-case analysis is exposed through the CLI; this milestone does not publish a hosted service.

See [architecture](ARCHITECTURE.md), [project rules](AGENTS.md), and [roadmap](ROADMAP.md).
