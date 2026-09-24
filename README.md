# GameTagger v2

GameTagger classifies video game evidence across **PC, console, and mobile**. The local, platform-neutral vertical slice now uses [Genre Taxonomy v4.1](docs/GENRE_TAXONOMY_V4_1.md):

```text
EvidenceItem → Observer → Observation[] → Jev → Policy → AnalysisResult
```

The observer describes visible facts. Jev interprets them against the canonical VGMS taxonomy. Application policy decides whether to accept a decision, acquire evidence, or request review. A feature that is not observed is never automatically marked absent.


## Local website

A responsive, private workspace is available in this repository: Analyze → saved result → review → catalog/history/export, plus Taxonomy, Jev Impact and Roadmap. Live inference is budget-disabled; arbitrary uploads receive explicit not-evaluated states, not canned classifications.

```bash
uv sync --frozen --extra dev
npm --prefix frontend ci
npm --prefix frontend run build
GAMETAGGER_LOCAL_ROLE=reviewer ./scripts/start_workspace.sh
```

Open **http://127.0.0.1:8000**. See the [local runbook](docs/LOCAL_WORKSPACE.md), [measurement contract](docs/METRICS.md), and [execution status](docs/EXECUTION_STATUS.md). This is a working local application, not a public deployment or a newly validated model experiment.

## Rich Genome mode

`gametagger-genome` asks Jev about 189 attribute tags plus the v4.1 genre hierarchy. It reads
store pages (Steam, App Store) and Wikipedia by exact ID, including store screenshots and
trailers sampled into short frame bursts. It can use YouTube's API as a trailer backup. It
defaults to a dry run that makes no model calls; live runs need `--live`. See [rich Genome mode](docs/GENOME_RICH_MODE.md)
for why the pilot path returned few tags and how to run it.

```bash
gametagger-genome fixtures/genome/hollow_orchard.dossier.json            # dry run
gametagger-genome fixtures/genome/hollow_orchard.dossier.json --offline  # pipeline check with mocks
```

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

This prints the complete JSON result. Offline mode explicitly uses `mock-observer-v1` and `mock-jev-v1`, marks the run `offline: true`, and assigns all probability to `insufficient_evidence` for eligible mock questions. It exercises serialization, provenance, and policy; it is **not model inference**. The mock observer quotes supplied metadata and accepts injected visual facts in Python tests. It never invents image observations.

## Analyze a real image

Set `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY` in your process environment. Choose a vision-capable Claude model enabled for your account using `OBSERVER_MODEL` or `--observer-model`. No key is accepted as a CLI argument, and no credentials belong in source, fixtures, or results.

```bash
gametagger --image /path/to/screenshot.png \
  --metadata /path/to/metadata.json \
  --observer-model YOUR_CLAUDE_VISION_MODEL \
  --game-id case-001 --game-title "Example game"
```

For a key that is not scoped to one Anthropic workspace, also set `ANTHROPIC_WORKSPACE_ID`
from Claude Console → Settings → Workspaces. The observer sends it in the
`anthropic-workspace-id` header; workspace-scoped keys can omit this setting.

Metadata is an optional JSON object with string values. The Anthropic adapter sends the image and metadata to Anthropic; factual observations are then sent to TypeSafe. Image input is a single local PNG, JPEG, WEBP, or nonanimated GIF, at most 5 MiB and 8000 pixels per side. The website additionally supports bounded local MP4 preprocessing; an ordered-frame Observer adapter is offline-tested, while live recognition quality and remote URL adapters remain pending.

`.env.example` is a template. Nothing loads `.env` implicitly. If you store credentials in an ignored local `.env`, explicitly load them into the command environment, for example `uv run --env-file .env gametagger ...`. The live integration test follows the same environment rule.

`--blind-media` removes title and metadata before observation and classification and uses a generic evidence-source label. Use opaque game/evidence IDs. Text visible in an image can still reveal identity; this is not an image-redaction feature. Local paths remain in the returned provenance but are not sent to either model.

## Result contract

Milestone 2 PR A adds [source-identity eligibility and isolated execution](docs/PR_A_SOURCE_INTEGRITY.md).
Library analysis requires an approved source manifest or an explicit uploaded-project association.
The image CLI associates user-supplied files with `--project-id` (defaulting to the local case ID).
Imported source associations remain unverified until reviewed; unrelated sources are excluded
before classification. PR B adds [evidence policy and trustworthy measurement](docs/PR_B_MEASUREMENT.md) while keeping the taxonomy fixed.

