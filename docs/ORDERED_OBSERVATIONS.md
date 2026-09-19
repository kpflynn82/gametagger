# Ordered media observation and saved replay

This milestone implements an ordered-window Observer adapter and a private website replay path. It does **not** establish temporal recognition accuracy or enable live spending. The taxonomy, single-image Observer contract, original experiment, and Jev probability validation are unchanged.

## Inputs and observation boundary

Local video preparation still samples three bounded windows across the full timeline. Each window contains 2–12 consecutive decoded JPEG samples (at most 640 pixels per side, 4 MiB total). Exact presentation timestamps, source/frame SHA-256 hashes and the selection strategy are retained. Gaps greater than 0.5 seconds split windows; fewer than two nearby samples remain unavailable for ordered observation. This is a conservative sampling contract, not proof that fast mechanics are observable.

`AnthropicOrderedObserver` sends the exact verified frame bytes through the installed Anthropic Messages SDK. Its `ordered-observer-v1` system prompt and response schema have a combined hash. The request digest includes the ordered input, requested model and prompt/schema hash. No game title, store description or local path enters this media-only request. Visible image text may still reveal identity. The multi-image content format follows the [official vision documentation](https://platform.claude.com/docs/en/build-with-claude/vision); successful mocked transport is not live API/model validation.

A structured output distinguishes:

- `visual_fact`: a directly visible statement linked to one frame.
- `visual_text`: attributed literal text linked to one frame and a normalized region. “Merge” or “Survival” can be text, never a genre assertion.
- `sequence_fact`: a description of changes across consecutive supplied frames. It must not infer hidden events, precise reactions, named mechanics, causation or game-wide absence.

Each response proposes gameplay/menu/cinematic/title-card/overlay/mixed/unknown context. That proposal is not human approval or proof of normal gameplay. The existing classification boundary is applied to nonliteral statements. Prompting and lexical checks cannot prove that every paraphrase is factual; recognition quality needs checked footage and independent labels.

The adapter records requested/returned models, SDK/prompt versions, request/response/output hashes, per-request elapsed time, available usage and a hashed request ID. An invalid response becomes an explicit per-window error with no semantic observations. Other windows can still succeed. It performs no automatic retries. Actual provider errors are redacted; returned usage remains available on invalid-answer attempts, unknown where unavailable.

Without an injected test client, the adapter refuses calls by default. A future authorized budget executor may explicitly enable it; the website has no route to do so. Keys alone do not authorize spending.

## Website replay

1. Create an associated publisher project or an explicitly isolated demo, upload a local clip, and prepare a run.
2. Download its **exact window manifest** from the Results page. This describes inputs only; it is not a fabricated saved response.
3. A reviewer may import an `ordered-observation-replay-v1` JSON bundle containing retained `WindowAttempt` records, the parent input hash and taxonomy hash. The typed contract is in OpenAPI and `gametagger.workspace.observation_replay`.
4. The backend checks exact source/frame bytes, window order/timestamps, prompt/request/model binding, output hashes, attribution and taxonomy boundaries. A changed bundle is rejected. Illustrative bundles are restricted to demo projects. Owner, role, identity and same-origin controls still apply.
5. A successful import creates a separate durable **partial** run. It preserves the original preparation and human catalog corrections. It records valid/error/not-evaluated windows independently. Repeated identical idempotency keys return the same run; different inputs cannot reuse the key.
6. Select an observation to seek its original video timestamp. Reopen the replay from Catalog/History. Default JSON/CSV exports omit observation text and media.

Imported provenance is supplied, not cryptographically authenticated provider origin. All imported claims remain explicitly unverified; hashes alone cannot create human truth. The website makes zero new provider calls, never manufactures genre/tag probabilities, and does not promote replay observations into approved classification support. Classifiers still require a separately approved execution path. Original request timings/usage are preserved separately from local replay validation time; total replay-request latency is unmeasured.

A valid bundle must retain the installed prompt/schema version; older versions remain private historical artifacts and cannot silently replay under changed semantics. Only one retained attempt per window is accepted, no confidence-based cherry-picking. Missing windows remain in the not-evaluated denominator. Malformed import/provenance envelopes are rejected as a whole; valid adapter-produced error records preserve independent successful windows.

## Offline verification

`tests/test_ordered_observer.py` exercises the real SDK serializer/parser through mocked HTTP transport, exact image bytes/order, identity exclusion, source/temporal references, literal text, malformed envelopes, preserved failed-attempt usage and the spend-disabled default. `tests/test_observation_replay.py` covers provenance mismatch, modified files/output, role/owner/identity boundaries, immutable parent runs, persistence, idempotency, unassessed classification and redacted exports.

The browser workflow creates synthetic local video, imports explicitly illustrative saved observations, checks an invalid import, seeks the source, reloads and exports. The two new screenshots are synthetic interface checks, not actual game recognition. No provider or human-label quality conclusion can be drawn from them.
