# Run the local GameTagger website

Requirements: Python 3.11+, uv, Node 22+, npm. FFmpeg/FFprobe on macOS/Linux enable experimental local MP4 preparation; without them capabilities report it unavailable. This is a single-user local development application, not a production deployment or hosted authentication system.

```bash
cd /path/to/gametagger
uv sync --frozen --extra dev
npm --prefix frontend ci
npm --prefix frontend run build
GAMETAGGER_LOCAL_ROLE=reviewer ./scripts/start_workspace.sh
```

Open http://127.0.0.1:8000. Omit the role variable for the default viewer role. No `.env` is loaded, no remote source is fetched and no model is called. The server binds loopback, disables proxy-header trust, validates Host/Origin, and requires a same-origin custom header for writes. Never expose it through a tunnel/reverse proxy. The configured OS user is the local principal; another process with that user's access is trusted. Production multi-user authentication is not implemented.

The website supports Overview, Analyze, saved Results, Catalog/History, canonical Taxonomy, Review, Jev Impact, Roadmap, Settings and methodology. Choose Publisher project to explicitly associate owned media, Game/store reference for an unresolved record, or Explicit demo to isolate testing from workspace totals. References are stored only; no downloader/store connector is advertised.

## Offline behavior

Preparation validates and hashes multiple images or short local MP4s, persists project/run/asset versions, quotes supplied documentary text, and records actual stages. The terminal status is **partial** because recognition/classification were not executed. All 25 tag execution states are `not_evaluated`, with null semantic states and no fabricated distributions. Arbitrary uploads never receive unrelated canned predictions. No inference method is promoted by this build.

Reviewer-only actions record a version, local reviewer, reason, time and before/after value. Primary publication requires explicit identity association and a canonical genre. Attribute review also requires identity association. These are current catalog decisions, separate from immutable model/run inputs, and survive another run. Test automation's synthetic review records are isolated temporary fixtures, not real human labels.

History counts runs separately from projects. One project currently represents one release/platform scope; cross-project canonical-game deduplication and multiple releases under one game are later work. Search, paging, sorting, primary/family, reviewed attribute present/absent, platform, input, date and review filters are supported. An unknown attribute never matches a present/absent filter. JSON/CSV exports redact original text/media, internal paths and review text; CSV neutralizes formula prefixes. The local evidence viewer is owner-scoped.

## Persistence and recovery

Default private storage is `.local/`, ignored by Git: SQLite `workspace.sqlite3`, original assets and re-encoded image previews, immutable per-run video frame directories, and optional `reports/`. Set `GAMETAGGER_DATA_DIR` to an absolute private directory to change it. Schema v1 initializes on first explicitly enabled start, or with `python scripts/migrate_workspace.py --data-dir /private/new-workspace`.

One worker, at most ten queued/active jobs, 30 new jobs per minute, idempotency keys bound to unchanged inputs. Page refresh recovers persisted job state. Process restart marks incomplete jobs `interrupted`; prepare a new run explicitly. Cancellation is checked between local stages; an active decoder finishes or hits its hard limit first. No remote charge exists here; future live cancellation must not imply that a provider stopped billing. Do not run two server processes against one workspace: leases for multi-process deployment are not implemented.

Limits: eight assets/project; nonanimated PNG/JPEG/WebP <=5 MiB, <=24 megapixels and 8,000 pixels per side; MP4 <=40 MiB/60 seconds/1080p-area, one supported video stream; 1 GiB local media quota with a conservative frame-output reserve; 100-row CSV/JSON dry runs; 1 MiB structured requests. Uploads use safe generated filenames, content decoding, original byte hashes, private storage and sanitized image previews. No arbitrary URL fetch. FFmpeg/FFprobe use local-file protocols, disabled external data references, one thread, fixed timeout, allocation/CPU/file/descriptor limits, plus Linux address-space limits. macOS has no equivalent hard address-space cap in this implementation; do not expose the decoder as a public upload service.

Video strategy `uniform-three-ordered-windows-v1` samples the start, midpoint and end, at most 5 Hz and 48 frames. Frames retain decoder presentation timestamps and content hashes. This is uniform sampling, not automatic meaningful-scene detection. `OrderedObserver` is an injectable contract; a real temporal observer is **not implemented/validated**. Menus, cinematics and overlays remain unreviewed context. The video player can seek to actual sampled frame times. Synthetic tests validate transport, selection and timestamp integrity only.

## Replay and comparisons

```bash
uv run --frozen gametagger-eval --manifest experiments/clean30/manifest.json --output /tmp/new-readiness-run
```

This produces an availability report and per-case ledger where artifacts exist. The checked manifest stays empty until independently verified packs exist. `experiments/clean30/candidate-intake.json` lists 30 **planning candidates**, with provisional development/holdout grouping and every identity/right/reference pending. Names are suggestions, not verified source mappings; final groups must prevent franchise/asset leakage before any outcomes are viewed.

For a private matched comparison, supply `workspace.experiments.MethodRecord` JSON files exported from checked runs:

```bash
uv run --frozen python -m gametagger.workspace.experiments \
  --baseline /private/baseline.json --candidate /private/candidate.json \
  --output .local/reports/comparison-v1.json
```

Outputs are exclusive-create; never overwrite a frozen report. `/experiments` validates/recomputes saved reports and exposes only typed fields. Both methods use one frozen cohort; mismatched inputs produce unavailable effects. The report schema is `experiments/paired-report.schema.json`. Store code/model/prompt/crosswalk/hardware/cache/concurrency/mode versions in the method version and conditions; preserve per-request details with the source benchmark artifacts. Unknown cost and usage remain unknown. The default scorecard is empty; the separately labelled 100-row historical ledger is not pooled into it. Clean paired attribute scorecards/curves and statistical uncertainty remain pending checked data and report adapters.

The hierarchy remains the reference production method. `direct_genre_spec` prepares the fixed 101-option Jev alternative; `SavedObservationClassifier` and `SavedPrediction` accept a non-Jev saved comparator without manufacturing probabilities. No conventional live provider or direct live experiment is executed. Source/evidence/Observation/decision interfaces remain separate.

## Tests and contracts

```bash
uv run --frozen pytest -q
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv build
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
cd frontend && npx playwright install chromium && npm run test:browser
```

Browser tests start an isolated localhost server and temporary database; stop any preview on port 8000 first. Test images/footage are synthetic and unrelated to any game benchmark. Browser reports/screenshots are in `frontend/test-results/` and `frontend/playwright-report/` (ignored). Checked delivery screenshots are in `docs/screenshots/`. Frontend types derive from backend OpenAPI: run `python scripts/export_workspace_schema.py`, then `npm --prefix frontend run types` and format/check changes. CI verifies generated type drift.

No live test runs on keys alone; the explicit live opt-in remains required. No new billable call is authorized for this session. A numeric cap and a reviewed spend ledger/executor are still needed before enabling a website live path. Existing CLI/manual smoke tools are separate developer surfaces, not the budget-disabled website.

To reproduce the public historical ledger from the preserved private snapshot, use `python scripts/export_legacy_ledger.py --snapshot /private/genre-evaluation-100 --manifest experiments/legacy100/manifest.json --output /private/new-redacted-ledger.json`. It verifies the complete immutable inventory first and writes an allowlist of IDs, decisions and hashes only. The checked ledger was reproduced exactly; never publish the original source pack.
