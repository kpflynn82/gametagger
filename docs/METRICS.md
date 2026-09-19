# Measurement interpretation contract

GameTagger has **no measured Jev uplift** from this session. The saved 100-row experiment is a descriptions-only intake stress suite with historical machine annotations. It is not a clean accuracy or vision benchmark, a bill, or an end-to-end speed comparison. Source-title flags are review referrals, not confirmed mismatches.

## Units and eligibility

Every ratio in `evaluation.metrics` carries a numerator, denominator and nullable value. The enclosing report binds method, mode, cohort/split, taxonomy/evidence/observation hashes and reference origin. `workspace.experiments.ComparisonReport` additionally records method versions, conditions, label version, input hashes, metric unit, per-side counts and measurement status. A saved report is recomputed on read. Declarations and hashes establish consistency, not independent verification or permission.

An eligible assigned game is the unit for primary metrics. A tag decision is the unit for per-tag precision; it is not an independent game for statistical uncertainty. Identity-excluded records remain in intake/operational counts. Quality scoring uses human-reviewed evidence-supported references; legacy keys and AI suggestions are not truth. Missing keys remain unknown. Invalid distributions are operational failures and cannot enter probability scoring.

| Measure | Numerator / denominator and scope |
| --- | --- |
| Actual primary correctness | Correct **emitted** primaries / all labelled identity-eligible cases assigned to the method, including failed, deferred and null outputs. |
| Emitted-primary accuracy | Correct emitted primaries / labelled emitted primaries. This selected subset is **not** end-to-end correctness. |
| Forced-choice candidate accuracy | Correct highest non-null candidate / labelled valid full distributions. Diagnostic only; null emitted primary never becomes correct publication. |
| Accepted-primary precision | Correct publishable primaries / labelled publishable primaries. Identity, evidence, attribution, contract and policy must pass. |
| Publication coverage | Publishable primaries / all assigned cases; report identity-approved selection separately. The saved paired-report `approved-primary-v1` useful-output contract uses its declared eligible assigned cohort. |
| Attribute precision | Correct accepted present claims / accepted present claims with reviewed evidence-supported labels. Unknown truth is excluded and reported, never counted false. |
| End-to-end attribute recall | Correct accepted positives / all positive reference claims in the identity-eligible assigned cohort, including failures and deferrals. Game-truth recovery and selected-asset-supported recovery are separate. |
| Accepted-only recall | TP / (TP + accepted FN). Explicitly subset-conditioned; never substitute for end-to-end recall. |
| Positive/negative coverage | Accepted decisions / positive or negative reviewed reference cases respectively. |
| Four-state accuracy | Correct valid states / valid human evidence-supported states. State abstention differs from execution failure. |
| Calibration/Brier | Multiclass sum of squared error across the four states / valid aligned reviewed distributions; reliability buckets retain sample counts. Not probability of game-wide feature existence. |
| Reliability | Completed, partial, failed and not-evaluated runs / all runs; first-attempt success / known first attempts; recovery / known retry outcomes. Per-question counts stay separate. |
| Evidence coverage | Eligible evidence, decided dimensions, and specifically attributed support counted separately. Prepared/evaluated context is not proof. |
| Review workload | Review referrals / all assigned cases (multiply by 100 for referrals per 100). Reviewer minutes remain unknown unless timed. |
| Latency | Actual queue-to-finish wall clock and separate stage/request spans. Local upload preparation excludes upload transfer and model inference. It is not a live system benchmark. |
| Cost | Complete all-provider/all-attempt accounting only. Token totals without complete rates/usage are not a bill. Cost per useful result is total complete cost / accepted results. |
| Throughput | Usable completions / observed elapsed wall time under declared resources and concurrency. Not inferred from one call's latency. |

No accepted predictions produces undefined precision. No positive reference labels produces undefined recall. Tags with missing legacy comparability still count all new semantic/execution outcomes. A 90%-unknown distribution with a correct 10% candidate has zero actual primary correctness when no primary is emitted; one accepted positive and 99 deferred positives has 1% end-to-end recall, even at 100% accepted precision.

## Matched comparisons and effects

Keep A (frozen legacy) → B (source repairs on the same classifier), B → C (separate Observer/conventional classification), C → D (same observations, Jev instead of conventional), and legacy → new end-to-end comparisons distinct. The production legacy version/media flags are unverified. No A→B change demonstrates Jev's incremental contribution.

Paired reports refuse effects when cohort/case IDs, exact evidence/observation hashes, taxonomy, conditions, or reference-label version differ. Conventional outputs may be categorical; never manufacture probabilities. Taxonomy crosswalks must be frozen in run conditions; broad legacy family labels cannot acquire invented leaf truth. The illustrative report mode is excluded from effects and from real aggregates.

