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

### Rich mode media (September 24, 2026)

At the owner's request, rich mode now reads Steam and App Store pages by exact ID. It downloads
their screenshots and store trailer, and samples trailers into short frame bursts. Timing
attributes can therefore use `gameplay_clip` evidence. Cinematic and title-card bursts are left
out. The YouTube backup uses the Data API only, as the owner chose: it records a reference and
YouTube's published stills, and downloads no video. Google Play is a link-only slot until the owner
chooses a data service. The shared image loader no longer crashes on JPEG input, and ordered
windows accept source videos up to 30 minutes (website uploads keep their 60-second limit).
Offline tests only; no live provider, store or YouTube request was made. See
[GENOME_RICH_MODE](GENOME_RICH_MODE.md).

### Next: Jev versus previous-method benchmark (handoff, September 24, 2026)

The owner wants 100 games compared: the top 50 Steam games by concurrent players and the top 50
mobile games by grossing. The comparison is rich mode (Observer + Jev) against the original site's
single Claude call, on identical inputs. It should measure timing per stage, tokens, cost, tags per
game and accuracy, and end with charts and a short social-media write-up. Every figure must state
its sample, date and answer-key method.

Owner actions taken: API keys were added to the environment as `TYPESAFE_API_KEY`,
`ANTHROPIC_API_KEY`, `ANTHROPIC_WORKSPACE_ID` (if needed) and `YOUTUBE_API_KEY`, and network
access was requested for `api.typesafe.ai`, `api.anthropic.com`, `store.steampowered.com`,
`api.steampowered.com`, `steamstatic.com`, `en.wikipedia.org`, `itunes.apple.com`, `mzstatic.com`,
`www.googleapis.com` and `i.ytimg.com`. In a new session, first verify that each variable name
exists (never print values) and that each host is reachable.

Still needed from the owner before any paid run:
- A numeric spending limit. Estimates for one 100-game pass: vision Observer on Claude Sonnet 5
  about $8-10; previous method about $2 on Haiku 4.5 (standard) or about $9 on Opus 4.8 (deep);
  Jev about 3.3M input tokens at the owner's TypeSafe rate. Suggested: a $40 Claude cap plus a
  Jev cap, and a 10-game pilot first.
- The top-50 mobile grossing list (rank, name, App Store ID and/or Google Play package; chart
  region, platform and month). No reliable free official grossing source is known.
- The answer-key method. Recommended: a blind human primary genre for all 100 games plus about
  20 tags on about 30 games. Steam community tags are a cheaper, weaker PC-only option.
- Previous-method mode: Haiku standard, Opus deep, or both (recommended: both).
- Confirmation that non-game Steam chart entries (for example Wallpaper Engine) are skipped.

To build, none of which needs keys:
- A faithful adapter of the original `gametagger-web` tagger prompt (the decisions/legacy.py
  placeholder), run on the same dossier.
- A Steam most-played chart reader.
- A batch runner recording per-stage wall clock, tokens and cost.
- An old-59-to-new-100 genre crosswalk for the owner to approve.
- Scoring, charts and a write-up template.

### Benchmark tools built (September 24, 2026)

The owner decided the open questions. The spending limit is **$40 in total**. Mobile games come
from AppBrain's Google Play top-grossing games chart (US). Accuracy is judged by Steam user tags
plus the owner's own blinded review. The previous method runs on both Haiku 4.5 (standard) and
Opus 4.8 (deep). Steam non-games are skipped and listed.

`gametagger-compare` is built. See [JEV_VS_LEGACY_BENCHMARK](JEV_VS_LEGACY_BENCHMARK.md) for
steps, outputs and caveats. Its parts:

* chart readers and a frozen 100-game cohort (`experiments/jev-vs-legacy/cohort.json`, charts of
  2026-09-23 and 2026-09-24)
* exact-ID identity through Wikidata
* a Steam user-tag answer key
* shared dossiers, with a new Google Play listing reader that includes the store's MP4 trailer
* a faithful adapter of the original tagger (`decisions/legacy.py`, verbatim prompt and rules
  from `gametagger-web@4b710fd`)
* a budget-capped runner with per-stage timing, tokens and list-price cost
* draft crosswalks in `taxonomy/crosswalks/`
* scoring, a blinded review sheet, and an HTML report with a social card

