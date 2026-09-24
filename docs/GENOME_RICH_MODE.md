# Rich Genome mode

Rich mode is a second way to run GameTagger with Jev. It asks many more questions, and it shows
Jev much more attributed evidence. The pilot pipeline, frozen 25-tag taxonomy, experiments and
website are unchanged.

## Why the pilot path gave thin results

The original GenomeTagger (`kpflynn82/gametagger-web`) pulled Wikipedia, Steam and Xbox text
automatically. It sent everything to Claude in one request and asked for about 95 yes/no tags
across 12 categories. Claude could also use what it already knew about the game.

The pilot pipeline in this repository is deliberately cautious. When combined, those limits leave
Jev with very little to judge. An offline check with a recording gateway (September 2026, pilot
path at `687d0b2`) showed the following:

| Limit in the pilot path | Effect |
|---|---|
| Only 25 attribute tags | The original asked for about 95 |
| Store or description text can only ride along as metadata on a screenshot, and the evidence policy then classifies it as `other` | That text reached Jev for **0 of 25 tags** (genre only). A description saying "online co-op", "craft", "procedurally generated" or "dialogue choices" could not support those tags |
| Tags with no eligible evidence are skipped | 8 of 25 tags were never asked |
| One Observer sentence containing a tag label or genre name (for example "pixel art" or "puzzle") raises an error | The **whole analysis fails** |
| Publishing needs a human-reviewed support link | Even perfectly confident answers are never publishable |
| The website never calls providers (budget gate) | Website runs show "not evaluated" |

Most of these limits are intentional safety rules. The largest loss comes from the two evidence
limits: text is lost, and one word can stop the whole run. Having only 25 tags also narrows the
results.

## What rich mode does

```text
dossier (store text, press kit, encyclopedia, screenshots)
  -> numbered, attributed claims            e.g. store#3 = "Play solo or with 3 friends in online co-op."
  -> screenshot facts from the Observer     statements with taxonomy words are set aside, not fatal
  -> per-tag evidence filter                each tag sees only the source types it may use
  -> Jev: one four-state Choice per tag     present / absent / insufficient_evidence / conflicting_evidence
     plus the unchanged v4.1 genre hierarchy (14 families -> 100 genres)
  -> deterministic policy + GenomeProfile   primary genre, alternatives, tags grouped by category
```

* **189 tags.** The 25 frozen pilot tags plus 164 extended tags in
  [`taxonomy/genome_tags_v1.yaml`](../taxonomy/genome_tags_v1.yaml). The extended tags are adapted
  from the owner's original glossary: gameplay elements, mechanics, narrative structure, world
  structure, modes, social and live engagement, business model, setting, tone, themes,
  protagonist, visual style, accessibility, and audience. `vgms_v4.yaml` is not modified, so
  benchmark taxonomy hashes stay valid.
* **Text is first-class evidence.** Each source becomes numbered claims, so every answer can be
  traced to the exact sentences Jev saw. Evidence policy `rich-evidence-v1` lets store, developer
  and encyclopedia text support pilot tags about systems, features, modes and timing. Pilot
  *appearance* tags such as realistic or stylized still require a screenshot, as before. Claims
  remain labelled as claims, never as visual facts.
* **Jev-native batching.** Questions that share the same evidence go in one request, with at most
  60 questions per request by default. Shared rules live in the evidence package, so they are sent
  once per request. Each tag question stays short.
* **Failures stay local.** The existing `QuestionExecutor` validates every answer strictly. It
  retries only the failed questions and keeps every attempt. One broken answer or one failed
  request marks only those tags as `error`.
* **Rules kept from `AGENTS.md`.** The four states stay distinct, and "not mentioned" is never
  "absent". There is no fallback genre. Jev's raw distributions are stored unchanged. The Observer
  never assigns tags. The game title is not placed in Jev's evidence.

### Reading a result

Each tag gets a display band computed from Jev's raw probability:

* **strong**: present with probability of at least 0.85
* **likely**: present, below that
* **absent**: a source explicitly rules it out
* **conflicting**: sources disagree
* **unknown**: the evidence neither supports nor rules it out
* **not asked**: no allowed evidence type was supplied
* **error**: execution failed

These bands are not measured accuracy. Nothing is marked publishable without human review.

## How to run it

```bash
uv sync --frozen --extra dev

# 1. Dry run (default): shows what Jev would receive and a rough token estimate. No model calls.
gametagger-genome fixtures/genome/hollow_orchard.dossier.json
gametagger-genome fixtures/genome/hollow_orchard.dossier.json --format json   # exact questions and evidence

# 2. Offline: runs the whole pipeline with mocks. Everything comes back "unknown"; this is not inference.
gametagger-genome fixtures/genome/hollow_orchard.dossier.json --offline

# 3. Build a dossier from public sources. Give an exact Steam app ID and Wikipedia title, never a search.
gametagger-genome --game-id stardew-valley --title "Stardew Valley" \
  --steam-app 413150 --wikipedia "Stardew Valley" --save-dossier stardew.dossier.json

# 4. Live: an explicit opt-in. Keys come from the environment only.
export TYPESAFE_API_KEY=...        # plus ANTHROPIC_API_KEY and --observer-model if the dossier has screenshots
gametagger-genome stardew.dossier.json --live --output stardew.profile.json
```

The Hollow Orchard dossier describes a **fictional** game, and its text is synthetic.
`--categories setting,monetization` limits a run to some categories. A live run refuses to start
when the rough Jev input estimate exceeds `--max-estimated-tokens`, which defaults to 50,000.
The full sample needs about 33,000 estimated tokens in 6 requests.

A dossier is plain JSON:

```json
{
  "schema_version": "dossier-v1",
  "game_id": "my-game",
  "title": "My Game",
  "sources": [
    {"id": "store", "type": "store_metadata", "provider": "Store listing",
     "text": "Full description text...",
     "fields": {"store_features": ["Online Co-op", "Controller support"]}},
    {"id": "presskit", "type": "developer_documentation", "provider": "Press kit", "text": "..."}
  ],
  "images": [{"id": "shot1", "path": "screens/shot1.png"}]
}
```

Source `type` is one of `store_metadata`, `developer_documentation`, `wikipedia`, `transcript` or
`other`. Image paths are resolved relative to the dossier file.

## What has and has not been verified

* Verified offline: 33 automated tests cover the vocabulary, claim splitting, evidence filtering,
  batching, strict validation and targeted retries, partial failures, observer quarantine, source
  parsing, the fixed-host network guard and the command-line safety gates. The pilot tests still
  pass after a behaviour-preserving extraction of `JevDecisionEngine.resolve_genre`.
* **Not yet verified: live quality, cost or latency.** No TypeSafe or Anthropic key was available,
  and the network blocked the Jev, Steam and Wikipedia hosts in the build environment. The token
  estimate is a characters-divided-by-four heuristic, not TypeSafe's billing. Whether TypeSafe
  accepts 60 questions per request is also unconfirmed. If it rejects them, lower
  `--max-questions-per-request`.
* The Steam and Wikipedia adapters are tested against response shapes built for the tests, not
  against live responses.

## Suggested next steps

1. Run a live check on 3–5 well-known games. Compare the profiles side by side with the original
   site's tags for the same games, then decide whether Jev earns its place for each category.
2. If rich mode is kept, add it to the website's Analyze flow behind the existing budget gate.
3. Calibrate the strong/likely display bands and the policy thresholds on human-reviewed labels.
4. Consider using Jev's **Score** primitive for ordered dials such as difficulty, story emphasis
   or session length. Score has no "insufficient evidence" option, so pair it with an
   evidence-gate question.
