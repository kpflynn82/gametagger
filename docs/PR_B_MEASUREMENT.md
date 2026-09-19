# Milestone 2 PR B: measurement and benchmark readiness

This change preserves the 14 families, 100 eligible genres and 25 tags byte-for-byte.
It makes no paid model calls, changes no legacy database, and assigns no new real-world
identity approvals or human truth. The hierarchy remains the production inference method.
The original experiment is an intake stress suite, not a verified game benchmark.

## Evidence and publication contracts

`evidence-policy-v1` is a separate, versioned eligibility overlay, not a taxonomy edit.
It applies the PR A source identity gate and each tag's frozen evidence-type allowlist
before making a request. Questions without eligible observations retain `not_evaluated`
and a rule-based `identity_not_eligible` or `no_eligible_evidence` reason, with no model
answer or manufactured probabilities. These outcomes remain in all operational denominators.

An `EvidenceProfile` separates provider, actual modality and reviewed publisher authority.
A store description stays `store_metadata` and text; a store screenshot is image evidence.
A metadata quotation attached to an image does not inherit visual eligibility.
A supplied profile with the wrong content hash or modality fails eligibility.

The only additional documentary exception is a reviewed, exact, explicit claim matching
one of the co-op/multiplayer/parry rules. It requires a hash-bound official publisher profile,
a reviewed same-release or localized-alias mapping, and the same nonempty release ID.
(The first two tags already permit store text in the frozen taxonomy.) Generic combat
marketing does not satisfy the parry exception. This supports documented existence or
explicit absence, not visually confirmed timing. Source types are never relabelled.
These conservative English phrase rules are prefilters; they do not adjudicate meaning.
Other languages/ambiguous phrasing await review instead of expanding every allowlist.

`ClaimAttribution` links a decision to an exact span in an observation, with review origin,
reviewer and date. Context `evidence_ids` remain context, not proof. `support_links` stays
empty unless explicitly attributed and reviewed; an `accept` action alone does not set
`publishable`. Publication requires eligible identity/evidence, valid answers, accepted
policy and support links. A review field is an audit declaration, not proof that a human
actually performed review. No such declaration was created for the real 100-record suite.

The narrow exception is signalled separately in the decision payload. Prompt version is
`jev-evidence-v1`. Distributions still require the exact option set, finite/range-correct
values, a matching selected option, and totals within the existing 0.001 tolerance.
No 0.02 tolerance, quantization compatibility policy, or silent repair was introduced.

## Observer boundary

`observer-v2-literal-text` retains the existing Observer interface and adds one attributed
kind: `visual_text`, with verbatim text and a normalized bounding region. “Merge”, “Survival”,
or “Action RPG” on screen may be transcribed. They cannot alone become supporting citations
for a genre or tag. `visual_fact` still passes the taxonomy lexical guard; `metadata_quote`
still requires an exact source substring. Structured extras remain forbidden. Both providers'
prompts treat quoted content, including instructions visible in an image, as untrusted data.

Regression fixtures were added before the real provider prompt was changed. They cover
literal labels, injected instructions, invalid/missing regions, unsupported visual conclusions,
and blind context. There was no real vision experiment in this PR. Bounding boxes and a
lexical guard cannot independently verify OCR truth or catch every inferential paraphrase.

## Metrics and denominators

Every ratio includes `numerator`, `denominator`, and a nullable `value`; zero denominators
produce null. Missing legacy keys are unknown. Human-reviewed labels, AI suggestions and
legacy machine annotations have distinct origins. A reference without a reviewer/date
cannot claim human review. Game truth and evidence-supported four-state truth are separate.
Mode-specific supported labels belong in `references_by_mode`; a combined annotation is
never silently reused as media-only truth.

- Operational: completion/all cases, first success/known first attempts, recovery/known
  retry outcomes, terminal errors, partials, pending/not evaluated, identity eligibility,
  no evidence/known availability, and unknown counts.
- Genre: forced best-non-null candidate accuracy is diagnostic only. Emitted-primary
  accuracy uses actual valid emitted primaries; coverage uses all cases. Accepted/publishable
  precision additionally requires identity, evidence, contract, attribution and policy.
  A null primary whose candidate happens to match is not an emitted correct answer.
- Tags: accepted positive precision counts unsupported positive publications against
  precision. Accepted-only recall is TP/(TP+accepted FN); end-to-end positive recovery is
  accepted TP/all human evidence-supported positives, including errors and abstentions.
  Game-truth positive recovery has its own denominator. Positive/negative coverage,
  four states, errors and not-evaluated counts remain visible independently of legacy keys.
