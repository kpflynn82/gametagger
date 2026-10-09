# Google Play Top grossing, read from the Android emulator

On October 8, 2026 AppBrain's Google Play top-grossing table was empty, so that day's site
update reused the September 24 list. This folder tests another source: the Play Store app
itself, running on the Android Studio emulator.

## How it works

1. Open the Play Store on the emulator: Games > Top charts > Top grossing.
2. Run `scripts/mac/play-chart.sh` on the Mac. It scrolls the list and saves a screenshot and
   Android's screen text (an accessibility dump) for each screenful. It never taps anything.
3. Run `uv run python experiments/play-chart/parse_dump.py benchmark-runs/play-chart/<folder>`
   to turn the screens into `chart.json`: rank, title, Play's own genre labels, star rating and
   badges (Event, Editors' Choice, and so on).

Screenshots and dumps stay in `benchmark-runs/` (third-party content, never committed). Only the
parsed ranks and titles are kept here, like `cohort.json`.

## First reading: October 9, 2026

[2026-10-09-top-grossing.json](2026-10-09-top-grossing.json) holds 165 ranked games with no gaps
in the numbering. It is the US chart (en-US, US SIM, prices in dollars). It agrees closely with
AppBrain's September 24 list: 45 of that top 50 are still in it, 9 of the top 10 are the same
games, and the median game moved 2 places.

**It is not complete.** The Play Store only lists games that can run on the device. This
emulator uses a 16 KB page-size Android 17 image (`sdk_gphone16k_arm64`), and the 5 September
top-50 games missing from today's list (Township, NIKKE, All in Hole, Mystery Town, Magic Sort)
each show "Your device isn't compatible with this version" on this emulator. Gardenscapes, which
is in the list, shows Install. Other hidden games cannot be detected, and every game below a
hidden one is ranked too high.

Package IDs are not on screen. 58 of the top 100 titles match games already in our cohorts; the
other 42 need their store IDs looked up before they can be tagged.

## Next

- Read the chart again on a standard 4 KB-page Google Play system image (for example Android 15
  or 16, "Google Play" arm64). If the five games appear, use that emulator for charts.
- Then match titles to package IDs and build a cohort from it in place of the AppBrain fallback.
- The same screen also has "Top free" in its chart menu and a "New" filter, which could replace
  the top-free stand-in for rising games.