Accuracy uplift is `100*(candidate - baseline)` percentage points. Relative error reduction is `(old_error-new_error)/old_error`, undefined at zero old error. Speedup is `old_total/new_total`; latency reduction is `1-new_total/old_total`; cost reduction is `1-new_total_cost/old_total_cost` with complete ledgers; coverage change is a percentage-point difference. The current UI reports direct differences with explicit units, not implied speedup ratios. Missing components stay unknown.

Median total latency in saved comparisons requires at least two matched complete samples; p95 uses nearest rank and requires at least 20. These are descriptive summaries, not claims of statistical reliability. Match hardware, cache/cold state, concurrency and repetitions in `conditions`. Overlapping stage durations must not be summed to replace wall clock. No paired confidence intervals or matched-coverage curves are claimed yet; these need sufficient checked cases. Future resampling must cluster by game and respect development/holdout boundaries.

## Current availability

- Original stress suite: 100 records retained, 97 completed, three terminal errors. All 2,425 completed tag outcomes are counted; only 498 legacy booleans are comparable.
- Clean pilot: zero checked packs/approved labels, 30 planning candidates; all assets, release mappings, rights and labels pending. No fake screenshots or approvals were generated.
- New provider calls in this build: **zero**. Existing `typesafe-sdk==0.7.0`, Observer prompt `observer-v2-literal-text`, Jev prompt `jev-evidence-v1` remain; no new resolved live model version was observed.
- The experimental direct 101-option specification uses the same canonical definitions, without examples. [Official Choice documentation](https://docs.typesafe.ai/primitives/choice) lists up to 255 options and sum-to-one probabilities. Strict 0.001 tolerance is unchanged. Request acceptance and comparative quality remain untested live.
- Family Action .51 / RPG .49, Action child .80 / unknown .20, RPG unknown 1.0 still yields genre .408 and global unknown .592. This tests arithmetic, not whether wrong-family rejection means genuinely insufficient game evidence.

See [replay contracts](PR_B_MEASUREMENT.md), [original audit](LEGACY100_EVIDENCE_AUDIT.md), and [local runbook](LOCAL_WORKSPACE.md).

## Paired case scorecards (v2)

`paired-report-v2` can carry `case_measurements` for each method using the existing typed `CaseMeasurement` contract. Every assigned case must be present for paired quality; case IDs, evidence/observation hashes, taxonomy, conditions, reference version, input mode, platform, identity eligibility and reference annotations must agree. Method/case IDs, detailed SHA-256 hashes and the frozen tag/genre vocabulary are checked. Run execution-error rates include malformed tag/genre distributions; partial-output rates remain separately visible. `paired-report-v1` remains readable for historical summary-only reports and cannot carry v2 case rows.

The website reuses `evaluation.metrics` for per-tag accepted precision, accepted-only recall, end-to-end positive recovery, raw outcomes, errors, four-state Brier, reliability buckets and genre confusion **counts**. It shows micro tag precision/recall in the headline, per-tag denominators in the quality table, and macro values in the full report inspector. Paired n is games, never games × 25 tags. Undefined denominators remain null. One accepted positive and 99 deferred positives yields 100% accepted precision but only 1% end-to-end recall. Identity-excluded and pending-label cases remain visible in assigned/operational counts.

Detailed rows take precedence over summary booleans for emitted-primary correctness, useful coverage and the accepted-result denominator of cost. A null primary cannot become correct/usable through a contradictory summary flag. A missing or mismatched detailed pair cannot fall back to those summary booleans. A known candidate metric may be displayed even when the baseline denominator is undefined; its **change remains undefined**.

Four-state calibration uses only valid distributions and evidence-supported human references. Game-truth positive recovery is reported separately. Invalid totals such as 0.99 stay invalid, count as errors and do not enter Brier/reliability. No raw distribution is renormalized by this adapter. The visual reliability plot requires at least two buckets with five scored cases each; this is a display guard, **not** sufficient evidence of calibration. Sparse bins remain in the table with counts. No per-genre accuracy or independent tag-level confidence interval is inferred.

Saved reports declare `comparison_question`: source repair (A→B), Observer separation (B→C), classifier increment (C→D), end-to-end, Jev method, or unassigned. Claiming a Jev increment requires declared conventional→Jev method roles and identical nonempty classification-criteria hashes, as well as the shared evidence/observations/conditions contract. Reports remain descriptive and cannot automatically attribute an effect to a vendor. Changed-evidence source-repair studies need a separately reviewed design; this viewer deliberately does not weaken matched-evidence gates to produce a number.

To prepare a report from permitted existing method files without network calls:

```bash
python -m gametagger.workspace.experiments \
  --baseline /private/conventional-method.json \
  --candidate /private/jev-method.json \
  --question classifier_increment \
  --output .local/reports/new-comparison.json
```

Output is create-only and private. The website never loads raw source bodies or full case-reference payloads to draw these charts. Model/method records and allowlisted case identifiers/status/primary choices remain inspectable. Imported reference provenance is declared data; this code cannot turn AI suggestions into actual human review. No new reviewed labels or real effect sizes were produced to implement this interface.
