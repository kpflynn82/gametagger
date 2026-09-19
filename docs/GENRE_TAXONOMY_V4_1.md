# Genre taxonomy v4.1

GameTagger has 14 families and 100 primary-capable genres. A game has **one store-facing primary
genre** whenever the supplied evidence supports classification. Up to two secondary genres are
retained separately; neither review routing nor secondaries replace or multiply the primary.
`insufficient_evidence` represents genuine inability to classify, not a generic fallback genre.

## Canonical taxonomy

`taxonomy/vgms_v4.yaml` is the only classification taxonomy. `genre_families` contains family IDs,
display names, definitions, and nested genre records. Each genre has a stable `id`, `display_name`,
`family`, `definition`, `inclusion_criteria`, `exclusion_notes`, `example_games`, and a boolean
`primary_eligible`. IDs remain stable when display wording changes. Duplicate IDs/names, wrong
parent families, missing fields, and invalid eligibility values fail loading.

All 100 requested initial genres are eligible. A future `primary_eligible: false` concept remains
documentable but is excluded from primary/secondary questions and rankings. Each classified family
must retain an eligible child. Examples are illustrative boundary aids for documentation/tests;
they are never included in Jev question criteria, even outside blind-media mode.

The existing 25 Genome tag definitions are unchanged. Open world, crafting, pixel art, co-op, PvP,
F2P, gacha, dark fantasy, anime, and procedural generation remain discovery dimensions, not new
primary genres. This PR does not add or redesign Genome tags. Compound genres such as Open World
Survival Craft require their defining gameplay loop rather than a single discovery trait.

## Two Jev stages

1. **Stage A:** request the existing 25 Genome decisions and a 15-option family Choice: 14 stable
   family IDs plus `insufficient_evidence`.
2. **Stage B:** request a separate conditional Choice for each selected family. Keep at least the
   top two families, then every additional family with nonzero probability. This deliberately
   avoids approximate beam pruning: no positive probability mass is lost, and a third or later
   family can win globally. All selected family questions are batched into one second API request.
   Each Choice contains only that family's eligible genres and `insufficient_evidence`.

The classifier never makes one large 100-genre Choice and never uses a greedy one-family path.
Even when Stage A assigns all mass to insufficient evidence, two branches are retained, their
zero family weights ensure they cannot manufacture a primary, and all raw responses remain visible.
This favors correctness and auditability over saving the second request in that edge case.

## Aggregation and sufficient evidence

For normalized family probabilities `F` and conditional probabilities `C`:

```text
P(genre g) = F(family(g)) × C(g | family(g))
P(insufficient_evidence) = F(insufficient_evidence)
                        + Σ F(family f) × C(insufficient_evidence | f)
```

The global distribution includes every eligible genre plus insufficient evidence and sums to one.
An unevaluated family has exactly zero Stage A mass, so its genres have zero global contribution;
this is an aggregation result, not a fabricated conditional provider response.

Raw Jev values, choices, confidence, and model identifiers are stored unchanged. SDK contract
validation still permits only sums within 0.001 of one. Aggregation normalizes *copies* of those
validated distributions to account for rounding and normalizes the derived global result. The
result contract verifies that the global values match the family/conditional products.

The highest-probability eligible genre becomes `primary_genre` if its global probability is
strictly greater than global `insufficient_evidence`. Otherwise the primary is null and secondaries
are empty. A tie with insufficient evidence abstains. Ties between eligible genres are resolved
by ascending stable ID, so identical inputs always yield exactly one primary.

This is a deterministic choice rule, not an empirically calibrated confidence threshold. A close
race between two supported genres still has one primary, while policy can flag it for human review.
No absolute acceptance threshold can silently replace that primary with a generic label.

Secondaries are the next highest-ranked eligible genres, at most two, each with global probability
at least 0.10 and strictly greater than insufficient evidence. They are supported alternative
labels, not independent estimates that both genres must apply. This initial display threshold is
explicit and uncalibrated; it never affects primary selection.

## Result contract and migration

Genre results carry `schema_version: "4.1"`. This is a deliberate schema change from Milestone 1:

| Field | Meaning |
| --- | --- |
| `primary_genre` | One stable genre ID, or null for insufficient evidence; formerly a display name |
| `secondary_genres` | Zero to two distinct eligible IDs; excludes the primary |
| `family_probabilities` | Complete raw 15-option Stage A distribution |
| `family_choice`, `family_confidence`, `family_model` | Unmodified Stage A metadata |
| `conditional_genre_probabilities` | Complete raw per-family Stage B distributions |
| `conditional_choices`, `conditional_confidences`, `conditional_models` | Stage B metadata keyed by family ID |
| `evaluated_families` | Auditable list of the branches evaluated |
| `global_genre_probabilities` | Derived normalized distribution; replaces the old flat `probabilities` field |
| `global_genre_ranking` | All eligible IDs and their global probabilities, sorted by probability then ID |
| `confidence` | Probability of the selected primary or insufficient evidence; not raw Jev confidence |
| `evidence_ids` | All evaluated context evidence IDs, unchanged in meaning |
| `action` | Existing accept / evidence / review policy action |

`usage` sums both Jev requests; if a stage omits a token count, the total for that count is null.
`usage_by_stage` preserves the original counts. Taxonomy version is `4.1`; decision prompt version
is `jev-genre-v4.1`. Returned per-stage model identifiers are retained even if an alias resolves
differently between requests. Consumers resolve display names using `/taxonomy`, which now returns
the complete family tree with documentation examples. Observer code, interface, and prompts are
unchanged; its existing display-name vocabulary view is derived from the hierarchical taxonomy.

## Deterministic validation

The named game cases are test labels paired with scripted distributions, not title heuristics or
live-model accuracy assertions. Tests cover Elden Ring in the second-ranked RPG branch (both Action
RPG and Souls-like outcomes), Fortnite, Destiny 2, Hades, Hollow Knight, Slay the Spire, RimWorld,
Factorio, Vampire Survivors, Pokémon, Among Us, Candy Crush, and a mobile merge title. They also
cover a third-family winner, all 14 branches, unknown and tie behavior, eligibility, probability
rounding, secondary limits, schema validation, and malformed Stage B responses.

```bash
pytest
ruff check .
ruff format --check .
gametagger --image fixtures/sample.png --metadata fixtures/sample.metadata.json --offline
```

The optional environment-gated live test checks the hierarchical API contract without asserting
specific genres. The named-game regressions always run without network access or credentials.

On September 18, 2026, the authenticated full suite passed **103 tests**, including both Jev
stages through `typesafe-sdk==0.7.0`. The requested `jev-latest` alias returned `jev-1.13.0`
for the conditional response. Both requests passed the existing strict Choice contract checks;
no SDK wrapper change was needed. Combined usage was 12,200 input and 2,160 output tokens for
that single live fixture. These observations verify transport and schema, not genre accuracy
or a performance benchmark. Without credentials, 102 tests pass and the live test skips.
Lint and formatting checks pass; the built wheel includes the exact v4.1 taxonomy, and the
offline CLI serializes all 15 family options and all 101 global outcomes correctly.
