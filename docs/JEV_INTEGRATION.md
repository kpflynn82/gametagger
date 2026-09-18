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

## Live status and reproducible completion

The existing smoke test was attempted before changes. It stopped with `No API key was provided` because `TYPESAFE_API_KEY` was not set. No authenticated request was sent. The updated smoke test reports this condition directly, and the new live test is skipped without a key.

**Still unverified:** server acceptance of this complete 26-question payload, account access to `jev-latest`, the server-returned model/version, real distribution shapes/rounding, and live latency. Documentation describes the alias, but this PR does not claim to have observed its resolution. The real Anthropic adapter is SDK-transport-tested but also lacks an authenticated run.

To finish validation, provide the key through the environment and run:

```bash
python scripts/jev_smoke.py
pytest -m live -s
```

For an ignored local `.env`, use `uv run --env-file .env python scripts/jev_smoke.py` and `uv run --env-file .env pytest -m live -s`. Record the returned model, SDK version, outcome, and latency here; never record credentials. A live failure must not be converted into a skip or silently replaced with mock output.

## Primary references

- [Official Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python)
- [TypeSafe Python SDK documentation](https://docs.typesafe.ai/sdk/python)
- [Choice request and response contract](https://docs.typesafe.ai/primitives/choice)
- [TypeSafe models](https://docs.typesafe.ai/models)
- [Anthropic vision input](https://platform.claude.com/docs/en/build-with-claude/vision)