Environment findings:

* The TypeSafe key was accepted by the free model-listing call; `jev-latest` is `jev-1.13.0` at
  $0.042 per million input tokens.
* The YouTube key works.
* `ANTHROPIC_API_KEY` is not visible to the agent here. The tools also read
  `GAMETAGGER_ANTHROPIC_API_KEY`, which the owner has added; a new session picks it up.
* After the owner widened network access, every needed host was reachable. Wikimedia
  rate-limits this shared address heavily, so identity and Wikipedia fetches wait and retry.
* `ffmpeg` must be installed in each session.

The only paid call so far is one live Jev check on Stardew Valley's text: 185 questions in 6 requests, 4.0 seconds, $0.0019. No Claude call has been made. Next step, in a session that can see the key: run `dossiers`, then a
10-game pilot, then the full run and `report`, all under the same $40 ledger.

### Benchmark run attempt (September 24, 2026): blocked on Anthropic credit (resolved below)

* The new Anthropic key (108 characters) is accepted by the free model-listing call once the
  `anthropic-workspace-id` header is sent; `ANTHROPIC_WORKSPACE_ID` is set and the tools send it.
  Haiku 4.5, Opus 4.8 and Sonnet 5 are all listed.
* Steam changed its store API: `appdetails` sometimes files its reply under another ID (a DLC or
  package), so most Steam games read as unlisted. Fixed: a reply is accepted only when its own
  `steam_appid` matches the requested game. Dossiers were rebuilt from scratch after the fix.
* The 10-game pilot was refused on every Claude request with "Your credit balance is too low to
  access the Anthropic API". Nothing was billed (30 zero-cost error rows in the ledger; the failed
  results were deleted so they are re-run). The runner now stops the whole run on this message
  instead of booking every remaining game as a failure.
* **Owner action:** add prepaid credit to the Anthropic organization that owns this key
  (Console → Plans & Billing), then re-run the pilot with `--budget-usd 39.99`.

### Benchmark measured (September 25, 2026)

All 300 runs finished (100 games x 3 methods) with no failures; 5 rich-mode games are `partial`
(thin evidence or one errored Jev question). Total spend **$20.67** of the $39.99 ledger cap, plus
the earlier $0.0019 Jev check. Sample: Steam most-played (2026-09-23) and Google Play US
top-grossing (2026-09-24), 50 each. Accuracy uses the 50 Steam games' top 20 player tags through
draft crosswalks.

| | Jev pipeline | One prompt, Opus 4.8 | One prompt, Haiku 4.5 |
|---|---|---|---|
| Player-tagged attributes found (all mapped) | 77% | 45% | 23% |
| Same, attributes both vocabularies name | 77% | 78% | 40% |
| Player-tagged attributes called absent | 0.8% | 5.9% | 3.7% |
| Attributes present per game (median) | 35 | 17 | 15 |
| Time per game (median) | 100 s (observe 94.5 s, Jev 5.9 s) | 12.1 s | 7.5 s |
| Cost per game (mean) | $0.153 (Claude $0.150, Jev $0.0028) | $0.040 | $0.006 |

Jev versus Opus on the shared vocabulary is -1 point (paired 95% interval -5 to +3): no clear
difference. In 34 of 100 games Haiku nested its answers where the original parser does not look,
so the old site would have recorded no tags; results keep that behaviour (Opus: 0). With every
answer readable, Haiku's all-mapped recall would be 40%.

Fixes made during the run: Steam `appdetails` replies keyed by another ID are matched by
`steam_appid`; rich mode quarantines malformed Observer statements one at a time (screenshots and
trailer windows) and allows 4,096 output tokens; a no-credit refusal stops the run; cancelled
jobs no longer crash the runner.

Published (private until the owner shares them):
* Home page (dashboard, September 27): https://claude.ai/artifact/26Pbg1Lbt3wzadN5b3qwMS. What is
  in the top 100 (genre mix, most common tags, PC versus mobile gaps, tags weighted by Steam peak
  players, top 10 versus the rest, where evidence runs out, Steam chart movers), the game library
  and tag dictionary, a short method and comparison. Built from
  `experiments/jev-vs-legacy/site/dashboard-template.html`; `web/` serves it at `/` with the
  benchmark write-up at `/benchmark`. Trends over time need a second weekly snapshot and the page
  says so.
