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
store pages (Steam, App Store) + Wikipedia        exact IDs only, never a title search
  -> text, screenshots and the store trailer       YouTube search is the backup when no store trailer exists
  -> numbered, attributed claims                   e.g. steam#3 = "Play solo or with 3 friends in online co-op."
  -> screenshot facts from the vision Observer     one still, one moment
  -> trailer bursts from the ordered Observer      short runs of consecutive frames: visible movement and change
     (statements with taxonomy words are set aside; cinematic and title-card bursts are left out)
  -> per-tag evidence filter                       each tag sees only the source types it may use
  -> Jev: one four-state Choice per tag            present / absent / insufficient_evidence / conflicting_evidence
     plus the unchanged v4.1 genre hierarchy (14 families -> 100 genres)
  -> deterministic policy + GenomeProfile          primary genre, alternatives, tags grouped by category
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

## Screenshots, trailers and the YouTube backup

Jev reads text only. Screenshots and video reach it as factual sentences written by Claude's
vision model (the Observer). The Observer never names genres or tags. Jev then decides.

* **Store pages first.** `--steam-app` returns the listing text, the store's screenshots (4 per
  store by default, `--max-screenshots`) and its trailer. Highlighted trailers come first, then a
  direct MP4, then the HLS stream newer Steam players use. `--app-store` returns App Store text and
  screenshots; Apple's public lookup has no preview videos.
* **Trailers become frame bursts.** ffmpeg samples 6 bursts of 6 consecutive frames, 0.4 seconds
  apart, spread between 5% and 95% of the trailer (`--bursts`, `--frames-per-burst`). The ordered
  Observer describes what changes within each burst, for example "the figure moves sideways as the
  enemy swings". Timing tags such as dodge roll, parry or real-time combat can only use this
  `gameplay_clip` evidence (or developer documentation); a still screenshot is never enough for them.
* **Trailers are marketing.** The Observer labels each burst: gameplay, menu, cinematic, title
  card, creator overlay, mixed or unknown. Cinematic and title-card bursts are left out, because
  cutscenes do not show how a game plays. Each remaining claim carries its label and time range,
  such as `[gameplay, 41.2-42.0s]`.
* **The YouTube backup is API-only.** When no store page offered a trailer and `YOUTUBE_API_KEY`
  is set, rich mode searches `"<title> official trailer"` through the YouTube Data API. It prefers
  a video whose title names the game and whose channel matches the store's developer or
  publisher. If there is no trailer, it takes the most-viewed `"<title> gameplay"` video. The API
  does not provide the video file, and nothing is downloaded from YouTube. Rich mode records the
  video as a **reference** (link, channel, views, and whether the channel is confirmed official)
  and analyzes YouTube's three published still frames of it as screenshots. Each lookup uses
  about 101 of the default 10,000 daily quota units, or 201 when it falls back to gameplay.
  Use `--youtube always` or `--youtube never` to override this.
* **Google Play is a slot for now.** Google has no public store API. `--google-play com.x.y`
  records the store link, and YouTube still supplies the trailer stills. Connecting a data
  service is a small adapter once one is chosen.
* **Safety.** Only the Steam, Apple, Wikipedia and YouTube API hosts and their image and video
  CDNs are contacted, over HTTPS. Redirects must stay on those hosts, and every download is size
  capped. Images are decoded and re-encoded before use. Video is decoded only from local files,
  inside the project's resource-limited ffmpeg wrapper. Downloads are kept in
  `gametagger-media/<game-id>/`, which git ignores. Only ffmpeg is required; ffprobe is not.

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
uv sync --frozen --extra dev          # plus ffmpeg on your PATH for trailers

# 1. Dry run (default): shows what Jev would receive and rough Jev and vision estimates. No model calls.
gametagger-genome fixtures/genome/hollow_orchard.dossier.json
gametagger-genome fixtures/genome/hollow_orchard.dossier.json --format json   # exact questions and evidence

