# Vocabulary v2 draft: mobile meta, live ops and ads

Status: **approved by the owner on October 5, 2026**, with all 51 tags kept (Improvement 7,
step 1). The pipeline does not use these tags yet: the loader and conditional questions come
next (see "After approval"). The machine-readable draft is
[`taxonomy/drafts/genome_tags_v2_additions.draft.yaml`](../taxonomy/drafts/genome_tags_v2_additions.draft.yaml).
`tests/test_vocabulary_v2_draft.py` checks that it stays well formed and never collides with
v1.

## What changes

* **51 new tags in 4 new categories.** v1's 189 tags are unchanged, so v1 results stay
  comparable. The new version will be `genome-tags-v2` (189 + the approved additions).
* **Meta layers (13):** the systems wrapped around the core loop.
* **Live operations & offers (21):** events, schedules, currencies and offers.
* **Advertising (5):** how ads are shown and what players can do about them.
* **Implementation details (12):** follow-up questions asked **only when the parent tag is
  present**. For example, "the battle pass has a free track" is asked only if a battle pass was
  found. Otherwise the answer is "not evaluated", never "absent".
* Each tag has a plain definition. Where it matters, it also says what must be visible or
  documented before the tag can be present.
* The same rules as v1 apply: unseen is never "absent", and every tag keeps its evidence.

## Why these need recorded gameplay

Almost all of these show up only on screens that store pages rarely show:

* the shop;
* offer pop-ups;
* event and pass screens;
* guild menus;
* ads themselves.

From store pages alone they would mostly come back "not enough evidence". The plan therefore
ships v2 together with the 5-game recording pilot, which the automated Android player
(`gametagger-play`) or your own recordings can now provide.

## Owner's decisions (October 5, 2026)

1. **Keep, cut or rename:** keep all 51 as drafted.
2. **The v1 umbrella tags** ("Daily rewards or quests", "Auto-play or idle progress",
   "Ad-supported"): **undecided for mobile.** The owner wants to retag the Google Play top 50
   with the v2 tags as the test, and doubts the broad tags are needed for mobile. They stay in
   the vocabulary until that retag shows whether the specific tags cover them; v1 results and
   the PC games keep using them either way.
3. **"Likely" unlocks follow-ups:** yes. A parent decided "strong" or "likely" counts as present
   for its follow-up questions.
4. **A missing Google Play "Contains ads" notice:** not evidence of no ads.
5. **Weekly event cadence:** keep. The owner plans to play-test the top-performing games about
   once a week, so cadence is decided from those dated sessions, and only for those games.
6. **Crosswalks:** no Steam crosswalk for the v2 tags (the owner does not rate Steam's player
   tags), and no mapping to commercial feature lists such as GameRefinery's.

## Meta layers (13)

Systems wrapped around the core loop that drive long-term progression.

| Tag | Definition | Must be visible or documented |
|---|---|---|
| **Merge board** `meta_merge_board` | Players combine identical items on a board to create higher-tier items. | Present only when a grid of items and a merge (two alike becoming one higher item) is shown or described. |
| **Decorating or renovation meta** `meta_renovation` | Progress earned in the core game is spent to restore, build or decorate rooms or areas. | Needs an area being restored or decorated with a cost paid in a progress currency (for example stars). |
| **Story chapters as progression** `meta_story_chapters` | Finishing levels unlocks chapters or episodes of an ongoing story. |  |
| **Collection albums** `meta_collection_album` | Sets of collectible cards, stickers or items that give rewards when a set is complete. | Needs an album or set screen, or a store claim about completing sets or card collections. |
| **Character roster** `meta_character_roster` | Players collect many distinct characters or heroes, level them and choose which to field. |  |
| **Star-up from duplicates** `meta_duplicate_star_up` | Duplicate copies or shards of a character or item raise its rank, stars or tier. |  |
| **Offline earnings** `meta_offline_earnings` | Resources build up while the player is away and are claimed on return. | Distinct from auto-battle. Needs a claim screen for time away or a store claim about earning offline. |
| **Build or upgrade timers** `meta_build_timers` | Building or upgrading takes real time to finish, and can be sped up. | Needs a visible countdown on a build or upgrade, or a documented build queue. |
| **Shared world map** `meta_world_map` | A map shared with other players' bases or cities, used to gather, rally or attack. |  |
| **Raiding other players** `meta_base_raids` | Players attack or steal from other players' bases, often while those players are offline. |  |
| **Roll or spin progression loop** `meta_roll_loop` | Players spend a limited, refilling resource (dice rolls, spins) whose random result moves them or pays out. |  |
| **Level path map** `meta_level_map` | Levels are laid out along a map or path that the player advances through in order. |  |
| **Pre-level boosters** `meta_pre_level_boosters` | Consumable power-ups chosen before starting a level. |  |

## Live operations & offers (21)

Time-limited content, schedules, currencies and offers that keep players returning and paying.

