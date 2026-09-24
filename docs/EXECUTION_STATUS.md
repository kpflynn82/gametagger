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