- Four-state accuracy, selected-state calibration bins and multiclass Brier (sum across
  four states) use evidence-supported human truth. Invalid distributions never enter
  probabilistic scoring. This is not calibrated probability of game-wide feature existence.
- Confusion/support counts are sliced by family, tag, input modality and platform.
  Development and holdout summaries are separate, as are every method and input mode.
  No per-genre accuracy is claimed from a single example.

## Saved-result replay

Run without keys:

```bash
gametagger-eval --manifest experiments/clean30/manifest.json --output /tmp/gametagger-readiness
python -m gametagger.evaluation.legacy_audit \
  --snapshot /private/path/to/genre-evaluation-100 \
  --manifest experiments/legacy100/manifest.json --output /private/new-audit-directory
```

Outputs must be new directories. The original 257-file inventory is verified before the
legacy audit and never overwritten. Keep detailed outputs private: they can contain
historical annotations or raw invalid answers. Only the sanitized aggregate
`experiments/legacy100/pr_b_audit.json` is committed.

The general runner accepts `BenchmarkManifest` in `evaluation/benchmark.py`:

1. Declare methods (e.g. `jev_hierarchical`, `non_jev`) and modes (`metadata_only`,
   `media_only`, `combined`). Add real cases with split, canonical/franchise/asset groups,
   platform, mobile-first status, references, and pending reasons. Cross-split duplicate
   canonical games, franchises, declared assets or observation hashes are rejected.
2. Freeze an `ObservationBundle` per evidence version/mode, with identity manifest,
   evidence, observations, provenance, policy profiles/claims, model/prompt versions,
   residual visible identity cues, actual permitted media artifacts and hashes. Store
   observations once and reference the identical artifact for every decision method.
   Media-only requires observations produced **without metadata before observation**;
   dropping quotes from an already combined observation is rejected as a blind experiment.
3. Export each adapter's saved output as `SavedPrediction`. It must bind the case, method,
   mode, evidence version, observation hash, taxonomy hash and context hash. Compute the
   context hash with `context_for(bundle, mode, taxonomy)` and `sha256(context.encode())`.
   This identifies the frozen comparison input; request records retain actual request
   provenance. Non-Jev categorical outputs can omit probabilities; never invent them.
   Full Jev distributions remain required by the live engine. Saved conditional/family
   responses can remain in the optional hash-bound private `raw_response` artifact.
4. Retain request attempt IDs, components, model versions, timing, retry flags, errors and
   reported usage. Null usage means unknown, not zero. Observer and decision request lists
   are separate. The built-in Observer disables hidden SDK retries so one recorded call
   is one attempt; injected adapters must disclose their own retry/usage limitations. End-to-end latency is distinct from final-call and local replay timing.
   The replay does not calculate a bill or reconstruct missing token totals.
5. Replay to `cases.jsonl`, `summary.json` and an exact manifest copy. Missing cells remain
   pending. Bad artifact/envelope bindings become case errors. Invalid individual answers
   preserve other independent valid answers and their raw invalid values in error records.
   Predicted support/identity/truth flags are replaced by the bound evidence and references.

There is no network/model execution path in the runner. The test suite uses synthetic
fixtures only. Existing legacy labels are retained as unpaired non-Jev historical annotations:
there are no matching saved observations that justify calling them a controlled comparison.
Grouping/rights/review declarations require independent checking; hashes prove stability,
not authenticity or permission. The manifest is ready to accept checked packs, not an
assertion that they already exist.

## Availability and stopping point

`experiments/clean30/manifest.json` declares a target of 30 checked packs (at least ten
mobile-first), with six development and 24 frozen holdout cases planned. Actual checked
packs, human labels and permitted assets available to this task: zero. Nothing was filled
with generated screenshots, model-memory identity matches, or invented human approvals.
Source-span adjudication and benchmark execution remain pending.

The original eight text-bearing abstentions have preserved arithmetic breakdowns in the
sanitized audit. The diagnostic Action .51 / RPG .49 example still yields top genre .408
and unknown .592. Wrong-family rejection and genuine missing evidence have different
meanings, so this arithmetic is not evidence that probabilities should be changed. Resolving
these causes needs verified sources and reviewed evidence. A direct-vs-hierarchical model
experiment and current provider request-limit verification remain later, budgeted work;
this PR neither promotes an alternative method nor tunes on the holdout.