| Tag | Definition | Must be visible or documented |
|---|---|---|
| **Login calendar** `liveops_login_calendar` | A calendar or streak of rewards for logging in on consecutive or set days. |  |
| **Daily or weekly missions** `liveops_daily_missions` | Tasks that reset daily or weekly and give rewards for completion. |  |
| **Limited-time event modes** `liveops_event_modes` | Time-limited events with their own levels, mode or rules, not only extra rewards. |  |
| **Event leaderboards or tournaments** `liveops_event_leaderboards` | Time-limited competitions where players are ranked and paid out by position. |  |
| **Team or guild events** `liveops_team_events` | Events where players work toward shared goals as a team or guild. |  |
| **Seasons** `liveops_seasons` | Themed, time-boxed seasons that change content or reset progress on a schedule. |  |
| **Event pass** `liveops_event_pass` | A short reward track tied to a single event, separate from any season-long pass. |  |
| **Brand or IP collaborations** `liveops_collaborations` | Crossover events featuring characters or brands from outside the game. |  |
| **Lucky wheel or spin** `liveops_spin_wheel` | A wheel or spinner that awards a random prize, often free once a day or for currency. |  |
| **Premium currency** `liveops_premium_currency` | A scarce currency, mainly bought with money, separate from the everyday soft currency. | Needs two distinct currencies with one clearly sold for money, shown or documented. |
| **Piggy bank** `liveops_piggy_bank` | Currency builds up in a bank from play and can only be collected by paying to open it. |  |
| **Starter pack** `liveops_starter_pack` | A discounted bundle aimed at new players. |  |
| **First-purchase bonus** `liveops_first_purchase_bonus` | An extra reward for a player's first purchase of any kind. |  |
| **Time-limited offers** `liveops_timed_offers` | Purchase offers shown with a countdown or expiry. |  |
| **Tiered or chained offers** `liveops_offer_chains` | Offers in a sequence or ladder, where buying one unlocks the next or better tiers. |  |
| **Pop-up offers** `liveops_popup_offers` | Purchase offers pushed as pop-ups, for example at session start or after failing. |  |
| **Pay to continue** `liveops_pay_to_continue` | After failing, the player can pay (currency, money or an ad) for extra moves, time or a revive. |  |
| **Membership or monthly card** `liveops_membership` | A recurring purchase that grants daily rewards or perks for its duration. | Distinct from a subscription needed to play at all. |
| **VIP levels** `liveops_vip_levels` | Tiers of perks unlocked by total spending. |  |
| **Gifting to friends** `liveops_friend_gifting` | Players send lives, currency or items to friends. |  |
| **Invite rewards** `liveops_referral_rewards` | Rewards for inviting friends to install or play the game. |  |

## Advertising (5)

How the game shows advertisements, and what players can do about them.

| Tag | Definition | Must be visible or documented |
|---|---|---|
| **Rewarded video ads** `ads_rewarded_video` | Players can choose to watch a video ad in exchange for a reward. | Needs an offer to watch an ad for a reward. A store "Contains ads" notice alone is not enough. |
| **Interstitial ads** `ads_interstitials` | Full-screen ads shown between levels or screens without the player choosing to watch. |  |
| **Banner ads** `ads_banners` | Ads that stay on screen in a strip during play or menus. |  |
| **Ad-removal purchase** `ads_removal_purchase` | A purchase that removes some or all ads. |  |
| **Offerwall** `ads_offerwall` | Rewards for completing third-party offers, such as installing other apps. |  |

## Implementation details (12)

How a feature is done. Asked only when its parent feature is present.

| Tag | Asked only if | Definition | Must be visible or documented |
|---|---|---|---|
| **Pass has a free track** `depth_pass_free_track` | Battle pass | The battle pass has a free reward track alongside the paid one. |  |
| **Pass has an upper paid tier** `depth_pass_upper_tier` | Battle pass | A second, more expensive paid tier or level skips are sold on top of the standard pass. |  |
| **Gacha shows drop rates** `depth_gacha_rates_shown` | Gacha or loot boxes | The game displays the odds of each reward from its random draws. |  |
| **Gacha pity guarantee** `depth_gacha_pity` | Gacha or loot boxes | A guaranteed top reward after a set number of draws without one. |  |
| **Gacha duplicates convert** `depth_gacha_duplicates_convert` | Gacha or loot boxes | Duplicate draws turn into shards, upgrades or another currency. |  |
| **Energy works as lives** `depth_energy_as_lives` | Energy or stamina timers | The play-limiting resource is a set of lives lost on failure. |  |
| **Energy can be bought** `depth_energy_refill_purchase` | Energy or stamina timers | Energy or lives can be refilled with premium currency or money. |  |
| **Rewarded ads give progress** `depth_rewarded_ads_progress` | Rewarded video ads | Rewarded ads grant progress resources such as energy, continues or speed-ups, not only soft currency. |  |
| **Paid speed-ups** `depth_paid_speedups` | Build or upgrade timers | Waiting times can be skipped with premium currency or money. |  |
| **Guild chat** `depth_guild_chat` | Guilds or clans | Guild members can message each other in the game. |  |
| **Guild help requests** `depth_guild_help` | Guilds or clans | Guild members can speed up each other's timers or send requested items. |  |
| **Weekly or faster event cadence** `depth_live_events_weekly` | Live events | New live events start at least once a week. | Needs dated evidence across time, such as update notes or an event calendar. One session cannot show cadence. |

## After approval

1. Promote the approved tags into `taxonomy/genome_tags_v2.yaml`.
2. Teach the loader the `requires` field.
3. Ask follow-up questions only after their parent is decided.
4. Show the new categories on the site's tag dictionary.
5. Run them on the 5 pilot recordings. v2 is done when at least half the new tags are decided
   on the pilot games and the blind review agrees with at least 90% of the "present" calls.
