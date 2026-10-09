# Google Play Top grossing, read from the Android emulator

On October 8, 2026 AppBrain's Google Play top-grossing table was empty, so that day's site
update reused the September 24 list. This folder tests another source: the Play Store app
itself, running on the Android Studio emulator.

## How it works

1. Start an emulator with a Google Play system image and sign in (once, by hand).
2. Run `scripts/mac/play-chart.sh` on the Mac. It opens the Play Store, declines any welcome or
   location prompt, taps Games > Top charts > Top grossing, then scrolls the list and saves a
   screenshot and Android's screen text (an accessibility dump) for each screenful. It never taps
   a game, Install or a purchase.
3. Run `uv run python experiments/play-chart/parse_dump.py benchmark-runs/play-chart/<folder>`
   to turn the screens into `chart.json`: rank, title, Play's own genre labels, star rating and
   badges (Event, Editors' Choice, and so on).

Screenshots and dumps stay in `benchmark-runs/` (third-party content, never committed). Only the
parsed ranks, titles and store IDs are kept here, like `cohort.json`.

## Readings on October 9, 2026

| File | Emulator | Read at (PT) | Ranked games |
|---|---|---|---|
| [2026-10-09-android17.json](2026-10-09-android17.json) | Android 17, 16 KB page size | 12:05 | 165 (stopped at the page limit) |
| [2026-10-09-android15.json](2026-10-09-android15.json) | Android 15, 4 KB page size | 12:35 | 171 (end of the list) |

Both are the US chart (en-US, US SIM, prices in dollars), with no gaps in the numbering. Their
top 100 are the same 100 games, and no game is more than 5 places apart.

**The chart is real.** Appfigures' public Google Play grossing page (updated hourly, top 30
shown) has 28 of its top 30 in the emulator's top 30. The one it has that the emulator hides is
Township (#9). Counting Township, 25 of the 29 shared games are within 1 place.

**But it has gaps.** The Play Store only lists games the device can run, and some games refuse
emulators. On both emulators, the store pages of Township, NIKKE, All in Hole, Mystery Town and
Magic Sort say "Your device isn't compatible with this version"; Gardenscapes says Install. The
Android 15 emulator also hides Genshin Impact and Honkai: Star Rail, which the Android 17 one
lists at #101 and #125. So the page size was not the cause; every emulator hides some games. A
hidden game is simply absent, and each game below it ranks one place too high. Township is the
only hidden game in the top 30; in September, NIKKE and the other three ranked between #33 and #46.

**Store IDs.** Package IDs are not on screen. For the Android 15 top 100, 57 come from our earlier
cohorts and 43 were found by searching Google Play's website for the exact title (42 exact
matches; Bingo Voyage's web title differs slightly).

## Using it

`experiments/mobile-top100/play_cohort.py` builds the site's top-grossing cohort from the Android 15
reading: the emulator's top 100 with Township added at #9 (Appfigures) and the rest of the hidden
games listed as unranked. The site has used it since October 9. Reading the chart again on
another day gives Google Play chart movers from one source.
