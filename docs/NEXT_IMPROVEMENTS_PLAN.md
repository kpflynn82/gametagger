# Next improvements: implementation plan

September 27, 2026. This plan expands four improvements from the review of the 100-game benchmark:
asking for more evidence (2), better evidence than store media (3), lower cost (4) and a deeper,
mobile-focused tag set (7). Every step keeps the architectural rules in `AGENTS.md`: the
Observer describes and never tags, "not observed" never means "absent", Jev's full distributions
and evidence provenance are kept, and live inference stays budget-capped.

## Where we start

Measured on the frozen top-100 cohort (charts of September 23 and 24, 2026):

* Jev leaves **76% of tag questions as "not enough evidence"**. Evidence runs out fastest in
  themes, accessibility, world structure and narrative. For mobile teams the painful gaps are
  in live features: ads were settled for only 22 of 100 games, and energy timers, daily rewards
  and guilds are mostly unknown.
* Store flags already work when they exist. Of the 18 Google Play games whose listing says
  "Contains ads", Jev marked ads present or likely for 17 (one conflicting). For the 32 without
  the notice, it said "not enough evidence" 28 times, as the rules require.
* Cost is almost all Claude describing images: $0.150 of $0.153 per game in the benchmark. A
  20-game test describing with Claude Haiku in half-price batches cost **$0.035 per game** with
  recall within about 2 points, 93% of present tags kept and 95% genre agreement.
* The vocabulary has 189 tags in 14 categories. Mobile monetization and live operations are
  covered by 8 business-model and 15 engagement tags. The analyst-built product closest to this
  (GameRefinery) tracks about 260 mobile features.

## Improvement 2: act on "not enough evidence"

**Goal.** When Jev can't decide a tag, go and get the specific evidence that could decide it,
then ask again. Stop when the tag is decided, the sources run out, or the budget for that game
is spent.

**What exists.** Every Jev decision already carries an `action`. Undecided tags come back as
`acquire_evidence` (`src/gametagger/domain.py`), and each tag lists the evidence types allowed
to answer it (`allowed_evidence` in the vocabulary). Nothing acts on this yet.

**Design.**

1. **Evidence planner.** A new module (`src/gametagger/genome/planner.py`) takes a finished
   run and groups undecided tags by the evidence that could settle them. For example:
   `monetization_ads` → store fields or gameplay footage; `engagement_co_op` → store feature
   list or gameplay footage; `feature_controller_support` → store feature list. The mapping
   comes from `allowed_evidence` plus a short table of which source can supply each evidence
   type. The Observer is never told which tags are being chased, so it keeps describing
   neutrally.
2. **Targeted fetchers.** Each missing evidence type maps to a fetcher with a known cost.
   * Free store fields first: Steam feature categories, Google Play's ads and in-app purchase
     notices, and App Store in-app purchase listings.
   * Then paid Observer work on new media (Improvement 3).
   * Fetchers return `EvidenceItem`s with source, timestamp and hash, like today's dossier.
3. **Re-decide only what changed.** After new evidence arrives, Jev is asked again only for the
   tags whose allowed evidence grew. Earlier decisions stay in the record with their evidence,
   so a flip from unknown to present is traceable.
4. **Stopping rules.** There is a per-game limit on rounds (default 2) and on spend (default
   2¢ extra per game). A tag that is still unknown after its sources run out stays unknown and
   is labelled with what was tried.
5. **Report it.** Each game gets "tags settled by follow-up" and "tags still unknown, sources
   tried" in its record, and the site shows them.

**Owner decision needed.** Google requires developers to declare ads and in-app purchases.
Should a missing "Contains ads" notice count as evidence of *no* ads? Today it counts as
nothing, which is the safe default. Treating a required disclosure as explicit evidence of
absence would settle about 30 more mobile games, but it is a policy choice, not a bug fix. It
would be written into the evidence policy with its own version number.

**Tests.** Offline tests with injected fetchers and a mock Jev:
* the planner picks the right fetcher per tag;
* only affected tags are re-asked;
* stopping rules and the spend cap hold;
* unknown never turns into absent without explicit evidence.

