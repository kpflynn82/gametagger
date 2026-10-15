"""Signal scoring: the monetization fingerprint, soft-launch, novelty and trend fit."""

from __future__ import annotations

from gametagger.radar.candidate import Candidate, ChartEntry, RegionChart, merge_candidates
from gametagger.radar.signals import SignalWeights, score_candidate


def _cand(entries, *, known=None, title="Test Game", dev="Studio", hints=()):
    c = Candidate(store="google_play", store_id="com.x.y", title=title, developer=dev, hints=hints)
    c.entries = entries
    c.known_genome = known
    return c


def test_high_grossing_absent_from_downloads_is_strong_monetization():
    # #12 grossing in Canada, not in the top-100 downloads anywhere: the fingerprint.
    c = _cand([ChartEntry("CA", "google_play", "grossing", 12, 100)])
    sig = score_candidate(c, us_game_ids=frozenset())
    assert sig.monetization.value >= 0.7
    assert "not in" in sig.monetization.reason


def test_grossing_tracks_downloads_is_weak_monetization():
    c = _cand(
        [
            ChartEntry("CA", "google_play", "grossing", 10, 100),
            ChartEntry("CA", "google_play", "free", 8, 100),
        ]
    )
    sig = score_candidate(c, us_game_ids=frozenset())
    assert sig.monetization.value < 0.3


def test_out_earns_install_rank_scores_mid_high():
    # #15 grossing but only #70 downloads: out-earns its installs by 55 places.
    c = _cand(
        [
            ChartEntry("AU", "google_play", "grossing", 15, 100),
            ChartEntry("AU", "google_play", "free", 70, 100),
        ]
    )
    sig = score_candidate(c, us_game_ids=frozenset())
    assert 0.5 <= sig.monetization.value <= 1.0
    assert "out-earns" in sig.monetization.reason


def test_soft_launch_rewards_multi_market_and_us_absence():
    multi = _cand(
        [
            ChartEntry("CA", "google_play", "grossing", 20, 100),
            ChartEntry("AU", "google_play", "grossing", 25, 100),
            ChartEntry("NZ", "app_store", "grossing", 18, 100),
        ]
    )
    one = _cand([ChartEntry("CA", "google_play", "grossing", 20, 100)])
    s_multi = score_candidate(multi, us_game_ids=frozenset())
    s_one = score_candidate(one, us_game_ids=frozenset())
    assert s_multi.soft_launch.value > s_one.soft_launch.value


def test_known_us_game_is_not_a_soft_launch_and_not_novel():
    c = _cand(
        [ChartEntry("CA", "google_play", "grossing", 5, 100)],
        known={"primary_genre": "puzzle", "genre_family_probabilities": {"puzzle": 1.0}},
    )
    # game_id is gp-com.x.y; mark it as a known US grosser.
    sig = score_candidate(c, us_game_ids=frozenset({c.game_id}))
    assert sig.soft_launch.value < 0.4
    assert sig.novelty.value <= 0.1


def test_trend_fit_matches_hot_terms():
    c = _cand([ChartEntry("CA", "google_play", "grossing", 30, 100)], hints=("merge", "dragons"))
    sig = score_candidate(c, us_game_ids=frozenset(), hot_terms={"merge": 0.9})
    assert sig.trend_fit.value > 0.5
    assert "merge" in sig.trend_fit.reason


def test_trend_fit_ignores_punctuation_and_plurals():
    # A hyphenated standout in the hints must still match a spaced, singular digest term.
    c = _cand(
        [ChartEntry("CA", "google_play", "grossing", 20, 100)],
        hints=("a live social-tournament ladder (guild vs guild)",),
    )
    sig = score_candidate(c, us_game_ids=frozenset(), hot_terms={"social tournament": 0.8})
    assert sig.trend_fit.value > 0.0
    assert "social tournament" in sig.trend_fit.reason


def test_priority_is_0_100_and_weights_normalize():
    c = _cand([ChartEntry("CA", "google_play", "grossing", 3, 100)])
    sig = score_candidate(c, us_game_ids=frozenset(), weights=SignalWeights(1, 1, 1, 1))
    assert 0 <= sig.priority <= 100


def test_merge_folds_regions_into_one_candidate():
    charts = [
        RegionChart(
            "CA", "google_play", "grossing", "2026-10-14", {"com.a.b": (10, "Alpha", "DevCo")}
        ),
        RegionChart(
            "AU", "google_play", "grossing", "2026-10-14", {"com.a.b": (14, "Alpha", None)}
        ),
        RegionChart("CA", "google_play", "free", "2026-10-14", {"com.a.b": (88, "Alpha", None)}),
    ]
    cands = merge_candidates(charts)
    assert len(cands) == 1
    c = cands[0]
    assert c.developer == "DevCo"
    assert {e.region for e in c.entries if e.kind == "grossing"} == {"CA", "AU"}
    assert c.best_rank("grossing").rank == 10
