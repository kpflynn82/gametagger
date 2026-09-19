# Milestone 2, PR A: source integrity and isolated execution

Scope: the frozen 14-family/100-genre taxonomy and 25 Genome tags. No old database writes,
retagging, source corrections, production UI, paid calls, or clean benchmark are part of this PR.
PR B (evidence-policy/measurement/Observer literal text) and Experiment C remain separate work.

## Preserved reference

The actual saved 100-record experiment was found in the existing Codex workspace. Before new
execution, 257 files were inventoried and preserved in a read-only, content-addressed tar archive.
The public `experiments/legacy100/manifest.json` contains artifact hashes, snapshot file timestamps,
112 linked attempt IDs, source-record creation dates, the baseline commit
`8a822308cf52c9a43cc9d8bb9dd7110c5ad48c75`, seed `20260918`, taxonomy/prompt/model/SDK versions,
and explicit capture limitations. The original source bodies/media remain local; only hashes,
minimal title/product audit metadata, and probability-only response fixtures are checked in.

Archive SHA-256: `4ef9d5a1792167cda797af12e55cefb278184800585b8bb95b496363598b0767`.
Manifest inventory SHA-256: `2ede77a4dffbbffd447bc262f42dc0eb2a7644685bee13ac29b4186fb3d78d6c`.
This is write-protected and tamper-evident preservation, not a claim of external WORM storage.

The 12 first-attempt failures have error records but no saved response bodies. The 22 retry
response files are SDK `model_dump` output; original HTTP JSON and request IDs were not captured.
SDK reparsing preserves those saved numbers, but cannot establish what the wire originally sent.
File modification times are not authoritative acquisition timestamps. The final retry-enabled
runner is preserved; its pre-retry source hash was never recorded. These gaps are not filled in.

All 100 rows remain in the stress suite, including missing evidence and terminal errors. Historical
labels remain machine annotations, not human truth. The original 77/85 source-title review flags
are not a verified mismatch rate, and the original agreement rates are not accuracy.

## Identity contract and gate

`IdentityManifest` separates the raw imported record/label, reviewed record kind, intended canonical
subject, release/platform/edition IDs, and per-source actual page/product ID, reported title,
provider, supplied publisher/developer/year/platform, acquisition time, and content hash.

Relationships are explicit: verified same release, approved cross-release property scope, approved
alias/localization, related different product, mismatch, ambiguous, or unverified. Reviewer,
justification, decision origin, and timestamp are retained. Automated suggestions and imported
associations never approve themselves. A store ID is an identifier, not sufficient verification.
The library records approval supplied by a trusted caller; it is not an authentication or human
review UI. Callers must enforce who can submit reviewer attestations.

No title similarity, punctuation normalization, franchise inference, or first-search-result rule
exists in the gate. Localization aliases retain their scripts. Explicit release/platform/edition
conflicts block same-release use. Cross-release approvals name the exact transferable properties
(e.g. `genre`); wildcard transfer is disallowed. Each tag and the genre chain get only their eligible
source context. A genre-only transfer cannot establish co-op or another release-specific property.

The gate retains excluded sources in the audit. Unresolved identity, invalid nongame record,
no eligible sources, execution failure, and a valid semantic `insufficient_evidence` answer are
different states. Clip/chapter/location/encounter records remain preserved for later reviewed links.
No public canonical ID is inferred from model memory.

For unknown/prerelease work, a user explicitly associates uploaded assets with an opaque publisher
project. The existing image CLI creates that declaration from its uploaded files (`--project-id`,
or its local case ID). This does not approve retrieved store pages for the project. Library callers
must supply a manifest or explicitly associate uploads; otherwise the pipeline calls neither the
Observer nor Jev. Corrected associations create a new evidence version with the prior version hash,
reviewer, and reason; original versions are not overwritten.

Identity validation occurs before observing or combining source content. Model context uses only
eligible, hash-matched evidence and validated observations. Blind runs additionally remove document
quotes, title/metadata, source names, and identifying record/evidence IDs. Audit identities remain
outside the model context. Visible image identity cues are not claimed to be removed.

## Execution contract and compatibility

