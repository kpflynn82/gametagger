"""Soft-launch radar: spot test-market games that are monetizing well, before they reach the US.

The radar reads top-grossing and top-free charts in the common mobile test markets (Canada,
Australia, New Zealand), then scores each game on four transparent signals:

* **monetization** -- a high grossing rank paired with a weak or absent top-free (download) rank.
  Earning a lot of money on relatively few downloads is the fingerprint of a strong monetization
  system, which is exactly what is worth tearing down.
* **soft_launch** -- the game shows up in the test markets but not (or barely) in the US, and it
  is new to the chart. That pattern says a studio is testing before a wider launch.
* **novelty** -- the game is not already in GameTagger's tagged catalogue of established US top
  grossers, so it is something we have not already studied.
* **trend_fit** -- its apparent genre or mechanics line up with what the weekly mobile digest
  says is currently hot.

Nothing here makes a paid model call or downloads a game. The radar only reads public chart
positions and hands a ranked shortlist to the morning brief. Acquiring and tearing a game down
is a separate, owner-approved step. See ``docs/RADAR_V3_PLAN.md``.
"""

from gametagger.radar.candidate import Candidate, RegionChart, merge_candidates
from gametagger.radar.signals import Signals, SignalWeights, score_candidate

__all__ = [
    "Candidate",
    "RegionChart",
    "merge_candidates",
    "Signals",
    "SignalWeights",
    "score_candidate",
]