* Benchmark write-up (the earlier results page): https://claude.ai/artifact/5pVfp8rgBXSy1rV3bx3KvG (charts, method diagram, tag
  dictionary, per-game table, LinkedIn kit). Sources in `experiments/jev-vs-legacy/site/`.
* Requests board: https://claude.ai/artifact/3MLmYUfDTkFgC9RFfkNiPU (organization-only; the owner
  approves requests, which are tagged in batches under a cap the owner sets).
* LinkedIn slides and post text: `experiments/jev-vs-legacy/linkedin/`.

Owner to do: fill `experiments/jev-vs-legacy/review/owner-review.csv` (494 rows, yes/no/unsure),
review the three draft crosswalks, confirm the 10 App Store title-and-developer matches in
`cohort.json`. Next improvements (evidence follow-up, recorded gameplay, lower cost, a deeper mobile
vocabulary) are planned in [NEXT_IMPROVEMENTS_PLAN.md](NEXT_IMPROVEMENTS_PLAN.md). Follow-up agreed: a public GitHub Pages site with a public request form.

### Cheaper image descriptions (September 25, 2026)

Built saved descriptions (identical requests are never paid twice), half-price batch describing
(`run --batch`, resumable with `--resume-batch`), and two cost-test arms. On the first 20 benchmark
games, Haiku 4.5 through the batch cost **$0.035 per game all in versus $0.170** for the benchmark's
Sonnet run, found 76.4% of Steam players' tags versus 78.5% (10 Steam games; not a measurable
difference at this size), kept 93% of the benchmark's present attributes and 95% of its genre
calls, but had more Observer statements quarantined (13.8 versus 1.2 per game). Brief Sonnet
descriptions with duplicate skipping cost $0.070 per game. Details:
`experiments/jev-vs-legacy/cost-test/README.md`. The test cost $1.99 for descriptions plus Jev;
ledger total $22.86 of the $39.99 cap. Also tagged Epic Plane Evolution for cloning work
(`experiments/single-games/epic-plane-evolution/`, $0.097).

### More store videos per game (September 27, 2026)

Rich mode can now sample several store videos per game instead of one:
* Steam videos named as gameplay come first, then highlights, up to three.
* The Google Play trailer is kept.
* App Store preview videos are read from the product page (`apps.apple.com`, exact app ID).
  Apple asks that previews be captured from the app itself.

Other details:
* Videos are taken one per store before a second from any store, and a failed download is
  replaced by the next.
* The per-game burst budget is shared across videos (at least two bursts each), so Observer cost
  does not grow with the number of videos.
* Options: `gametagger-genome --max-videos` (default 2) and `gametagger-compare dossiers
  --max-videos` (default 1, as in the benchmark).

Free check on 12 cohort games with `--max-videos 3`:
* All 4 Steam games got 2–3 videos (two had one video fail to download and fall back).
* 5 of 8 mobile games got the Google Play trailer plus 1–2 App Store previews.
* The other 3 (Royal Match, Kingshot, Last War) have no App Store preview and no direct Google
  Play video; their only video is a YouTube trailer, which is recorded as a reference and not
  downloaded.

No paid run yet.

YouTube gameplay videos (proof of concept, owner-approved on September 27 despite YouTube's
terms): `--youtube-gameplay N` on `gametagger-genome` and `gametagger-compare dossiers` finds the
N most-viewed uploads between one minute and an hour that name the game.

How videos are chosen:
* The short name is matched too ("Last War" for "Last War:Survival Game").
* Trailers, Shorts, "fake ads" compilations, reviews, reactions, hacks and mods are dropped;
  "fake ads" videos show the ads' invented gameplay, not the game.
* Uploads that call themselves gameplay or walkthroughs come first.

How videos are downloaded:
* The tool downloads a video-only copy at 480p or lower with yt-dlp (optional, like FFmpeg:
  on PATH or `GAMETAGGER_YTDLP`). Uploads longer than 15 minutes are cut to 15 minutes from
  the one-minute mark.
* Downloads are marked `community_video` with the channel in provenance.
* They share the per-game burst budget with store videos.

