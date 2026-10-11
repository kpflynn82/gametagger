# Android kit pilot with REA (October 10, 2026)

The owner asked whether [REA](https://github.com/morluto/rea) can help analyze Android games. The
pilot reads which software kits (ad networks, attribution, analytics, support, payments, consent)
and engine five top games ship with, and compares that with GameTagger's store-page tags, where the
specific ad tags are "not enough evidence" for about 97% of the 222 mobile games.

## How it was done

1. Official Play Store installs on the Android 15 emulator, signed in to the owner's test account
   (owner-approved; the owner completed Google Play's "Complete account setup" step once).
   `mac/install-games.command` taps only "Install" on each game's own store page.
2. `mac/copy-game-files.command` copies each installed APK set off the emulator. Plain `adb pull`
   dropped the emulator connection on large files, so it streams 8 MB pieces with `adb exec-out dd`
   and checks every file's SHA-256 against the device's. 13 files were copied that way, all
   matching; 3 small Coin Master files had already come through `adb pull` with matching sizes.
3. In the cloud workspace: REA 6.3.0 (npm `rea-agents`) with its pinned JADX engine
   (jadx-headless-mcp 0.7.1, SHA-256 checked) and JDK 21, heap 4 GB. Per game,
   `rea inspect-android-package base.apk` (manifest, permissions) and
   `rea search-android-classes base.apk ""` (every class name), 30–55 s each.
4. `sdk_scan.py` maps class-name prefixes and native library names to kits and engines.

APKs are third-party content: they stay in `benchmark-runs/apk-pilot/` and on the owner's Mac,
never in git. `results/` holds only derived facts (kit names, counts, library names).

## Results

| Game | Engine | Ad kits in the APK | Store says "Contains ads" | GameTagger `monetization_ads` before |
|---|---|---|---|---|
| MONOPOLY GO! 1.78.2 | Unity (IL2CPP) | 1: Unity Ads, with its full-screen ad screen declared | No | not enough evidence |
| Royal Match 38911 | Unity (IL2CPP) | 7: AppLovin MAX with Mintegral, Moloco and Unity Ads adapters, plus AdMob | No | absent |
| Candy Crush Saga 1.338.0.2 | King's own engine (`libcandycrushsaga.so`) | 10: ironSource LevelPlay and AppLovin MAX, Vungle, Meta, Moloco, Unity Ads, AdMob | Yes | likely |
| Coin Master 3.5.2740 | Unity (IL2CPP) | 7: AppLovin MAX with Facebook, Google, Google Ad Manager and Unity Ads adapters, plus ironSource | Yes | strong |
| Royal Smash! 1.16.494 | Unity (IL2CPP) | 14: AppLovin MAX with 12 adapters (Pangle, Mintegral, Moloco, InMobi, DT Exchange, Vungle, …) | Yes | strong |

Other stack facts, all five read cleanly: attribution (Adjust in Monopoly GO, AppsFlyer in Royal
Match, Coin Master and Royal Smash, none found in Candy Crush), Firebase Analytics everywhere,
Helpshift support in three, Braze CRM in Candy Crush, consent tools (Google UMP, OneTrust,
Usercentrics), Google Play Billing everywhere, Facebook login in all five.

## What it shows

* **The tech stack is reliable and new to GameTagger.** Engine, mediation layer, ad networks,
  attribution, CRM, support and consent come straight from the shipped code. That supports a
  "tech stack of the top grossers" view and is fresher than Exodus Privacy (the Monopoly GO report found
  there is from July 2024 and has no Unity Ads or Datadog).
* **Kits in the code are not proof that players see ads.** Monopoly GO and Royal Match declare no
  ads on Google Play, yet ship ad SDKs; Royal Match has a full AppLovin MAX stack with 32 ad
  components in its manifest. The code may serve tests, other markets or future plans. So kit
  evidence fits a separate capability tag ("ad SDK integrated") rather than "shows ads", and the
  store's own "Contains ads" declaration stays the better signal for "shows ads". Ad formats
  (rewarded, interstitial, banner) are not settled by kits either. (For Monopoly GO, the
  follow-up below found Unity Ads switched on by the server and an optional reward-ad offer.)
* **REA works, with one rough edge.** It read all five games without installing anything on the
  Mac. For 4 of 5 games it refused the class list because an obfuscated build repeats 1–6 class
  names out of 22,000–41,000; REA keeps the engine's raw pages in its error, and `sdk_scan.py`
  recovers the full list from them (de-duplicated, noted in each result).
* **Getting the APKs is the real cost:** about 3–5 minutes of download per game, Google Play's
  one-time account setup, an unstable `adb pull` (fixed by streaming in checked pieces), about
  1.1 GB of APKs for five games, and no route for games that refuse emulators.

## Follow-up: what Candy Crush introduces when

The owner asked whether the code shows mechanics and progression, not just ads (and noted that
legal advice he obtained says a game's economy and progression are not protected by copyright).
For the Unity games, the game logic is compiled to native code REA does not translate, and tuning
mostly comes from servers. Candy Crush is the exception: its base APK ships all 23,645 levels as
JSON in a SQLite file, plus a binary index with each level's hard-level label.
`candy_crush_levels.py` turns them into derived facts only (`results/candy-crush-levels.json`):
the first level each game mode, level tag, mechanic setting, board-element code and order item
appears, and per level band the median move limit, mean colour count, share of levels labelled
hard and number of new board elements. Board-element and order-item codes are King's numbers; the
APK does not name them.

## Follow-up: Monopoly GO's systems and how it gates them

Monopoly GO keeps its rules on its servers, so its APK cannot give a level-by-level table like
Candy Crush's. Three readable sources together give the list of systems, the gating rules and some
live thresholds. None of them involved playing the game or changing anything on the emulator.

**1. Code names (`unity_systems.py`, `results/com.scopely.monopolygo-systems.json`).** Unity games
built with IL2CPP keep every class, method and field name in `global-metadata.dat`, which is
unencrypted in Monopoly GO 1.78.2 (metadata version 39). The game's own code sits under `Tophat.*`
in 316 named systems. The game-facing ones, grouped by hand:

| Group | Systems (namespace names) |
|---|---|
| Roll and move | Roll, Rolling, DiceRoll, RollEV, RollRecharge, RechargeV2, LockedRollMultiplier, Board, TileMechanics, Chance, ChanceDeck, CommunityChestV2, Jail, InstantJail, RentDue, Pickups |
| Build and progress | Building, BuildMenu, Landmarks, LandmarksV2, HousePlacement, NetWorth, Prestige, PlayerXp, Chapters, SeasonalBoards, Seasons, EndOfContent |
| Attack and defend | BankHeist, Shield, Shields, ForceField, HostileTakeover, Revenge, PVP, BoardRaid |
| Collections | Sticker, StickerPack, StickerShop, StickerBoom, WildStickers, Collections, AlbumTrading, AlbumPityCounter, CompleteSet, SetSwap, TimeLimitedSets, Vanity, VanityCollection, DiceSkins, Token, TokenChase, Emoji |
| Events and minigames | Tournaments, Leagues, SpecialEvents, BoardRush, GoldenBlitz, CoopEvents, AdventureEvent, PinataParty, TradeFest, GoFriendsEvent, BuildersBash, Quests, QuestsV2, Minigames, MinigameDig, Plinko, ForeverGames, HarvestTile, TileRun, LuckyRolls, CashBoost, CashGrab, JackpotStash, JackpotSurprise, RewardWheels |
| Daily habit and comeback | DailyCalendar, DailyTasks, FreeGift, QuickWinsAutoClaim, QuickWinsReactivation, RichReturns, NotificationReminder, Inbox, Newsfeed |
| Social | Friends, FriendGift, SocialGift, Teams, GoChat, QuickMessages, SocialInvites, AddressBook, Facebook, FriendCode, SocialHub |
| Offers and store | Store, Shop, Purchasing, Offers, OffersV2, ProgressiveOffer, EndlessOffer(s), DecoyOffers, OutOfRolls, OutOfRollsOffer, PiggyBank, PiggyBankOffer, PersonalisedOfferImpressions, EscrowPack, StoreCommodityMultiplier, WebPortal |
| Tuning and targeting | Rubberbanding, ArcheSegments, FeatureEligibility, Prerequisites, DynamicCommodities, Weights, AutoConfig |

The names also show **how a feature is gated**: 34 kinds of prerequisite, including And and Or to
combine them. The progression ones are number of boards completed, board completed or not, being
on a given board, net worth amount, player level, first-time tutorial finished, quest completed,
owning an item, and "never connected to Facebook". Live-ops ones are an event, season, offer group
or comeback ("rich returns") period being active, plus a random interval. Settings named
`RequiredFriendCountToUnlock`, 
`BoardUnlocks`, `CategoryFeatureUnlockMap`, `LeaguesUnlockedInNetWorth`, `FirstImpressionMinBoard`,
`RewardChannelsByBoardLevel` and `StartupDynamicCommoditiesByBoardLevelConfig`, and a method
`GetEconomyKeyAtBoardIndex`, say the economy and rewards are switched per board. 77 features have
their own tutorial, a fair proxy for "mechanics the game introduces". Names show what exists, not
how it behaves: what Rubberbanding or RollEV do is in compiled code this pilot does not read. The
same name reader opens the other three Unity games in the pilot (metadata v31, unencrypted).

**2. Saved data (`mac/copy-saved-data.command`, `saved_rules.py`,
`results/monopoly-go-saved-rules.json`).** After the 11.8-hour teardown run, the game's
shared-storage folder on the Android 17 emulator held 1,802 files (856 MB, almost all downloaded
art). The launcher lists them all and copies the 29 small non-art files, each SHA-256 checked;
Android does not let an unrooted device read the game's private folder, where its server settings
would be. The useful parts:

* **Live targeting rules** for 17 pop-ups. This week's Halloween album gifts and time-limited
  sticker sets require `net_worth >= 15`; push-notification reminders wait for
  `num_boards_completed > 2`; a Facebook fan-page link needs 2 boards, a Facebook trading-group
  pop-up 5 boards (after closing the album, at most 3 a week); a friend-invite pop-up follows
  declining the out-of-rolls offer. A community guide also gives net worth 15 for the sticker
  album, 8 for auto-roll and 25 for daily treats
  ([Shattered Vault](https://shatteredvault.com/monopoly-go/get-started/)).
* **Remote settings**: Unity Ads is switched on (`unityads_enabled`, updated October 8). The
  teardown player also logged one optional "Multiply & Collect" reward-ad offer (and three
  undescribed ad offers) in 11.8 hours, and no forced ads. That is more than "kit in the code":
  Monopoly GO offers at least an optional rewarded ad, although Google Play lists no ads.
* **Downloaded content**: 770 bundles, including 45 feature bundles (tournaments, leagues, jail,
  co-op events, Golden Blitz, minigames and more) and 5 board themes.

**3. The teardown run, checked screenshot by screenshot** (run 20261006-062259 on the owner's
Mac, 11.8 hours of automated free play; `results/monopoly-go-unlock-ladder.json`). Monopoly GO
shows its own unlock list: the **Net Worth Gallery** (the avatar at the top left) is a ladder of
cards, each with the net worth it needs. Net worth rises as landmarks are built. The run's
screenshots show the ladder up to 120:

| Net worth | Unlocks |
|---|---|
| 4 | Rent Targets (collect rent from more players on your board) |
| 8 | Auto Roll |
| 15 | Albums (sticker collections) |
| 25 | Daily Treats |
| 35 | Quick Wins (daily tasks; card gives 20 dice) |
| 45 | Roll Capacity (most rolls you can bank goes from 30 to 40; card gives 80 dice) |
| 60 | GO! Tile |
| 75 | Rent Targets, second step |
| 90 | Emojis |
| 100 | Community Chest |
| 120 | Roll Regeneration |
| above 120 | a Bank Heist card (its number was off screen) |

When they came for this player (play minutes, board): net worth 4 and 8 at 37 and 44 minutes on
New York (15 builds); London (30 builds) from about 150 minutes, with net worth 15 at 153 and the
Monster Mash album event starting at once; a Board Rush event (finish all landmarks in 21 hours
for 30 dice and 60K) at 317; net worth 25 at 383; a bank heist minigame at 401 (heists come
from railroad tiles, before the gallery's Bank Heist card); net worth 35 at 408; Venice from 419,
with net worth 45 at 420, an attack on another player's board at 428 and net worth 60 at 445; net
worth 62 at 584, next up Rent Targets at 75. The build menu sold Paris cards by the end (board 4).
Events and album seasons (Board Rush, Monster Mash, Spooky Express) are live-ops on their own
schedules, not ladder steps. The community guide's 8, 15 and 25 match the ladder. The times are
one automated player's pace, slower than a person's.

The run's own blueprint got the levels wrong after 37 minutes: it read the dice counter under GO
("78/30": 78 dice, 30 at most refilled) as the level, and its level curve stopped at 4. The
teardown player now names the level it reads ("Net Worth"), never reads a fraction as the level,
reads screens like the gallery into a ladder, reports locked features with their stated
requirement, and lists each unlock with the level and board at that moment (teardown player
commit 5d85cb7). Its launcher "Start Monopoly GO unlock run" starts a fresh guest on the Android
15 emulator, leaving the October 6 game on the Android 17 emulator untouched.