**Done when.** On the 100-game cohort, the unknown share drops measurably on the targeted tags,
no present/absent flips appear that the blind review marks wrong, and the added cost stays
under 2¢ per game.

**Effort.** About 3–4 days of build plus one budgeted run.

## Improvement 3: better evidence than store media

**Goal.** See the parts of a game that store pages hide, such as the shop, timers, ad
placements, event screens, social systems and progression menus. Collect this evidence in a way
that stays legal and repeatable.

**Why.** Store screenshots and trailers are marketing. They show combat and art style well,
which is where Jev is already strong. They rarely show the systems product and monetization
teams ask about.

**Status (September 27).**
* Store videos are done: several Steam videos with gameplay-named ones first, and App Store
  preview videos. See EXECUTION_STATUS.
* Automated play on an emulator was drafted but not merged. This session's safety check blocked
  running it as an autonomous agent, so it waits on the owner's decision.

**Sources, in order of preference.**

1. **Owner-supplied recordings (best quality, clearest rights).** A short capture protocol for
   whoever plays the game:
   * the first 10 minutes;
   * the shop and any currency screens;
   * one event or live-ops screen;
   * the social or guild screen;
   * one ad, if any appears.

   Files stay private (git-ignored, like `benchmark-runs/`), and only the Observer's text
   descriptions and hashes are kept in results. This fits the brief's rule against exposing
   private footage.
2. **Developer press kits and official channels.** Official gameplay videos, which are more
   representative than trailers. `youtube_search` already finds official trailers and falls
   back to the most-viewed gameplay video. It can be extended to prefer official gameplay
   uploads. Clips are sampled as still frames through YouTube's published thumbnails or the
   existing burst method, never re-published.
3. **Store structured data (free, see Improvement 2).**
4. **Community footage (last resort).** Used only when 1–3 are missing, marked as lower-trust
   evidence in provenance, and never used to mark a tag absent.

**Design.**

* A new evidence type is optional. The existing `gameplay_clip` type already covers "short
  bursts of consecutive frames". Recordings get a `capture_context` field (first session, shop,
  event, social) so Jev's questions can weigh a shop screen properly for monetization tags.
* The burst sampler (`genome/media.py`) gets a "systems" strategy for long recordings. It
  detects screen changes (reusing the average-hash dedupe from the cost work) and keeps one
  burst per distinct screen, so a 10-minute recording costs about the same as today's trailer.
* The Observer prompt and boundary rules stay unchanged. It still describes what is visible
  ("a timer reading 02:14:59 above a locked chest") and never labels it ("energy system").

**Tests.** Offline fixtures with synthetic frames: the scene-change sampler keeps distinct
screens and drops repeats, capture context is carried into claims, and provenance marks each
source tier.

**Pilot.** Record 5 mobile games from the cohort with the protocol. Compare unknown share and
blind-review accuracy on monetization and live-ops tags against store-only runs.

**Effort.** About 3 days of build, plus about an hour of play and recording per game for the
pilot.

## Improvement 4: lower the cost per game

**Goal.** Make the $0.035-per-game setup the standard, confirm it on the full cohort, and stop
paying twice for evidence that hasn't changed.

**Steps.**

1. **Confirm on 100 games.** Re-describe the 80 games not in the 20-game test with Claude Haiku
   through the half-price batch (`--arms rich-haiku --batch`). The expected spend is about
   $2.60. This needs a numeric budget authorization from the owner, as always. Compare against
   the benchmark with `cost-test/compare.py`.
   * Adopt Haiku if recall stays within 3 points, present-tag agreement stays at 90% or
     higher, and no category loses more than 5 points.
   * Otherwise fall back to the "brief + skip near-duplicates" Sonnet setup ($0.070 per game).
2. **Make the winner the default.** Rich mode reads its Observer model and batch setting from a
   single config, and the result records which one ran.