Live check:
* Search works. After the filters it picked real play for Royal Match, Kingshot and Last War.
* Every download from this cloud container was refused by YouTube ("Sign in to confirm you're
  not a bot"). YouTube blocks data-center addresses, and no attempt was made to get around
  that. Downloads are expected to work from a home connection.
* The first check also showed that the most-viewed "gameplay" results are often "fake ads"
  commentary, which is why the filter exists.

An automated-play pilot (AI tapping through a game on an emulator) was drafted, then dropped at
the owner's request; it was never merged.

### Scene-change sampler and automated Android player (September 27, 2026)

The owner asked for the YouTube video analyzer and an Android game player, with AI play
(reversing the earlier drop) and up to $2 of paid testing. Branch
`claude/android-player-youtube-systems`.

Built:
* **Scene-change ("systems") sampling** (`genome/systems.py`, Improvement 3):
  * One 8x8 average hash per second (free, local ffmpeg, decoded in 60-second chunks to stay
    under the decoder's CPU limit) splits a video into still screens and motion.
  * Repeated still screens are dropped. A recording's systems contexts (shop, currency, event,
    social, progression, ad) each get one burst first.
  * About a third of the rest goes to motion, then distinct stills round-robin across
    contexts, and any budget left fills the largest gaps.
  * Still screens get 3-frame bursts instead of 6.
  * `--burst-strategy auto` (the new `gametagger-genome` default) uses it for
    `community_video` and `gameplay_recording`. Store trailers keep `even-bursts-v1`, so the
    benchmark's sampling is unchanged.
* **Recordings in dossiers.**
  * `VideoSource` gains the role `gameplay_recording`, plus `capture_method`
    (owner / automated_play) and `capture_contexts` (time ranges with a fixed label set).
  * Claims read `[menu, 12.0-12.8s, capture context: the shop] ...`.
  * When a recording is present, Jev's reading guide adds that a capture context is
    navigation, not observation. States without recordings are byte-identical to before.
* **`gametagger-genome --budget-usd/--ledger`.** Live runs can now be capped on the shared
  ledger, as `gametagger-compare` already was.
* **`gametagger-play`** (`src/gametagger/play/`):
  * adb device wrapper, segmented screen recording joined at a constant 10 fps.
  * Claude picks one action per screenshot through a validated `act` tool, playing normally
    for 5 minutes and then visiting the systems goals.
  * Code-level guards close purchase screens (activity names containing billing, purchase and
    similar words) and undo leaving the game.
  * Outputs: a recording, steps, screenshots, a session summary and a dossier.
  * `--check` is free; live runs need `--budget-usd`.
* **Mac scripts** (`scripts/mac/`) and the plain-language guide `docs/MAC_TOOLS.md`. Keys are
  read from `~/Claude Workspace/gametagger/gametagger.env`, outside the repository.

Measured:
* 417 tests pass offline (1 live test skipped); ruff clean.
* **Live check, $0.0468 in total** (cloud ledger, 8 Claude calls; no Jev, store or YouTube
  call, because this cloud session cannot reach them). The player agent was run on three
  synthetic game screens (menu, shop, purchase confirmation):
  * The first version asked for coordinates on a 0-1000 grid. Claude answered in image
    pixels, so the tap meant for "Cancel" would have hit "Buy".
  * Coordinates are now image pixels, scaled to the device. Sonnet 5 then hit Shop and Cancel
    correctly and scrolled the shop instead of tapping a price.
  * Haiku 4.5 returned an invalid action name on the shop screen. The player defaults to
    Sonnet 5, and five malformed answers in a row stop a session.
* The owner set `OBSERVER_MODEL=claude-sonnet-5` for this work.
* The same session also spent $0.069 checking a separate project, the owner's long-session
  "teardown player" (kept outside this repository), with the same Anthropic key. The session's
  total spend was $0.116.
* A marketing trailer is on branch `claude/marketing-trailer` (`experiments/trailer/`). It
  involved no paid calls.

Not done:
* No real emulator session and no real YouTube download has run. Both need the owner's Mac;
  see `docs/MAC_TOOLS.md`.
* Suggested first paid test, within the $2 authorization: one YouTube game and one 6-minute
  Android session.
* Pilot comparison (unknown share and blind-review accuracy on monetization and live-ops tags,
  recorded versus store-only) is still open, as in Improvement 3.

### Vocabulary v2 draft (September 27, 2026)

Improvement 7, step 1:
* Drafted 51 mobile tags for owner review: 13 meta layers, 21 live operations and offers,
  5 advertising, and 12 follow-ups asked only when their parent tag is present.
* Files: [VOCABULARY_V2](VOCABULARY_V2.md) and
  `taxonomy/drafts/genome_tags_v2_additions.draft.yaml`.
* Not loaded by the pipeline. v1 is unchanged.
* `tests/test_vocabulary_v2_draft.py` checks the draft is well formed, collides with no v1 or
  pilot ID or label, and that every follow-up names a real parent tag.
* No paid calls.

Next:
* The owner's decisions listed in the draft.
* Then the loader's `requires` field and conditional asking.
* Then a run on the 5-game recording pilot.

### Fold & Fly prototype and the Epic Plane teardown (September 29, 2026)

A separate project, kept outside this repository: a fairer version of Epic Plane Evolution,
built overnight in three.js from the teardown player's measurements. No GameTagger code
changed and no paid run came from this repository; the game itself makes no model calls.

* Where it lives: the owner's Mac at `~/Claude Workspace/fold-and-fly` (a git clone, with
  `fold-and-fly.bundle` beside it); the playable "Fold & Fly" artifact on claude.ai; the
  "Fold & Fly: morning report" doc.
