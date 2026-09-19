# GameTagger continuation: ordered media and trustworthy scorecards

The existing local website was extended, not restarted. This continuation delivers a real ordered-frame Observer adapter tested with mocked SDK transport, a durable saved-observation replay workflow, and case-based Jev Impact quality views. It does not establish live recognition accuracy or Jev superiority.

## Revisions and delivery

| Item | Revision / status |
| --- | --- |
| Current main (unchanged) | `1a928d600239a5343153d3df3eb41dc9b71d8250` |
| Continuation start / reused PR #5 | `a71b1f5c171957d3f7cc1cdc0a6fd05e85d3a1a3` |
| Ordered-media application source | `46abdee02ec154615e5b882be8bd8f94363cd530` |
| [PR #6](https://github.com/kpflynn82/gametagger/pull/6) delivery | `7300362ceba77edec2db5c25ab2a8897e5c0625d`, `feat/ordered-observation-replay`, open |
| [PR #7](https://github.com/kpflynn82/gametagger/pull/7) application source | `7d1bcca943b2b9d0f141aeee8dd52f93588e66dd`, `feat/paired-attribute-scorecards`, open |
| Review / merge | Author self-review only. No independent approval and no merge. |

PR #7 adds this documentation checkpoint after its application source. Its head is the exact delivery revision; the final task response records that SHA without embedding a commit's own hash inside itself. Review order is #4 → #5 → #6 → #7; each stacked diff is separately reviewable. PR #6 Python/website CI passed on its exact delivery head. PR #7 checks validate the pushed delivery head. No required review was claimed or bypassed.

Current main, open PRs/branches, clean working state, instructions, full saved brief, architecture, roadmap, relevant source/taxonomy documents and CI were inspected first. The earlier full brief remains at `docs/CODEX_BUILD_PLAN.md`; no separate newer attachment was exposed in this request. No existing work was overwritten. The original local-website handoff is archived at [session-reports/2026-09-19-initial-workspace.md](session-reports/2026-09-19-initial-workspace.md).

## Working website and new interactions

Overview, Analyze, Results, Catalog/History, Taxonomy, Review/Bulk Intake, Roadmap, Settings and Jev Impact remain operational. The local workspace retains private SQLite persistence, bounded uploads/jobs, versioned human corrections, filters, reopening and scoped JSON/CSV exports. The original light neutral design remains platform-neutral.

For an associated local clip, Results now exposes an exact-window manifest and reviewer-only saved-observation import. Matching replay creates an immutable child run with per-window valid/error/not-evaluated states; selecting a statement seeks its source timestamp. Changed assets, frame hashes, order, prompts, request/model binding or taxonomy are rejected. Reload/idempotency/reopening/export are tested. Imported observations are visibly unverified, and a matched hash is not provider authentication. No genre, tag probabilities or support links are fabricated.

The real Anthropic multi-image adapter passes bounded, exact frame bytes through the installed SDK. Still facts, literal UI text and sampled sequence changes remain distinct. It rejects cross-window timing, unknown references and taxonomy conclusions, and preserves returned/requested models, prompt/schema hashes, reported usage and independent errors. Live calls are disabled by default and unavailable through the website. Synthetic tests establish transport/contracts, not actual-game temporal accuracy. Sampling remains uniform; meaningful-scene selection and finer timing coverage are not implemented.

Jev Impact now accepts detailed paired case records (`paired-report-v2`) and reuses the evidence-supported metric implementation. It shows accepted attribute precision alongside end-to-end recall, raw errors and counts, four-state Brier/reliability, separate game-truth recovery and genre confusion counts. Null primaries cannot become correct/useful through contradictory summary flags, including in cost-per-useful-result calculations. Invalid distributions remain errors. Missing labels and empty denominators stay null. Source repair, Observer separation, Jev increment and end-to-end effects are explicitly distinguished; a Jev-increment claim requires identical observations/criteria and declared conventional→Jev roles.

The actual installed scorecard remains **Inconclusive / Not measured** because no compatible reviewed pilot exists. Illustrative reports cannot compute real effects. Matched-coverage sweeps, game-clustered uncertainty, fuller stage traces and the actual clean evaluation remain pending; the quality page does not pretend a single operating point is a curve.

## Tests and artifacts

Final application checks: **245 Python tests passed, one paid live test skipped; nine frontend tests and seven Chromium browser workflows passed.** Python lint/format, frontend lint/type checks and both builds passed. One upstream Starlette/AnyIO deprecation warning remains. Browser checks cover original flows plus synthetic video → manifest → rejected import → accepted replay → seek → reload → original preserved, and unavailable/illustrative quality views. The filmstrip overflow found in visual inspection was fixed; desktop and phone page widths now have explicit assertions.

Commands run:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
uv build --offline
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
cd frontend && npm run test:browser
```

The Python build used the existing task cache after a dependency-network lookup was unavailable; the offline build succeeded. No tests were weakened to conceal failures. A catalog browser selector was scoped to its own project after the new replay fixture created a second valid two-run project. No paid integration test ran on key presence alone.

Environment remains macOS arm64, Python 3.11.14, Node 26.0.0/npm 11.12.1, FFmpeg 8.0.1, TypeSafe SDK 0.7.0 and Anthropic SDK 1.7.0; CI uses Python 3.11/Node 22 and installs FFmpeg for both test jobs. No live model was invoked or resolved. New prompt: `ordered-observer-v1`; existing single-image and Jev prompts are unchanged.

Screenshots (synthetic or unavailable-state UI evidence only): [video desktop](screenshots/video-replay-desktop.png), [video phone](screenshots/video-replay-phone.png), [quality desktop](screenshots/quality-desktop.png), [quality phone](screenshots/quality-phone.png). Earlier Overview/Result/flow captures remain in the same directory. Browser reports/traces are in ignored `frontend/playwright-report/` and `frontend/test-results/`, plus CI artifacts. No raw private media/source packs were published.

The preserved 257-file experiment inventory was hash-verified again. Taxonomy SHA-256 remains `d91cc6c46ea998911dee8e9657d59cc1a4d8ebb1affe7aac84d7219acda0067b`. Offline readiness output is `/Users/kpflynn/Documents/Codex/2026-09-18/ope/work/continuation-readiness-20260919`: **0 checked cases, 0 human-reviewed references, 30 not assembled, 0 paid calls**. This is data availability, not model failure or accuracy. Original legacy labels/results/database and older repositories were not changed.

## Startup and remaining gates

```bash
cd /Users/kpflynn/Documents/Codex/Gametagger
GAMETAGGER_LOCAL_ROLE=reviewer ./scripts/start_workspace.sh
```

Open **http://127.0.0.1:8000**. This is a private local preview, not a public deployment. Startup does not load `.env`; the server cannot enable model spending. See [LOCAL_WORKSPACE](LOCAL_WORKSPACE.md), [ORDERED_OBSERVATIONS](ORDERED_OBSERVATIONS.md), [METRICS](METRICS.md), [SECURITY_REVIEW](SECURITY_REVIEW.md) and the machine-readable roadmap.

New external-model calls: **zero**. Accuracy/coverage uplift, calibrated correctness, total-system speedup and cost savings versus the old product are **not measured**. No new human annotations or approved source identities were fabricated. Verified media rights/identities, actual human reference review, an explicit all-provider numeric call cap and independent PR review remain required. Production deployment/auth is outside this delivery.

Next runnable task: start the local reviewer workspace with the command above and inspect the saved-media and Jev Impact workflows. The next evidence task is one permitted, identity-checked pack with real human annotations; do not rerun or bulk-retag the original catalog while that is pending.
