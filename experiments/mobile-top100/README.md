# Mobile top 100 and rising games (October 8, 2026)

The owner wanted the site to be mobile-first for interviews with mobile studios: more mobile
games, today's chart, and a view of what is rising.

* `cohort.json`: today's Google Play top-grossing games (US, from AppBrain; segment `grossing`)
  and about 30 rising games (AppBrain's top-new-free chart, games already in the top grossing
  left out; segment `rising`). Each grossing game carries its September 24 rank, if any, for
  chart movers. Built by `gametagger-compare --experiment experiments/mobile-top100
  mobile-cohort`.
* `new-run/`: tag states and counts for the games tagged in this run (vocabulary v2, store pages
  only, Observer on the owner's Claude plan, Jev capped at $1.00). Games tagged on October 5 are
  not tagged again; their results are in `experiments/mobile-retag-v2/per-game.jsonl`.

Run on the owner's Mac with `scripts/mac/mobile-top100.sh` (Finder launcher
`Start mobile top 100.command` in `~/Claude Workspace/gametagger/`). The work directory
`benchmark-runs/mobile-top100/` (store media, descriptions, ledger) stays on the Mac.