* The original, measured by the teardown player (first 8 hours, one free player): 0.97 forced
  ads per flight, 19.4 per play-hour, 27 s median each (Pangle and AppLovin). After 13 hours
  of play it was still on its first plane, and an energy limit (5 flights, refilled on a timer)
  appeared at about 11 hours. From about 8 hours in, two copies of the teardown player wrote
  into the same run, so only per-flight ratios are used after that point.
* Paid spend: none here. The teardown player (separate project) shows $6.95 in its own ledger
  for that run.
* Fold & Fly, simulated (8 bot players, 6 hours): 0.11 forced ads per flight for a good player
  (11% of the original) and 0.05 for a casual one; 4.1 per hour (21%) and 6.6 per hour (34%).
  A 12-minute gap brings the casual player to 23%.
* Left for the owner: name and theme, pacing, the ad gap, the remove-ads price, feel on a real
  phone, and permission to install the teardown player's optional-ad guard (commit `375c332`
  in the teardown-player repository).
* Update, same day (owner feedback: "fairly basic, geometric shapes"; "planes start almost fully
  upgraded"): each plane now starts as a bare fuselage and gains wings and propeller, tail,
  cockpit and paint, boosters and gold trim every five levels, as in the original. Trees, bushes,
  flowers, rocks and ruin pieces are now real models from CC0 packs (Quaternius Stylized Nature
  MegaKit, Kenney kits), with the owner's approval. Still no paid runs.
* Update, September 29-30 (owner feedback: the bare fuselage "looks like a rotating turd"; put it
  in the slingshot as in the original; wings before the propeller; one-time rocket jets; real
  ground effect; a UI like the original's, including its shaking gift chest):
  * The first plane is a card tube on wheels with an open nose and cockpit, resting in the
    slingshot's rope in the hangar, shot from the front right as in the original. Stages are now
    bare fuselage, wings, propeller (the engine), tail and rudder, cockpit and paint, big
    propeller and gold trim.
  * Ground effect follows the FAA handbook's figures (about 25% less induced drag at a quarter
    span, 50% at a tenth), measured against a 15 m "span" so it can be used in play.
  * Rocket jets: unlocked with wings (3 free), bought with coins or found in the chest, one pair
    per flight. The chest opens every 2 hours (first after 3 flights), with no ad.
  * Hangar, launch and flight report restyled after the original.
  * Simulated again (6 bots): a good player sees 0.107 forced ads per flight (11% of the
    original) and 5.1 per hour (26%, up from 21% because the glider stage has shorter flights);
    a casual player 0.047 per flight (5%) and 6.7 per hour (34%). First new plane at 23 minutes
    (was 22). Bots don't use rocket jets.
  * Tests: 22 rule tests and 10 browser checks pass. The Mac copy is at commit `bae3613`.
    Still no paid runs.
* Update, September 30 (owner: upgrade prices should rise with a new chassis; give course 2 an
  interesting theme, such as a town or a beach):
  * Prices now step up when the wings (x1.3) and the propeller (x1.65) are fitted, and each new
    plane's prices and coin values scale up together. Before, the propeller stage's upgrades cost
    about a third of a flight each, and the old course's winnings bought 15-21 of a new plane's
    upgrades at once (its whole bare-fuselage stage); now 8-12. `sim/pace.mjs` measures this.
  * Course 2 is a harbour town built from Kenney's CC0 building blocks (mirrored in the public
    repository Paumen/Taalei): a beach and promenade, main streets, a square with a fountain and
    clock tower, the harbour with docks, boats and a lighthouse, a winding alley with bridges.
    It draws in 156-233 calls and 229-344k triangles, about as much as course 1.
  * Simulated (6 bots): good players 0.107 forced ads per flight (11% of the original), 5.3 per
    hour (27%), all six planes in 4 hours; casual players 0.048 per flight (5%), 6.7 per hour
    (34%).
  * Tests: 24 rule tests and 10 browser checks pass. The Mac copy is at commit `4d8b078`. Still
    no paid runs.