3. **Pay once per image.** Saved descriptions are keyed by the exact request. For weekly
   re-tagging, add a content hash of each image and trailer segment: if the store media hasn't
   changed, reuse last week's descriptions and only re-ask Jev (a fraction of a cent).
   * Expected weekly cost for an unchanged game: under 0.5¢.
   * Expected weekly cost for the full top 100 with typical store churn: under $1.
4. **Quarantine watch.** Haiku produced more malformed statements (13.8 quarantined per game vs
   1.2). Track this per run and alert if it rises, since quarantined statements are evidence
   thrown away.

**Tests.** Hash-based reuse returns stored descriptions for unchanged media and re-describes
changed media. The ledger books reused descriptions at zero new cost. The budget cap still
holds when batching.

**Done when.** The 100-game Haiku run meets the adoption bar and a repeat weekly run of
unchanged games costs under 0.5¢ each.

**Effort.** About 2 days plus the budgeted run.

## Improvement 7: a deeper, mobile-focused tag set

**Goal.** Cover the features mobile product, monetization and live-ops teams track, and say how
a feature is done, not only whether it exists.

**Design.**

1. **Vocabulary v2 draft (new tags).** About 40–60 new tags in three groups, each with a plain
   definition, allowed evidence and a note on what must be visible:
   * **Meta layers:** base building, collection albums, character roster, idle rewards, merge
     board, decorating or renovation, story chapters as progression.
   * **Live operations:** limited-time events, season structure, event pass, login calendar,
     lucky wheel or spin, piggy bank, first-purchase offer, tiered offers, starter pack, VIP
     levels.
   * **Ads:** rewarded video, interstitials, banners, ad removal purchase.
2. **Implementation depth.** For a small set of high-value features (battle pass, gacha,
   energy, ads, live events), add follow-up questions that Jev answers only when the feature is
   present. For example: "battle pass has a free and a premium track" and "gacha shows its
   drop rates". These are separate tags, so "not observed" still never becomes "absent".
3. **Versioning.** The new tags ship as vocabulary `genome-tags-v2`. Results record the
   version, the site's dictionary shows it, and v1 results stay comparable because v1 tags are
   unchanged.
4. **Crosswalks.** Map the new tags to Steam tags where they exist, and draft a mapping to
   GameRefinery-style feature names so buyers can compare. Both stay drafts until the owner
   approves them.
5. **Dependence on Improvement 3.** Most new tags need shop, event and ad screens to decide.
   Without recorded gameplay they will mostly come back unknown. Ship the vocabulary with the
   recording pilot, not before.

**Tests.** Vocabulary loads and validates, every new tag has allowed evidence and a definition,
follow-up tags are only asked when the parent is present, and the site's dictionary renders the
new categories.

**Done when.** On the recorded pilot games, at least half the new tags are decided, and the
blind review agrees with 90% or more of the present calls.

**Effort.** About 2 days to draft and review the tag list with the owner, and 2 days to build.

## Order and budget

| Step | Depends on | Build time | Live spend (needs authorization) |
|---|---|---|---|
| 4.1 Confirm Haiku on 100 games | none | half a day | about $2.60 |
| 4.2–4.4 Default setup, image hashes, quarantine watch | 4.1 | 1.5 days | none |
| 2 Evidence planner and free store fields | none | 3–4 days | about $1 test run |
| 3 Recording protocol, scene sampler, 5-game pilot | 2 (fetcher shape) | 3 days + recording | about $1 |
| 7 Vocabulary v2 with depth questions | 3 pilot | 4 days | about $1 |
| Weekly re-tag of both charts, trend view on the site | 4.3 | 1 day | under $1 a week |

Total live spend for the plan is under $10, well inside the remaining $17 of the $39.99 cap.

## Decisions for the owner

1. Budget authorization for the 100-game Haiku confirmation run (about $2.60).
2. Whether a missing Google Play "Contains ads" notice may count as evidence of no ads.
3. Who records the pilot games, and which 5 (suggestion: 2 puzzle, 1 casino, 1 4X strategy,
   1 RPG from the mobile chart).
4. Approval of the vocabulary v2 draft before it is built.
5. The blind human review sheet, which is still the only way to measure wrong "yes" answers.
