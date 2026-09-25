# Cheaper image descriptions: 20-game test (September 25, 2026)

The Jev pipeline's cost is almost all Claude describing screenshots and trailer clips (98% in the
100-game benchmark). This test re-described the first 20 benchmark games (10 Steam, 10 Google Play,
interleaved by chart rank) two cheaper ways, through the Message Batches API at half price, and
compared each with the benchmark's own rich-mode results for the same games. Jev, the evidence
policy and the dossiers were unchanged. Scores come from `compare.py`; figures are in
`summary.json`.

| Same 20 games | Benchmark (Sonnet 5, live) | Haiku 4.5, batch | Sonnet 5 brief + duplicates skipped, batch |
|---|---|---|---|
| Cost per game, all in | $0.170 | **$0.035** | $0.070 |
| Image descriptions per game | $0.167 | $0.033 ($0.065 at list price) | $0.067 ($0.134 at list price) |
| Steam player tags found (10 Steam games) | 78.5% | 76.4% | 77.8% |
| Player-tagged attributes called absent | 0% | 0% | 0% |
| Attributes present per game | 36.1 | 35.6 | 34.6 |
| Benchmark's present attributes kept | – | 93% | 92% |
| Benchmark's absent attributes kept | – | 85% | 84% |
| Present/absent flips per game | – | 0.35 | 0.20 |
| Same primary genre as benchmark | – | 95% | 85% |
| Observer statements quarantined per game | 1.2 | 13.8 | 4.7 |

Batch describing of 441 requests (both variants) cost $1.99 and took about 95 minutes to complete.

## Reading it

* **Haiku through the batch is the clear cost winner: about a fifth of the cost** with results
  close to the benchmark (recall within about 2 points, 95% genre agreement). With only 10 Steam
  games the recall difference is not measurable at this sample size, so treat it as "no large
  loss seen", not "no loss".
* Haiku breaks the Observer's rules more often (about 14 statements per game set aside, versus
  about 1 for Sonnet). Those statements never reach Jev, so this costs evidence, not correctness;
  it is the first thing to watch at scale.
* Shorter Sonnet descriptions cut list-price image cost by only about 20%, and skipping duplicate
  screenshots saved almost nothing (store listings rarely repeat an image exactly). The batch
  discount did most of that variant's saving.
* The batch is not instant (95 minutes here, up to 24 hours by contract), which suits library
  backfill and the request queue but not interactive tagging.

## Recommendation

Use **Haiku 4.5 through the batch** for bulk and library tagging, keep Sonnet 5 for showcase or
disputed games, and confirm on a larger sample (and the owner's blinded review) before making Haiku
the default everywhere.

Reproduce: `gametagger-compare run --live --budget-usd <cap> --batch --limit 20 --arms
rich-haiku,rich-lean`, then `uv run python experiments/jev-vs-legacy/cost-test/compare.py`.
