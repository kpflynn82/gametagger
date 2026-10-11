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
  (rewarded, interstitial, banner) are not settled by kits either.
* **REA works, with one rough edge.** It read all five games without installing anything on the
  Mac. For 4 of 5 games it refused the class list because an obfuscated build repeats 1–6 class
  names out of 22,000–41,000; REA keeps the engine's raw pages in its error, and `sdk_scan.py`
  recovers the full list from them (de-duplicated, noted in each result).
* **Getting the APKs is the real cost:** about 3–5 minutes of download per game, Google Play's
  one-time account setup, an unstable `adb pull` (fixed by streaming in checked pieces), about
  1.1 GB of APKs for five games, and no route for games that refuse emulators.
