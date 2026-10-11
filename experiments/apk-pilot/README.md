# Android kit pilot with REA (in progress, October 10, 2026)

The owner asked whether [REA](https://github.com/morluto/rea) can help analyze Android games. The
pilot reads which software kits (ad networks, attribution, analytics, support, payments, consent)
and engine five games ship with, and compares that with GameTagger's store-page tags, where the
specific ad tags are "not enough evidence" for about 97% of the 222 mobile games.

* Games: MONOPOLY GO!, Royal Match, Candy Crush Saga, Coin Master, Royal Smash!. Installed from the
  Play Store on the Android 15 emulator (official installs, owner-approved), and their installed
  APK sets copied off with `adb`. APKs are third-party content: they stay in `benchmark-runs/` and
  on the owner's Mac, never in git.
* REA 6.3.0 (npm `rea-agents`) with its pinned JADX engine (jadx-headless-mcp 0.7.1, SHA-256
  checked) runs in the cloud workspace with JDK 21: `rea inspect-android-package` and
  `rea search-android-classes <base.apk> ""` (every class name).
* `sdk_scan.py` maps class-name prefixes and native library names to kits and engines, and writes
  `kits.json` per game. A kit's code shows a game can use it, not that it does; one ad SDK serves
  every ad format.

Status: REA verified on its public sample APK. MONOPOLY GO! is installed; Google Play paused the
other installs until the owner completes the emulator account's setup.