### Trailer: play, learn, build (October 2, 2026)

The owner asked to extend the trailer: keep how the tag database was built and how tags are
assigned, and lean into the newer loop (play a game for hours, learn what makes it work, build
a playable prototype in days). Branch `claude/trailer-prototype`. No paid calls.

* `web/trailer.mp4` is now 82 seconds in ten parts (was 54 s in six). The first five (NitroGen,
  vocabulary, Observer, Jev, top-100 site) keep their animation and play a little faster. The
  invented "Cloud Hopper" shop and guild scene is replaced by four new ones:
  * Play: the AI player's run on the plane game (13.2 hours; in the first 8 hours, 159 flights
    and 154 forced ads), with four of its own notes, trimmed. The phone screens are invented and
    labelled; the original game is not named and none of its screenshots are used.
  * Learn: the store-page tags from `experiments/single-games/epic-plane-evolution/tags.json`
    (Ad-supported, Energy or stamina timers and Pay-to-progress were "not enough evidence")
    next to what playing measured; the core loop; keep / drop / replace from the Fold & Fly
    design.
  * Build: 16 seconds of real Fold & Fly footage (hangar upgrade, slingshot launch, valley
    arches, a finish line, the harbour town with rocket jets, all six planes) beside four
    figures: first playable overnight, 1 forced ad in 9 flights and the first new plane in 25
    minutes (both simulated), six planes and six courses.
  * Pitch: spot, play, learn, build. "Find out if a feature is fun before you staff a team."
* The footage (`experiments/trailer/footage/prototype.mp4`, 3.6 MB, and `prototype.json`) was
  recorded by Fold & Fly's new `scripts/trailer-clips.mjs` (Fold & Fly commit `9f705b5`), which
  runs the game on a virtual clock so every frame is exactly 1/30 s apart. The Mac copy
  of Fold & Fly is now at that commit.
* Cost figure shown: model calls for the AI player's whole run were $6.95 paid plus $76.69 of
  subscription calls at API prices, so the video says "about $84 at API prices".
* The site's film blurb now says 82 seconds and lists the new parts. New poster from the Build
  scene.
* Site (owner: "add it to the website ... verbiage about the ability to play games"): a new
  "Play-testing" section after "Where the evidence runs out", linked from the header, footer and
  the pipeline's "Play" step. It shows the plane game's store-page tags next to what 13 hours of
  play measured, six measured figures, three of the AI player's notes, what play-testing adds
  (pacing, economy, why it works) and the step to a playable prototype, with a button that
  starts the film at 0:31. It says plainly that this is one game, played as a pilot, and that
  the top 100 are not play-tested yet. The same edits are in
  `experiments/jev-vs-legacy/site/dashboard-template.html`, so a rebuild keeps them. Checked at
  1280 px (light) and 390 px (dark); the film button was checked with a WebM copy of the film,
  because the headless browser here cannot play H.264.

Left for the owner:
* Merge PR #14 to put the film and the Play-testing section on gametagger.vercel.app (CI and
  the Vercel preview passed; the session's merge was blocked pending the owner's review).
* Whether to name the original game in the video (it is named in the repository docs).
* The end-card line ("Learn why hit games work. Prototype the next one in days.") and the
  length; a 30-second cut for social could reuse the Play, Learn and Build scenes.