`DecisionBatch.tags` contains only valid semantic tag answers. Every requested question remains in
`questions` with `valid`, `error`, or `not_evaluated` execution status; errors have no invented
probabilities. `genre` is now nullable for incomplete computation, which is distinguished by
`genre_execution` from a valid genre decision whose `primary_genre` is null. `execution_status`
reports complete/partial/failed/not-evaluated. Consumers must use those fields for denominators.
This is an additive execution contract with an intentional nullable-genre migration.

`JevDecisionEngine.decide` requires identity by default. A deliberate `require_identity=False`
reference/test call is labelled `identity_status: reference_only`; it must never be treated as a
publishable result. The application pipeline always enforces identity. Identity eligibility alone
is not final publication approval: evidence-policy/positive support attribution remains PR B.
Existing `evidence_ids` and `context_evidence_ids` are context provenance, not positive support links.

The SDK's public custom-response-model hook keeps answer payloads unparsed until independent
validation. A malformed ranged-combat answer retains the other tags and a valid genre chain.
A failed family blocks children but retains independent tags. Failed conditional branches remain
visible; no branch mass is dropped or renormalized into a primary. Conservatively, all selected
branches (including the minimum two zero-weight branches) must validate before aggregation.

Envelope/model/usage/unsolicited-question errors invalidate that request's answers. Missing requested
answers are isolated question errors. Authentication failures are terminal; transport/envelope
failures are recorded and bounded. Successful answers from earlier validated requests remain valid.
Probability option sets, finite/range checks, maximal selected choice, confidence, and the strict
0.001 total tolerance remain enforced. Raw invalid distributions are never normalized.

Retry policy `first-valid-v1` permits two attempts per question by default (configurable 1–3).
Only failed questions recur; unchanged evidence/spec hashes are recorded. The first valid answer
wins, never the highest-confidence answer. Real TypeSafe requests pin the resolved model version
for retries and conditional calls when the service returns one; a changed version fails closed.
Unresolved aliases/fixture transports explicitly report pinning unavailable. SDK automatic retries
are disabled, so hidden calls cannot escape the attempt ledger. Observer execution is outside
Jev retry loops.

Each request retains attempt ID, stage, ordinal, requested/returned model, SDK version, question IDs,
spec/evidence hashes, parsed raw answers, errors, latency, and reported usage. The owned HTTP client
also records response-body and request-ID hashes. Request-ID values and exception bodies are not
logged. Unknown usage stays null; totals include returned usage from retries and become null if any
attempt is unknown. No partial token sum is described as a bill. Original successful-call timing
is not end-to-end latency.

## Offline replay

```bash
python -m gametagger.evaluation.replay \
  --snapshot /path/to/original/genre-evaluation-100 \
  --manifest experiments/legacy100/manifest.json \
  --output /path/to/new/private/replay-output
```

This verifies every preserved file, retains all 100 rows, creates a separate unverified intake
manifest/evidence version, and revalidates saved provider responses. It makes zero network calls.
The output path must be new and outside the reference snapshot. Its source bodies stay private;
do not commit generated intake files. Missing/changed artifacts fail rather than being invented.

The actual offline replay retained 100 rows, left 100 identities pending review, made zero approvals
and paid calls, and reproduced exactly the three saved terminal 0.99 failures. The 12 original
first-attempt errors and nine retry recoveries remain visible in the reference manifest.

## Validation and stopping point

Offline regressions cover synthetic approved aliases, related franchises, restricted release
transfer, mixed verified/mismatched sources, opaque prerelease uploads, hash/version changes,
blind identity isolation, all failure dependency cases, selective retries, model drift, envelope/
auth/transport failures, and saved failure fixtures. Problematic original pairs are provenance-labelled
review cases, not newly adjudicated ground truth. The Observer provider prompt is unchanged.

Live tests require both `GAMETAGGER_RUN_LIVE=1` and `TYPESAFE_API_KEY`; a saved key alone does not
trigger a paid call. Run `pytest`, `ruff check .`, and `ruff format --check .` offline.

The sanitized [provider report](TYPESAFE_PROBABILITY_BUG_REPORT.md) is a draft only and has not been
sent. PR B and the clean benchmark must wait for this PR's review.