Every successful run includes:

- Execution status for all 25 pilot tags. Each valid answer includes its chosen state, **all four original probabilities**, Jev confidence, evidence IDs, decision model, and policy action.
- Raw probabilities across 14 families plus insufficient evidence, per-family conditional genre distributions, and a normalized global ranking across 100 eligible genres plus insufficient evidence. One stable-ID primary and up to two secondary genres are retained; insufficient evidence leaves the primary null. See the [v4.1 contract](docs/GENRE_TAXONOMY_V4_1.md) for field names and selection rules.
- Original evidence metadata, image SHA-256, factual observations, observer-returned model identifiers, requested observer/decision model, returned decision model, taxonomy/prompt versions, SDK versions, Jev token usage, and total/per-stage latency.

The four states are `present`, `absent`, `insufficient_evidence`, and `conflicting_evidence`. No fallback genre is injected. Invalid provider distributions fail explicitly; raw provider values are never filled, truncated, or normalized. Global genre probabilities are derived from normalized copies of the family and conditional distributions.

Partial runs retain valid tag answers and every question's execution status. `genre: null` with an
execution error means computation was incomplete; it is different from a valid genre result whose
`primary_genre` is null for insufficient evidence. Check `execution.questions`, `genre_execution`,
and the identity audit before consuming results. Failed questions alone receive bounded retries.

Decision `evidence_ids` identify the **complete evaluated context**, not provider-generated per-tag supporting citations. Each observation points to its source evidence. A `metadata_quote` additionally carries its exact source key; a quoted genre remains an attributed claim, not a confirmed visual fact.

## Observer boundary

The real provider uses a forced structured tool with separate `visual_fact`, attributed `visual_text`, and `metadata_quote` kinds. Metadata quotations must exactly match the named source value. Known taxonomy labels, tag IDs, and common classification terms are rejected in visual facts, including when using an injected observer. Extra structured fields such as `genre` or `tags` are rejected.

This is a conservative lexical guard plus prompting, not a guarantee that every paraphrase is factual. Novel synonyms and subtle inference require benchmark review. Single-image prompting forbids temporal claims: one still cannot establish that a shield was raised immediately before a strike. The [ordered-window adapter and saved replay](docs/ORDERED_OBSERVATIONS.md) extend factual observation to bounded clips; temporal recognition quality remains unvalidated.

Literal screen text has a normalized bounding region and remains a transcription; it cannot alone support a genre or feature conclusion. `support_links` are separate reviewed attributions; context evidence IDs and a high-confidence `accept` do not by themselves make a result publishable.

## Offline benchmark replay

```bash
gametagger-eval --manifest experiments/clean30/manifest.json --output /tmp/gametagger-readiness
```

This validates saved artifacts only; it makes no model calls. See the [manifest contracts and metrics](docs/PR_B_MEASUREMENT.md) and [preserved 100-record audit](docs/LEGACY100_EVIDENCE_AUDIT.md). The clean benchmark currently has zero checked packs or human-reviewed labels; 30 are planned.

## Live Jev validation

```bash
python scripts/jev_smoke.py
GAMETAGGER_RUN_LIVE=1 pytest -m live -s
```

The smoke test is an explicit reference experiment and runs 25 tag questions plus hierarchical
genre questions. Live tests require both `GAMETAGGER_RUN_LIVE=1` and `TYPESAFE_API_KEY`; a key alone
never triggers them. Offline tests execute SDK serialization and parsing with mocked HTTP transport.

See the [Milestone 1 integration record](docs/JEV_INTEGRATION.md) for historical live checks and
the [v4.1 contract](docs/GENRE_TAXONOMY_V4_1.md) for the unchanged hierarchy. PR A uses offline
regressions and saved-response replay; no new live provider validation was performed.

The development API still offers `/health` and `/taxonomy` (`uvicorn gametagger.api.main:app --reload`). Single-case analysis is exposed through the CLI; this milestone does not publish a hosted service.

See [architecture](ARCHITECTURE.md), [project rules](AGENTS.md), and [roadmap](ROADMAP.md).
