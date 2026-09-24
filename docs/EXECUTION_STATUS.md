# Benchmark qualification checkpoint

This task started from clean main `8db462445b57e02d8c398ca2931db6a214c5de95`. PRs #4 → #5 → #6 → #7 were already merged, in that order, with passing final-main CI. There is no open stack to rebase; merged history is preserved. The owner explicitly waived independent review when instructing “merge PRs”; checks and repository protections still apply.

[PR #8](https://github.com/kpflynn82/gametagger/pull/8), branch `fix/benchmark-qualification`, fixes mode-specific human-reference readiness and introduces `clean30-qualification-v1`. Tested application source: `50dd28ee5a6cb537840cbd24ec976a24d41776c3`. The documentation checkpoint follows that source; the PR identifies the exact delivery head and both push-head and PR-integration CI runs. No new merge is requested in this task.

Qualification requires the full 30-case, ≥10-mobile-first, 6-development/24-holdout pilot, all required evidence modes, approved identity, permitted verified assets, usable observation bundles, complete human references and recorded method×mode prediction cells. Partial readiness remains separate. Valid provider-failure records remain in denominators; qualification does not mean model success or authenticate supplied human-review declarations. The precise reference and failure-code contract is in [PR_B_MEASUREMENT](PR_B_MEASUREMENT.md#clean-pilot-qualification).

Local checks: **273 Python tests passed, one paid live test skipped; lint, formatting and offline package build passed**. Synthetic fixtures cover the requested six cases and additional missing/invalid dependencies. One upstream Starlette/AnyIO deprecation warning remains. Frontend/browser code is unchanged and still runs in both CI paths. Author review only; no paid model calls, taxonomy changes, original database writes or Jev Impact features.

Real readiness replay: `work/clean30-qualification-20260919-final` in the private task workspace. `benchmark_qualified` is **false**: zero assembled cases, zero human-reviewed references, zero saved predictions; target 30 cases / 180 method×mode prediction cells. Existing metrics remain visible and do not qualify this empty pilot. No labels or real game assets were fabricated.

The machine-readable roadmap is a saved snapshot, not a runtime heartbeat. Earlier implementation details remain in SESSION_REPORT; its pre-merge branch statuses are historical. Next substantive task: assemble the first permitted, identity-checked evidence pack with actual human-reviewed game-truth and per-mode support labels. Missing assets/rights/review stay pending. Do not add more Jev Impact features or run paid experiments while preparing that pack.

## Duplicate-game correction and development intake

PR #8 now rejects duplicate canonical game IDs within either split before replay, retains all cross-split leakage checks, and uses distinct canonical games for cohort/mobile/split qualification counts. Raw records and unresolved identities remain visible separately. Regression coverage includes both splits, mobile-minimum inflation, unknown IDs and the valid 30-distinct-game cohort. The 24 holdout candidates and frozen taxonomy are unchanged.

Parallel evidence assembly is limited to the existing six development subjects. The first target is Factorio. Private packets and actual assets live in `work/clean30-development` in the task workspace; no media is published into the repository. Documented publisher press/review permissions must not be promoted to benchmark/provider-processing permission. Proposed metadata/labels and pending rights/release facts remain separate from actual human approvals. Zero human approvals or paid experiments are claimed. The task handoff records the finished review packet and exact remaining decisions.

## Rich Genome mode (September 24, 2026)

The owner asked for richer Jev tagging. An offline diagnosis of the pilot path at `687d0b2` found
that store or description text reached Jev for no attribute tag, that 8 of 25 tags were never asked,
and that one taxonomy word in an Observer sentence failed the whole run. Branch
`claude/focused-hypatia-dyrxiz` adds `gametagger-genome`, which asks 189 tags (25 frozen pilot +
164 extended from the owner's original glossary) plus the unchanged genre hierarchy over attributed
text claims and screenshot facts. `vgms_v4.yaml`, the pilot pipeline, experiments and website are
unchanged. Offline tests only; no paid or live calls were made, and live quality, cost and latency
remain unmeasured. See [GENOME_RICH_MODE](GENOME_RICH_MODE.md). Next step: a small live comparison
against the original site's tags once the owner sets a budget.

### Rich mode media (September 24, 2026)

At the owner's request, rich mode now reads Steam and App Store pages by exact ID. It downloads
their screenshots and store trailer, and samples trailers into short frame bursts. Timing
attributes can therefore use `gameplay_clip` evidence. Cinematic and title-card bursts are left
out. The YouTube backup uses the Data API only, as the owner chose: it records a reference and
YouTube's published stills, and downloads no video. Google Play is a link-only slot until the owner
chooses a data service. The shared image loader no longer crashes on JPEG input, and ordered
windows accept source videos up to 30 minutes (website uploads keep their 60-second limit).
Offline tests only; no live provider, store or YouTube request was made. See
[GENOME_RICH_MODE](GENOME_RICH_MODE.md).

### Next: Jev versus previous-method benchmark (handoff, September 24, 2026)

The owner wants 100 games compared: the top 50 Steam games by concurrent players and the top 50
mobile games by grossing. The comparison is rich mode (Observer + Jev) against the original site's
single Claude call, on identical inputs. It should measure timing per stage, tokens, cost, tags per
game and accuracy, and end with charts and a short social-media write-up. Every figure must state
its sample, date and answer-key method.

Owner actions taken: API keys were added to the environment as `TYPESAFE_API_KEY`,
`ANTHROPIC_API_KEY`, `ANTHROPIC_WORKSPACE_ID` (if needed) and `YOUTUBE_API_KEY`, and network
access was requested for `api.typesafe.ai`, `api.anthropic.com`, `store.steampowered.com`,
`api.steampowered.com`, `steamstatic.com`, `en.wikipedia.org`, `itunes.apple.com`, `mzstatic.com`,
`www.googleapis.com` and `i.ytimg.com`. In a new session, first verify that each variable name
exists (never print values) and that each host is reachable.

Still needed from the owner before any paid run:
- A numeric spending limit. Estimates for one 100-game pass: vision Observer on Claude Sonnet 5
  about $8-10; previous method about $2 on Haiku 4.5 (standard) or about $9 on Opus 4.8 (deep);
  Jev about 3.3M input tokens at the owner's TypeSafe rate. Suggested: a $40 Claude cap plus a
  Jev cap, and a 10-game pilot first.
- The top-50 mobile grossing list (rank, name, App Store ID and/or Google Play package; chart
  region, platform and month). No reliable free official grossing source is known.
- The answer-key method. Recommended: a blind human primary genre for all 100 games plus about
  20 tags on about 30 games. Steam community tags are a cheaper, weaker PC-only option.
- Previous-method mode: Haiku standard, Opus deep, or both (recommended: both).
- Confirmation that non-game Steam chart entries (for example Wallpaper Engine) are skipped.

To build, none of which needs keys:
- A faithful adapter of the original `gametagger-web` tagger prompt (the decisions/legacy.py
  placeholder), run on the same dossier.
- A Steam most-played chart reader.
- A batch runner recording per-stage wall clock, tokens and cost.
- An old-59-to-new-100 genre crosswalk for the owner to approve.
- Scoring, charts and a write-up template.

### Benchmark tools built (September 24, 2026)

The owner decided the open questions. The spending limit is **$40 in total**. Mobile games come
from AppBrain's Google Play top-grossing games chart (US). Accuracy is judged by Steam user tags
plus the owner's own blinded review. The previous method runs on both Haiku 4.5 (standard) and
Opus 4.8 (deep). Steam non-games are skipped and listed.

`gametagger-compare` is built. See [JEV_VS_LEGACY_BENCHMARK](JEV_VS_LEGACY_BENCHMARK.md) for
steps, outputs and caveats. Its parts:

* chart readers and a frozen 100-game cohort (`experiments/jev-vs-legacy/cohort.json`, charts of
  2026-09-23 and 2026-09-24)
* exact-ID identity through Wikidata
* a Steam user-tag answer key
* shared dossiers, with a new Google Play listing reader that includes the store's MP4 trailer
* a faithful adapter of the original tagger (`decisions/legacy.py`, verbatim prompt and rules
  from `gametagger-web@4b710fd`)
* a budget-capped runner with per-stage timing, tokens and list-price cost
* draft crosswalks in `taxonomy/crosswalks/`
* scoring, a blinded review sheet, and an HTML report with a social card

Environment findings:

* The TypeSafe key was accepted by the free model-listing call; `jev-latest` is `jev-1.13.0` at
  $0.042 per million input tokens.
* The YouTube key works.
* `ANTHROPIC_API_KEY` is not visible to the agent here. The tools also read
  `GAMETAGGER_ANTHROPIC_API_KEY`, which the owner has added; a new session picks it up.
* After the owner widened network access, every needed host was reachable. Wikimedia
  rate-limits this shared address heavily, so identity and Wikipedia fetches wait and retry.
* `ffmpeg` must be installed in each session.

The only paid call so far is one live Jev check on Stardew Valley's text: 185 questions in 6 requests, 4.0 seconds, $0.0019. No Claude call has been made. Next step, in a session that can see the key: run `dossiers`, then a
10-game pilot, then the full run and `report`, all under the same $40 ledger.

### Benchmark run attempt (September 24, 2026): blocked on Anthropic credit

* The new Anthropic key (108 characters) is accepted by the free model-listing call once the
  `anthropic-workspace-id` header is sent; `ANTHROPIC_WORKSPACE_ID` is set and the tools send it.
  Haiku 4.5, Opus 4.8 and Sonnet 5 are all listed.
* Steam changed its store API: `appdetails` sometimes files its reply under another ID (a DLC or
  package), so most Steam games read as unlisted. Fixed: a reply is accepted only when its own
  `steam_appid` matches the requested game. Dossiers were rebuilt from scratch after the fix.
* The 10-game pilot was refused on every Claude request with "Your credit balance is too low to
  access the Anthropic API". Nothing was billed (30 zero-cost error rows in the ledger; the failed
  results were deleted so they are re-run). The runner now stops the whole run on this message
  instead of booking every remaining game as a failure.
* **Owner action:** add prepaid credit to the Anthropic organization that owns this key
  (Console → Plans & Billing), then re-run the pilot with `--budget-usd 39.99`.