# 2. Offline: runs the whole pipeline with mocks. Everything comes back "unknown"; this is not inference.
gametagger-genome fixtures/genome/hollow_orchard.dossier.json --offline

# 3. Build a dossier from store pages. This downloads screenshots and the trailer but calls no model.
export YOUTUBE_API_KEY=...            # optional: YouTube backup when a store page has no trailer
gametagger-genome --game-id stardew-valley \
  --steam-app 413150 --wikipedia "Stardew Valley" --save-dossier stardew/stardew.dossier.json

# 4. Live: an explicit opt-in. Keys come from the environment only.
export TYPESAFE_API_KEY=... ANTHROPIC_API_KEY=...
gametagger-genome stardew/stardew.dossier.json --live --observer-model claude-sonnet-5 \
  --output stardew/profile.json
```

The Hollow Orchard dossier describes a **fictional** game, and its text is synthetic.
`--categories setting,monetization` limits a run to some categories. `--no-video` skips trailers,
and `--no-media` runs on text only. A live run refuses to start when the rough Jev input estimate
exceeds `--max-estimated-tokens` (default 50,000), or when the vision estimate exceeds
`--max-observer-tokens` (default 80,000). The full sample needs about 33,000 estimated Jev tokens
in 6 requests. A game with 4 screenshots and one trailer adds about 10 vision requests and about
27,000 vision tokens. Any vision-capable Claude model enabled for your account works;
`claude-sonnet-5` passed the earlier integration check.

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
  "images": [{"id": "shot1", "path": "screens/shot1.png"}],
  "videos": [{"id": "trailer", "path": "media/trailer.mp4"}]
}
```

Source `type` is one of `store_metadata`, `developer_documentation`, `wikipedia`, `transcript` or
`other`. Image and video paths are resolved relative to the dossier file. `--image` and
`--video` add local files.

## What has and has not been verified

* Verified offline: 66 automated tests. They cover the vocabulary, claim splitting, evidence
  filtering, batching, strict validation and targeted retries, and partial failures. They also
  cover observer quarantine, the Steam, App Store, Wikipedia and YouTube parsers, and the network
  allowlist. The media tests check image re-encoding, HLS assembly, per-store caps, cinematic
  exclusion and the command-line safety gates.
* With real ffmpeg, the tests generate a synthetic 75-second video. Bursts come out 0.4 seconds
  apart with true timestamps: a frame's on-screen clock was checked against its recorded time.
  A synthetic fragmented-MP4 HLS stream was assembled and sampled, and gave the same timestamps as
  the plain MP4. Timing-tag questions received the trailer claims.
* **Not verified: MPEG-TS decoding.** Assembly of MPEG-TS HLS streams is tested at the byte
  level. The standalone ffmpeg used for local testing crashes on any TS file, so TS decoding was
  not exercised here. If a TS trailer fails to decode, the run records a note and continues.
* **Not yet verified: live quality, cost or latency.** No TypeSafe, Anthropic or YouTube key was
  available, and the network blocked Jev, Steam, Apple, Wikipedia and YouTube in the build
  environment. All adapters are tested against response shapes built for the tests, not live
  responses. The token estimates are heuristics, not provider billing. Whether TypeSafe accepts 60
  questions per request is also unconfirmed. If it rejects them, lower
  `--max-questions-per-request`.
* YouTube's numbered still images (`hq1.jpg`–`hq3.jpg`) are publicly served, but they are not a
  documented API feature. If they stop being served, the reference link is still recorded.

## Suggested next steps

1. Run a live check on 3–5 well-known games. Compare the profiles side by side with the original
   site's tags for the same games, then decide whether Jev earns its place for each category.
2. If rich mode is kept, add it to the website's Analyze flow behind the existing budget gate.
3. Calibrate the strong/likely display bands and the policy thresholds on human-reviewed labels.
4. Choose a Google Play data service and connect it through the `google_play_reference` slot.
5. Consider using Jev's **Score** primitive for ordered dials such as difficulty, story emphasis
   or session length. Score has no "insufficient evidence" option, so pair it with an
   evidence-gate question.