* The first new plane "in 25 minutes" and "1 in 9 flights" are bot simulations, labelled as
  such on screen; nobody has played Fold & Fly on a phone for pacing yet.

### Site split into pages (October 5, 2026)

The owner: on a phone the site was one very long page. Branch `claude/site-pages`. No paid
calls.

* The home page is now six views of one file: Home (headline, example profile, how it works in
  four steps, key numbers, and cards to each page), Dashboard (the charts, with a row of links
  to each chart), Games, Tags, Play-testing and How it works. Each has its own address
  (`/dashboard`, `/games`, `/tags`, `/play-testing`, `/how-it-works`) through rewrites in
  `web/vercel.json`, the browser's back button works, and switching pages does not reload.
* Old links still work: `/#library`, `/#game-...`, `/#tag-...` open the right page. Tag and game
  links in the charts jump to the Tags and Games pages. A tag link now opens the dictionary on
  that tag's category instead of all 189 tags.
* On a phone the page links are a sideways-scrolling tab row under the logo, with the current
  page underlined; every page ends with Previous and Next links and the request box.
* Height on a 390-px-wide phone: 26,149 px before; now Home 3,269, Dashboard 11,476, Games
  3,426, Tags 6,867, Play-testing 3,122, How it works 2,767.
* `experiments/jev-vs-legacy/site/refresh_web.py` rebuilds `web/index.html` from the template
  with the published data (`--check` confirms they match). Checked in headless Chromium at
  390 px and 1280 px, light and dark, with no page errors.

### Vocabulary v2 approved (October 5, 2026)

