# Mobile-first site data (October 8, 2026)

The owner wanted the site to be mobile-first for interviews with mobile studios: more mobile
games and a view of what is new.

* `cohort.json`: built by `gametagger-compare --experiment experiments/mobile-top100
  mobile-cohort`. The plan was today's Google Play top 100 grossing plus about 30 rising games.
  On October 8 AppBrain's top-grossing and top-new-free tables were empty (the pages loaded, with
  no games in them, in every country and in a real browser), so the cohort fell back: the
  September 24 top-grossing 50 (segment `grossing`) plus the 83 games on AppBrain's US top-free
  chart that are not among them (segment `rising`, labelled "Top free" on the site).
* `new-run/`: tag states and counts for the 83 games tagged in this run (vocabulary v2, store
  pages only, Observer on the owner's Claude plan, Jev capped at $1.00). The top-grossing 50 use
  their October 5 results in `experiments/mobile-retag-v2/per-game.jsonl`.
* `site_data.py`: rewrites the game data inside `web/index.html` from these files (Steam's 50
  unchanged); then `experiments/jev-vs-legacy/site/refresh_web.py` applies the template.

Run on the owner's Mac with `scripts/mac/mobile-top100.sh` (Finder launcher
`Start mobile top 100.command` in `~/Claude Workspace/gametagger/`). The work directory
`benchmark-runs/mobile-top100/` (store media, descriptions, ledger) stays on the Mac. If
AppBrain's top-grossing chart returns, delete `cohort.json` here and on the Mac and run it again
for a fresh top 100 and Google Play chart movers.
