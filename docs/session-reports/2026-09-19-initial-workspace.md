Historical handoff before the ordered-observation/paired-scorecard continuation. See [current report](../SESSION_REPORT.md).

# GameTagger — bounded product build handoff

The result is a working **local** website with durable evidence preparation, review/history/export, and an artifact-backed Jev Impact view. It is not a newly validated live classifier or a public deployment. The minimum coherent website slice is delivered; real temporal recognition and clean quality evaluation remain pending.

## Revisions and review

| Item | Actual revision / state |
| --- | --- |
| Starting main | `1a928d600239a5343153d3df3eb41dc9b71d8250` |
| Reused measurement PR #4 | `914678c63c218b13698dce208db8b07f3c75e8e8`, open and unmerged |
| Initial website commit | `04c8bcdc88f8c5701b83a8c7832ba6070decae63` |
| Final application source | `d8bf3fedf58bccb1ca1e136a42c358c55cc13c47` |
| Delivery branch | `feat/local-product-workspace` |
| Website PR | [#5](https://github.com/kpflynn82/gametagger/pull/5), stacked on #4 |
| Reviews / merges | Author self-review only; no independent approval and no merge |

The final documentation commit contains this report and the status snapshot; it does not change the application. The PR's head SHA is the delivery revision to pin for review/merge. The final task response records that exact delivery SHA without trying to embed a commit's own hash inside itself.

GitHub [Python](https://github.com/kpflynn82/gametagger/actions/runs/35432545183/job/105869589847) and [website](https://github.com/kpflynn82/gametagger/actions/runs/35432545183/job/105869589963) jobs passed on the final application source `d8bf3fedf58bccb1ca1e136a42c358c55cc13c47`. The current PR checks validate each subsequent head. Passing CI and author review do not substitute for independent review. Main, the older repositories, the legacy database and deployed product were not changed. The deployment inventory was empty before publishing the feature branch; only the Checks workflow was present.

## Website and operation

The new warm off-white/graphite/indigo workspace implements Overview, Analyze, Result, Catalog/History, Taxonomy, Review, Jev Impact, Roadmap, Settings and methodology. It supports publisher project association, unresolved game/store references, an isolated explicit demo path, attributed metadata, multiple local images, short local MP4s, real persisted job stages, saved partial results, current catalog approvals, versioned corrections, filters/pagination/sorting, scoped JSON/CSV exports, and bounded CSV/JSON intake validation.

A fresh offline image never receives another game's canned tags. Image recognition and classification are **not evaluated**, so model states/probabilities stay null. An approved human catalog primary is displayed separately and survives a new run. The automated review example in screenshots belongs only to synthetic UI test data; it is not a fabricated human game label.

The local backend is a modular FastAPI service with schema-v1 SQLite, private file storage, one bounded worker, idempotency, restart interruption recovery, role/owner checks, loopback/Host/Origin enforcement, same-origin writes, request/media limits, content decoding, formula-safe CSV and redacted default exports. Original provider interfaces remain; the website's live path fails closed regardless of key presence. The implementation does not provide production authentication, a multi-process queue or a public deployment.

Startup after setup:

```bash
GAMETAGGER_LOCAL_ROLE=reviewer ./scripts/start_workspace.sh
```

Open **http://127.0.0.1:8000**. This is localhost, not a public site. Full setup/recovery/export instructions are in [LOCAL_WORKSPACE](../LOCAL_WORKSPACE.md). No `.env` is loaded by this command. Private files default to ignored `.local/`.

Visual checks covered 1440, 768 and 390-pixel layouts, visible focus and mobile navigation. Captures are [desktop overview](../screenshots/overview-desktop.png), [phone overview](../screenshots/overview-phone.png), [tablet](../screenshots/overview-tablet.png), [result](../screenshots/result-desktop.png), [phone result](../screenshots/result-phone.png), [old/new flows](../screenshots/pipelines-desktop.png), and [shared-observation comparison](../screenshots/experiments-desktop.png). Browser automation also exercised controls and downloads; compilation alone was not treated as visual verification. No accessibility certification is claimed.

## Media and evaluation status

Image intake validates exact bytes, deduplicates, hashes and serves sanitized previews. Local MP4 processing enforces byte/duration/dimension/decoder limits and samples three ordered windows across the timeline, preserving actual presentation timestamps and hashes. Frame files belong to individual runs; reanalysis cannot overwrite a past run's pointers. The player can seek to these timestamps. Synthetic video tests cover the upload → processing → saved frames → retrieval path and timestamp/hash consistency.

`OrderedObserver` defines an injectable temporal input contract. A real ordered-video observer, meaningful-scene selection and temporal gameplay accuracy remain **unimplemented/unvalidated**. Uniform windows at up to 5 Hz cannot establish every timing mechanic. The existing single-image Observer remains separate from classification, with literal attributed text and documentary quotes distinguished from inferred conclusions.

The 14-family/100-genre/25-tag taxonomy is byte-for-byte unchanged (SHA-256 `d91cc6c46ea998911dee8e9657d59cc1a4d8ebb1affe7aac84d7219acda0067b`). Strict probability validation was not loosened. The original 257-file experiment inventory passed hash verification again; all 100 records and original labels remain historical annotations. The public ledger contains allowlisted numeric IDs/decisions/hashes only and was exactly reproduced by `scripts/export_legacy_ledger.py`. Raw source contents remain private.

Jev Impact provides an honest empty scorecard, real historical counts and per-record errors/distributions, legacy/new and shared-observation flow controls, a saved paired-report reader and a conservative recommendation: **Inconclusive**. Compatible saved reports can show correctness, primary-only useful coverage, complete latency/cost and error measurements with counts; unavailable metrics stay null. Full per-tag paired scorecards/coverage curves/calibration charts and uncertainty estimates await checked data and report adapters. The typed report rejects incompatible cohorts/evidence/conditions, nonfinite costs/times and mislabelled illustrative data.

The existing manifest replay supports metadata-only/media-only/combined conditions and shared-observation saved non-Jev outputs. A direct 101-option experimental Jev specification is prepared against the unchanged definitions; hierarchy remains the reference. This is an interface/specification and offline fixture path, not a new paid comparison or conventional live deployment.

Thirty candidates are listed in `experiments/clean30/candidate-intake.json` as planning only. Verified release identities, media rights, assets, human primary references and evidence-supported/game-truth tags are all pending. The checked benchmark manifest still contains **zero assembled cases**. No artificial screenshots or model-memory approvals were used to fill it. Provisional split/grouping must be checked and frozen before any held-out outcomes are examined.

## Verification and measurements

Final local source checks: **213 Python tests passed, one paid live test skipped; six frontend tests passed; five Chromium browser workflows passed; Python and frontend lint/type checks and both builds passed.** npm audit reported zero known vulnerabilities. One upstream Starlette/AnyIO deprecation warning remains; it was not suppressed. Linux CI additionally exercises the decoder and browser contracts. The generated OpenAPI/TypeScript drift check is part of CI.

Commands used: `pytest -q`, `ruff check .`, `ruff format --check .`, `uv build`, `npm test`, `npm run lint`, `npm run build`, and `npm run test:browser`. Browser workflows cover submission/persistence/review/reanalysis/reopening/export, invalid files, partial states, historical errors, roadmap/taxonomy, both comparison flows, an empty report and a labelled illustrative saved report. Backend tests additionally cover owner/role boundaries, restart recovery, idempotency, upload caps, CSV injection, corrupt asset detection, revision conflicts, explicit identity and spend failures. Existing identity, taxonomy, literal-text, probability and retry regressions pass.

Environment: macOS arm64; Python 3.11.14; Node 26.0.0/npm 11.12.1; FFmpeg 8.0.1; FastAPI 0.141.1; Pydantic 2.13.5; Pillow 12.3.0; pytest 9.1.1; Ruff 0.16.8; Vite 7.3.6; Chromium 153 via Playwright. Locked provider SDKs: TypeSafe 0.7.0, Anthropic 1.7.0. No live model was invoked or newly resolved. Observer prompt remains `observer-v2-literal-text`; Jev prompt remains `jev-evidence-v1`; direct experimental prompt is `direct-genre-experiment-v1`.

The readiness replay was run without keys to `/Users/kpflynn/Documents/Codex/2026-09-18/ope/work/product-readiness-final`, producing a frozen manifest copy, case ledger and summary. It reports zero ready predictions, zero reviewed references, 30 packs still unassembled and zero paid calls. Browser reports are in ignored `frontend/test-results/` and `frontend/playwright-report/`; safe selected captures are committed. The original private stress suite remains at `/Users/kpflynn/Documents/Codex/2026-09-18/ope/work/genre-evaluation-100`.

The evidence shows functioning offline software, stricter publication/measurement boundaries and preserved failures. It does **not** establish better genre accuracy, tag recall, calibrated probabilities, live total latency or cost than the existing product. Agreement is not accuracy. The historical final-call timing is not an end-to-end speedup, and partial usage is not a bill. New external-model requests in this build: **zero**.

## Remaining gates and next action

Independent review is required for PRs #4/#5. A numeric all-provider spending cap, checked evidence rights/identities and genuine human labels are needed for a clean pilot. Production deployment/auth, a real ordered-video provider, full comparison chart adapters and additional source connectors remain separate work. The website, local persistence/media processing, replay and regression checks proceeded despite these gates.

Single next runnable task: start the local reviewer workspace with the command above and review the delivered flow. For the engineering continuation, use the current branch/PR and `docs/execution-status.json`; do not restart from the old scaffold, repeat the original 100-record run, or modify the legacy database.
