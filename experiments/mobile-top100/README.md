# Mobile-first site data (October 8–9, 2026)

The owner wanted the site to be mobile-first for interviews with mobile studios: more mobile
games and a view of what is new.

* `cohort.json` (October 9): Google Play's US top 100 grossing games plus 71 top-free games.
  * Top grossing (segment `grossing`): read in the Play Store app on an Android emulator
    (`experiments/play-chart/2026-10-09-android15.json`), built by `play_cohort.py`. The emulator
    hides games that refuse emulators. Township is added at #9, its rank on Appfigures' hourly
    chart; NIKKE, All in Hole, Mystery Town, Magic Sort, Genshin Impact and Honkai: Star Rail are
    listed as hidden and unranked. Each game keeps its September 24 rank (from AppBrain) for chart
    movers.
  * Top free (segment `rising`, labelled "Top free" on the site): the October 8 top-free games
    from AppBrain that are not in the top 100 grossing.
* `cohort-2026-10-08.json`: the October 8 cohort. AppBrain's top-grossing and top-new-free tables
  were empty that day, so it used the September 24 top-grossing 50 plus 83 top-free games.
* `new-run/`: tag states and counts for the games tagged on the owner's Mac (vocabulary v2,
  store pages only, Observer on the owner's Claude plan, Jev capped at $1.00 in total): 83 games
  on October 8 (listed in `new-run/tagged-2026-10-08.txt`) and 42 on October 9. The games tagged
  on October 5 use `experiments/mobile-retag-v2/per-game.jsonl`.
* `site_data.py`: rewrites the game data inside `web/index.html` from these files (Steam's 50
  unchanged); then `experiments/jev-vs-legacy/site/refresh_web.py` applies the template.

Run on the owner's Mac with `scripts/mac/mobile-top100.sh` (Finder launcher
`Start mobile top 100.command` in `~/Claude Workspace/gametagger/`). It tags only games not
tagged before. The work directory `benchmark-runs/mobile-top100/` (store media, descriptions,
ledger) stays on the Mac. For a fresh chart: read it with `scripts/mac/play-chart.sh`, save it
under `experiments/play-chart/`, point `play_cohort.py` at it, and run the launcher again.
