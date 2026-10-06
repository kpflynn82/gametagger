# Google Play top 50, retagged with vocabulary v2 (October 5, 2026)

The owner's test of the 51 new mobile tags ([VOCABULARY_V2](../../docs/VOCABULARY_V2.md)):
the 50 Google Play games on the site's list, store pages only (Google Play, plus the App Store
and Wikipedia where linked; 8 images per game at the median, a trailer for 24 games). Same method
as the September benchmark's rich arm: Claude Sonnet 5 describes the images, Jev decides every
tag. This time the descriptions ran on the owner's Claude plan through Claude Code
(`--use-max-plan`), on the owner's Mac (`scripts/mac/retag.sh`).

Files: `summary.json` (counts per tag, the umbrella comparison, costs) and `per-game.jsonl`
(tag states per game, no store text). Rebuild with `summarize.py`.

## Results

* All 50 games tagged: 45 complete, 5 partial (one or more Jev questions errored). 240 tags
  each.
* **The new tags are mostly undecided from store pages, as expected.** Of 2,087 new-tag
  questions asked, 9% were decided: 185 present (88 strong, 97 likely), 4 absent, 2
  conflicting, 1,896 not enough evidence. A median game has 4 new tags present.
* By group:
  * Meta layers: 80 present of 650 answers (12%).
  * Live operations and offers: 101 present of 1,050 (10%).
  * Advertising: almost nothing (1 likely, 4 absent, 2 conflicting of 250). Ads barely show in
    store screenshots and text. The 4 absent are Royal Match, whose sources state it has no
    ads.
  * Follow-ups: 463 of 600 not evaluated because their parent was not found; of the 137 asked,
    3 present (guild chat).
* Most often present: event leaderboards or tournaments (19 games), character roster (15),
  decorating or renovation (14), roll or spin progression (12), lucky wheel (12), level path
  map (10), premium currency (10). 20 of the 51 tags were never present.
* **v1 tags are stable.** On the same 50 games, 98% of v1 tag answers (present or not) match the
  September run (9,232 same, 218 changed), although the store pages are two weeks newer.

## The umbrella tags (owner decision 2)

Do mobile games still need the broad v1 tags next to the specific v2 ones?

| Broad v1 tag | Broad present | Any specific present | Broad without any specific |
|---|---|---|---|
| Daily rewards or quests | 16 | 11 (login calendar, daily missions) | 5 |
| Auto-play or idle progress | 5 | 2 (offline earnings) | 3 |
| Ad-supported | 20 | 1 (the five ad tags) | 19 |

The specific tags never fired without the broad one, but the broad ones often fired alone. From
store pages, the broad tags carry information the specific ones do not: "Ad-supported" mostly
from Google Play's "Contains ads" notice, which says nothing about the ad format. So for now
they should stay. Recordings or play-tests should decide the question; this run cannot.

## Cost

* Jev: **$0.19** for 480 requests, inside the owner's $1.00 cap (about 0.4¢ per game).
* Claude: $0 in API money. 523 calls on the plan, which would have cost $8.16 on the API
  (16¢ per game). The plan's 5-hour window ended at 75% and the week at 23%.
* About 100 seconds per game, three games at a time; about 45 minutes in all.

A first attempt the same afternoon stopped at the start because the plan's 5-hour window was
full; nothing was spent.
