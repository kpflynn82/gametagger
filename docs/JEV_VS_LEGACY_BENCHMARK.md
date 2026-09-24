# Jev versus the previous method: 100-game benchmark

This benchmark compares rich mode (a Claude vision Observer plus Jev) with the original site's
single Claude request. It runs on today's top games, and every method receives identical
evidence. The tool is `gametagger-compare`. Every step except `run --live` is free: those steps
read public pages and make no model calls.

## Owner decisions (September 24, 2026)

| Decision | Choice |
|---|---|
| Spending limit | **$40 in total** across Claude and Jev. The tool enforces it for every request, and a pilot and the full run share the same cap |
| Games | Top 50 on Steam's most-played chart, and the top 50 on AppBrain's [Google Play top-grossing games, US](https://www.appbrain.com/stats/google-play-rankings/top_grossing/game/us) |
| Previous method | Both settings of the original site: **standard** (Claude Haiku 4.5) and **deep** (Claude Opus 4.8) |
| Answer key | **Steam user tags**, plus the **owner's own review** on a blinded sheet |
| Non-games on the Steam chart | Skipped and listed (default applied; the owner did not object) |

## The cohort (frozen)

`experiments/jev-vs-legacy/cohort.json` holds 50 Steam and 50 mobile games. They come from the
Steam chart of 2026-09-23 and the AppBrain chart of 2026-09-24. Four chart entries were skipped,
each with its reason recorded:

* **Wallpaper Engine**: Steam files it under software genres (Animation & Modeling, Utilities…).
* **FiveM**: its Steam store type is "advertising".
* **Grand Theft Auto V Enhanced**: another edition of GTA V Legacy, which was kept at its higher
  rank.
* **eFootball**: it is on both charts, so it was kept once, on the Steam list.

The next chart entries filled the freed places. *Call of Duty®* (Steam #43) is Activision's
launcher for several titles; it is kept because Steam lists it as one game. Treat its results
with care.

Games are identified by exact store ID (Steam app ID or Google Play package). **Identity**
follows those IDs through Wikidata to the English Wikipedia article and the other store listings.
When a mobile game has no Wikidata entry, an App Store search is accepted only if both the title
and the developer match exactly, and those links are flagged for the owner. Ambiguous matches
stay unlinked; nothing is guessed.

## What each method receives

`dossiers` gathers each game's evidence once:

* **Steam games**: the Steam listing text and fields, plus the Wikipedia article.
* **Mobile games**: the Google Play listing (read from its public page: description, category
  chips, in-app purchase and ads notices), the App Store listing when one is linked, and the
  Wikipedia article.
* **Media**: up to 4 screenshots per store, and the store trailer. Google Play serves its trailer
  as a direct MP4. When no store has a trailer, the YouTube Data API supplies YouTube's still
  images.

Each method then reads the same dossier in its own way:

| | Rich mode | Old method (faithful adapter) |
|---|---|---|
| Text | Every source split into numbered claims. The game's title is withheld from Jev | Steam short description, store and Wikipedia text cut at 1,000 characters, **plus the game's name** (so Claude can use what it already knows) |
| Images | Claude describes every screenshot and 6 short trailer bursts, and never names genres or tags | The first 2 screenshots per store at 600 pixels, sent inside the one request |
| Judgement | Jev answers 189 attribute questions with four states, then the v4.1 genre hierarchy | One JSON answer with about 91 yes/no keys and one of 59 genres. An unknown genre is silently replaced (recorded as a forced fallback) |
| Models | `claude-sonnet-5` Observer, `jev-latest` (jev-1.13.0) | `claude-haiku-4-5-20251001` (standard) / `claude-opus-4-8` (deep) |

The adapter copies the original prompt, genre list and post-processing verbatim from
`kpflynn82/gametagger-web@4b710fd`. Each result lists the adaptations: evidence comes from the
dossier, there is no Xbox section, mobile stores are formatted like the old Xbox section, and
trailer frames stay off as in the original's default.

## What is measured

* **Time per stage**: shared evidence gathering; rich mode's observe and decide stages; the old
  method's prepare, call and parse stages. Wall-clock time, with 3 games in parallel and SDK
  retries included.
* **Tokens** as reported by each provider, and **cost** from list prices: Claude Haiku 4.5 $1/$5,
  Opus 4.8 $5/$25, Sonnet 5 $2/$10 per million input/output tokens; Jev $0.042 per million input
  tokens, with output free.
* **Tags per game**: old-method keys are translated into the Genome vocabulary through the draft
  crosswalk.
* **Accuracy against Steam user tags**, for games with a Steam listing:
  * *Recall*: the share of attributes implied by a game's top 20 player-voted tags that a method
    reported present. It is reported twice: for all mapped attributes, and for only the
    attributes both vocabularies can name (the fair head-to-head). Paired 95% bootstrap intervals
    are given for the differences.
  * *Contradiction*: the share a method explicitly called absent.

  A missing Steam tag is never counted as a "no", so precision cannot come from Steam tags.
* **Owner review**: `review-sheet` writes a blinded spreadsheet of 30 sampled games (15 per list).
  It lists every method's primary genre and up to 15 randomly sampled attributes that any method
  proposed. Rows are shuffled and give no hint of which method proposed them. Marking
  `your_verdict` yes, no or unsure gives each method's precision.
* **Primary genre**: coverage, forced fallbacks, and agreement with genres implied by Steam tags
  (a weak signal, reported as such).

Crosswalks are in `taxonomy/crosswalks/`. They are **drafts pending owner approval**: old
59 genres to v4.1 genres, old tag keys to Genome tags, and Steam user tags to Genome tags and
genres. The old "Sports" and "Horror" map only to a family, never to an invented specific genre.

## Running it

A fresh cloud session needs `ffmpeg` (for trailers) and the keys. Name the Anthropic key
`GAMETAGGER_ANTHROPIC_API_KEY`, because some hosted agents reserve `ANTHROPIC_API_KEY` for
themselves.

```bash
sudo apt-get install -y ffmpeg        # or apt-get as root
uv sync --frozen --extra dev

# Free steps (the cohort, identity and Steam tag key are already committed)
uv run gametagger-compare identity            # only if cohort.json changes; resumable
uv run gametagger-compare answer-key          # refresh Steam user tags if needed
uv run gametagger-compare dossiers            # about 100 games of text and media

# Paid, under one $40 cap shared by all runs (ledger: benchmark-runs/jev-vs-legacy/ledger.jsonl)
uv run gametagger-compare run --live --budget-usd 40 --limit 10     # pilot: 5 Steam + 5 mobile
uv run gametagger-compare report                                    # check the pilot numbers
uv run gametagger-compare run --live --budget-usd 40                # the rest; finished games are skipped

# Write-up and the owner's check
uv run gametagger-compare report
uv run gametagger-compare review-sheet     # experiments/jev-vs-legacy/review/owner-review.csv
# (after the owner fills in the sheet)
uv run gametagger-compare report           # adds precision from the review
```

Before each request, the meter reserves the request's worst-case cost (input plus the full
`max_tokens` output). It refuses the request when spend so far plus requests in flight plus this
worst case would pass the cap. The run then stops cleanly and reports why. Estimated spend for
the full run is $17–22: rich-mode vision about $10–15, Opus about $6, Haiku about $1, and Jev
about $0.15.

Outputs:

* `experiments/jev-vs-legacy/results/`: `summary.json` and the compact `per-game.jsonl`. These
  hold no third-party text.
* `experiments/jev-vs-legacy/report/`: `report.html`, `social-card.html` / `.png` and
  `social-post.txt`.
* `benchmark-runs/` (git-ignored): dossiers, media, raw responses and the ledger.

`report` adds an "Illustrative / UI test data" watermark unless the ledger shows successful
provider calls. Fixture numbers therefore cannot be mistaken for measurements.

## Verified so far

* Live and free, in this session: both chart readers, the cohort rules, Wikidata identity, Steam
  user tags for all 50 Steam games, and dossier building on real games (Steam, Google Play with
  its MP4 trailer, and Wikipedia). The TypeSafe key was accepted by the free model-listing
  endpoint, and the YouTube key worked.
* Offline: 23 new tests. They cover the adapter's verbatim rules and parser, the input layout,
  the chart parsers, identity (ambiguity is refused), the answer key, the Google Play reader, the
  crosswalks (every old genre and key is covered), the cost and ledger arithmetic, and a budget
  stop that passes through every provider error handler. A complete fake run exercises metering,
  resume, scoring, the blinded sheet and the watermarked report.
* One live Jev check, on Stardew Valley's text only (no Claude call). All 185 questions went in
  6 requests (so batches of 60 are accepted). It took 4.0 seconds, used 44,566 input tokens and
  cost **$0.0019**, recorded against the $40 limit. The returned model was `jev-1.13.0`. Result:
  primary genre farm simulation (probability 1.0); 44 attributes present, 5 absent, 133 unknown,
  7 not asked (no allowed evidence type in text alone).
* **Not yet run: any Claude call.** The Anthropic key was not visible in this session.
