# Jev integration validation — Milestone 1

Checked on September 18, 2026 with `typesafe-sdk==0.7.0` and Python 3.11.14.

## Verified locally against the installed official SDK

- `TypeSafeClient.system_one(state=..., questions=..., model="jev-latest")` accepts the scaffold's call shape and serializes to `POST /v1/systemone`.
- `Choice(instructions=..., criteria={...})` supports the existing string descriptions. The compiler sends 25 four-option questions and one 60-option genre question in one call.
- `SystemOneResponse.answers` is a typed mapping. A `ChoiceAnswer` contains `choice`, `probabilities`, and `confidence`. `response.choices` is also available, but no migration to it is necessary.
- In SDK 0.7.0, `model`, `usage`, and Choice `probabilities` are required fields. Usage counts themselves may be null. The response's model is retained separately from the requested alias.
- The SDK reads `TYPESAFE_API_KEY` from the process environment. Instantiating a client without it fails before any network request.
- Tests run the actual SDK HTTP serializer and parser with an injected mock transport. Those tests verify the contract, **not authenticated server behavior**.

## Changes to scaffold assumptions

The scaffold's public request and answer field names remain valid in the installed SDK. The integration is pinned to the inspected 0.7.0 version, with a lockfile for reproducibility. We added context-managed clients, a 60-second request timeout, and strict validation of question IDs, Choice type, complete option sets, finite/ranged probabilities, chosen-option consistency, and confidence.

Distributions must sum to one within an absolute rounding tolerance of 0.001. Values are preserved exactly as parsed; there is no renormalization or replacement. An incompatible response raises `JevContractError` before policy runs. The SDK can discard unknown answer types, so the wrapper also explicitly requires every requested answer.

Previously discarded confidence, returned model, token usage, genre evidence IDs, and latency are retained. The result also records observer/prompt/taxonomy/SDK versions and image provenance. Jev receives evidence types and observation kinds, allowing it to distinguish metadata claims from visual facts. Evidence IDs refer to all evaluated inputs, not a claim that every input positively supports every tag.

## Authenticated Jev validation

On September 18, 2026, the saved environment key successfully authenticated against TypeSafe.
Both the original smoke call and the live integration test returned `jev-1.13.0` for the requested
`jev-latest` alias. All 25 tags had four probabilities; the genre response had all 59 labels plus
`insufficient_evidence`. The observed distributions passed all contract checks without repair.

The first smoke call completed in **427.64 ms**, using 7,969 input and 2,122 output tokens.
It selected First-Person Shooter. It also marked three unshown camera perspectives absent,
including an accepted third-person absence. This is an evidence-scope problem: seeing one
perspective does not establish which camera modes exist elsewhere in a game.

The `jev-v2` compiler prompt now explicitly requires negative source evidence for absence and
states that camera tags are not mutually exclusive. A follow-up authenticated call completed in
**1,062.85 ms**, using 9,694 input and 2,137 output tokens. It selected First-Person Shooter,
returned four `present` tags and 21 `insufficient_evidence` tags, and returned no `absent` or
`conflicting_evidence` selections. All tag distributions and the genre distribution summed to 1.
Returned probabilities are retained unchanged. These are individual smoke observations, not
latency benchmarks or proof of general classification accuracy.

To reproduce with credentials in the process environment:

```bash
python scripts/jev_smoke.py
pytest -m live -s
```

For an ignored local `.env`, use `uv run --env-file .env python scripts/jev_smoke.py` and
`uv run --env-file .env pytest -m live -s`. The live test skips without a key; real API failures
fail normally. No credentials or account identifiers are recorded in this repository.

## Anthropic workspace requirement

The first authenticated image-pipeline request returned HTTP 400 because the supplied key is not
scoped to a workspace and requires an `anthropic-workspace-id` header. Read-only workspace
discovery returned HTTP 403. This is a configuration prerequisite, not an observer response-schema
failure; it was resolved by supplying the workspace header, as described below.

The observer now accepts an optional workspace ID and the CLI reads it from
`ANTHROPIC_WORKSPACE_ID`. Both workspace-header and no-header paths are covered through the real
Anthropic SDK with mocked HTTP transport. Obtain the ID from Claude Console → Settings → Workspaces
and put it in the local environment. Workspace-scoped keys can omit the setting.

## Successful authenticated image pipeline

On September 18, 2026 (Pacific time), the full CLI path completed successfully using
`claude-sonnet-5` (Anthropic SDK 1.7.0) and `jev-1.13.0` (TypeSafe SDK 0.7.0).
The configured placeholder `ClaudeVision` initially returned HTTP 404. The authenticated model
listing confirmed `claude-sonnet-5` supports image input; that valid ID replaced the placeholder
in the ignored local environment. No application model default or credential was committed.

Input: the repository's synthetic `fixtures/sample.png` with `fixtures/sample.metadata.json`.
The observer returned a factual description of the white circle on a dark gray square and an
exact source-metadata quote, both linked to `image-1`. The complete result retained the image
hash, observations, all 25 four-state tag distributions, all 60 genre probabilities, policy
actions, provenance, model/prompt/SDK versions, and latency. The selected genre was null
(`insufficient_evidence`), with no fallback genre.

Observed latency: **2,571.18 ms** total, **2,238.35 ms** for observation, **332.66 ms** for Jev,
and **0.17 ms** for policy. Jev usage was 9,788 input and 2,163 output tokens. This single synthetic
case verifies the authenticated integration; it does not measure accuracy on real gameplay or
establish a performance benchmark. All prior credential/workspace validation blockers are resolved.


## Primary references

- [Official Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python)
- [TypeSafe Python SDK documentation](https://docs.typesafe.ai/sdk/python)
- [Choice request and response contract](https://docs.typesafe.ai/primitives/choice)
- [TypeSafe models](https://docs.typesafe.ai/models)
- [Anthropic vision input](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Anthropic workspace authentication](https://platform.claude.com/docs/en/manage-claude/authentication)