The owner answered the six questions in [VOCABULARY_V2](VOCABULARY_V2.md) (PR #13).
No paid calls.

* All 51 tags kept. (The draft said 52 and 22 live-ops tags; the file has always held 51 and 21.
  The counts are corrected.)
* A "likely" parent unlocks its follow-up questions; a missing "Contains ads" notice is not
  evidence of no ads; the weekly event-cadence tag stays, decided from weekly play-tests of the
  top-performing games; no Steam or commercial crosswalks for v2.
* Open: whether mobile keeps the three v1 umbrella tags. The owner wants to retag the Google
  Play top 50 with the v2 tags first. The September run's descriptions were not kept, so the
  retag re-describes each game: about $1.80 for 50 games with Haiku describing or about $7.70
  with Sonnet (from the September costs), plus under $0.25 of Jev. Needs a budget number.
* Next: promote the tags into `taxonomy/genome_tags_v2.yaml`, teach the loader `requires` (asked
  only when the parent is strong or likely, otherwise "not evaluated"), show the new categories
  in the site's dictionary, then the retag.

### Vocabulary v2 built, and describing on the owner's Claude plan (October 5, 2026)

Branch `claude/mobile-retag-v2` (on top of PR #13). No paid calls while building.

* **v2 in the pipeline.** `taxonomy/genome_tags_v2.yaml` (moved from `taxonomy/drafts/`)
  `extends` v1, so all 189 v1 tags load first, unchanged, then the 51 new ones: 240 in all.
  `--vocabulary v2` on `gametagger-compare run` (v1 stays the default). The 12 follow-ups
  (`requires`) are held back and asked in a second round only when their parent came back
  present, strong or likely; otherwise they are "not evaluated" with the reason, never absent.
  Results record `vocabulary_version` and `followups_asked`. Not done: the site's dictionary.
* **`--use-max-plan`.** Ported from the owner's teardown player
  (`src/gametagger/claude_code.py`): the Observer's calls run through `claude -p` (Claude
  Code logged in to the owner's subscription), with API keys hidden from Claude Code. Replies
  come back as ordinary API messages, so the Observers, saved descriptions and meter are
  unchanged. Plan calls book $0 in the ledger with `plan: subscription` and the API-equivalent
  price; they reserve nothing against the cap, so `--budget-usd` caps Jev alone. It pauses at
  90% of the 5-hour window (waits up to 6 hours for the reset) and stops at 70% of the week.
  `gametagger-compare check-plan` checks the login with one tiny call.
* **Retag kit.** `scripts/mac/retag.sh` (Google Play top 50 of the site's list, store pages,
  v2, Observer on the plan, Jev capped at $1.00 in its own ledger,
  `benchmark-runs/mobile-retag-v2/`), and `experiments/mobile-retag-v2/summarize.py`, which
  writes tag states and counts only. The owner authorized $1 of Jev for this run.
* Safety from an independent review: Claude Code gets no API keys or other secrets (every
  `ANTHROPIC_*`, `CLAUDE_CODE_USE_*`, key, token and secret variable is removed, except the
  plan's own `CLAUDE_CODE_OAUTH_TOKEN`); a run refuses to start unless `claude auth status`
  shows a subscription login on Anthropic's own service, and stops if Claude Code reports an API
  key source or paid extra usage. Claude Code failures (crash, timeout, refused model) fail the
  game before Jev is paid and count as retryable; five in a row stop the run. Text in a
  screenshot ("Daily limit reached") can no longer be mistaken for a plan limit. Plan and API
  descriptions are saved apart. A v2 run refuses to keep v1 results in the same folder.
* Checked against the real Claude Code (2.1.289, in the cloud container): `check-plan` sent a
  64-pixel image and a schema and got "red, 4" back; the setup record showed no API key source
  and all five trimming flags. That one call used the plan; nothing was paid.
* The plan's `claude` cannot run in the Cowork VM that the desktop bridge's shell uses (it only
  takes a text prompt), and the cloud container cannot reach the stores or TypeSafe, so the run
  happens in the Mac's own Terminal.
* Tests: `tests/test_vocabulary_v2.py`, `tests/test_claude_code.py` (a fake `claude`; one
  end-to-end retag of a fake game). 445 passed, 1 skipped.

### Google Play top 50 retagged with v2, on the owner's plan (October 5, 2026)

Run on the owner's Mac with `scripts/mac/retag.sh` (started from a Finder launcher, `Start
GameTagger retag.command`, beside the code in `~/Claude Workspace/gametagger/`). Results:
[`experiments/mobile-retag-v2/`](../experiments/mobile-retag-v2/README.md).

* **Paid: $0.19 of Jev** (480 requests) under the owner's $1.00 cap, in its own ledger
  (`benchmark-runs/mobile-retag-v2/ledger.jsonl` on the Mac). Claude: 523 calls on the plan,
  $0 in API money, $8.16 at API prices. Plan use ended at 75% of the 5-hour window and 23% of
  the week. A first attempt stopped at `check-plan` because the 5-hour window was full; nothing
  was spent.
* 50 of 50 games tagged (45 complete, 5 partial), about 100 s each, 45 minutes in all.
* New tags from store pages: 9% of 2,087 questions decided (185 present, 4 absent, 2
  conflicting); median 4 present per game; ads almost never decided; 20 of 51 tags never
  present. Follow-ups: 137 asked, 3 present.
* v1 answers match the September run on 98% of game-tag pairs.
* Umbrella tags: the broad ones often fire alone ("Ad-supported" in 19 games with no specific ad
  tag), so they stay until recordings or play-tests can test the specific tags.

Left:
* The site's tag dictionary does not show the new categories yet, and the site still shows v1.
* Recorded gameplay (the 5-game pilot or the owner's weekly play-tests) is what can decide most
  new tags; Improvement 7's bar (half decided, 90% review agreement) is not met from stores.
* PR: this branch (on top of PR #13).

### YouTube gameplay pilot for the v2 tags (October 5, 2026)

5 games (Royal Match, Monopoly Go, Last War, Coin Master, Candy Crush Saga), store pages plus up
to 2 YouTube gameplay videos each, 12 bursts with the scene-change sampler
(`scripts/mac/retag-youtube.sh`; `run` now takes `--bursts` and `--burst-strategy`).
* Paid: **$0.03 of Jev** under a $0.25 cap. Claude: 60 calls on the plan, $1.19 at API prices.
  The run waited about three hours for the plan's 5-hour window, as designed.
* New-tag answers decided 13% to 15% on the same games; present 24 to 29. No ad tag decided.
  Details: `experiments/mobile-retag-v2/README.md`.
* Not worth scaling: play-tests are what can decide shop, offer and ad tags.
* The Mac copy (`~/Claude Workspace/gametagger/repo`) has two stale git lock files
  (`.git/HEAD.lock`, `.git/objects/maintenance.lock`) that this session could not delete.
