"""The morning brief: build proposal (the Heroes-of-the-Wall card), push line, shortlist."""

from __future__ import annotations

from gametagger.radar.brief import (
    BriefedCandidate,
    build_proposal,
    propose_differentiation,
    render_push,
    render_shortlist_md,
)
from gametagger.radar.candidate import Candidate, ChartEntry
from gametagger.radar.signals import score_candidate


def _rpg_candidate():
    c = Candidate(
        store="google_play",
        store_id="com.studio.heroesofthewall",
        title="Heroes of the Wall",
        developer="Wallworks",
        hints=("action rpg", "military"),
        known_genome={
            "primary_genre": "action_rpg",
            "genre_family_probabilities": {"role_playing": 0.8, "action": 0.2},
        },
    )
    c.entries = [
        ChartEntry("CA", "google_play", "grossing", 22, 100),
        ChartEntry("AU", "google_play", "grossing", 19, 100),
    ]
    return c


def test_differentiation_freshens_theme_and_adds_a_mechanic():
    c = _rpg_candidate()
    diff = propose_differentiation(
        c, standout_mechanic="social tournaments", hot_terms={"gacha": 0.9}
    )
    assert diff.theme_to == "dragons"  # fresh for role_playing per the playbook
    assert diff.add_mechanic != "social tournaments"  # don't re-add the standout
    assert "crowded" in diff.rationale


def test_build_proposal_is_the_north_star_card():
    c = _rpg_candidate()
    sig = score_candidate(c, us_game_ids=frozenset(), hot_terms={"gacha": 0.9})
    p = build_proposal(
        sig, c, standout_mechanic="a social tournament system", hot_terms={"gacha": 0.9}
    )
    assert p.candidate_title == "Heroes of the Wall"
    assert "social tournament" in p.whats_working
    assert p.differentiation.theme_to == "dragons"
    assert p.question.endswith("?")


def test_push_line_names_game_theme_and_asks_to_build():
    c = _rpg_candidate()
    sig = score_candidate(c, us_game_ids=frozenset())
    p = build_proposal(sig, c, standout_mechanic="a social tournament system")
    push = render_push(BriefedCandidate(c, sig, p), n_more=2)
    assert "Heroes of the Wall" in push
    assert "dragons" in push
    assert "prototype" in push.lower()
    assert "+2 more" in push


def test_shortlist_md_renders_each_pick_with_a_decision_line():
    c = _rpg_candidate()
    sig = score_candidate(c, us_game_ids=frozenset())
    p = build_proposal(sig, c, standout_mechanic="a social tournament system")
    md = render_shortlist_md([BriefedCandidate(c, sig, p)], chart_date="2026-10-14")
    assert "Heroes of the Wall" in md
    assert "gametagger-radar approve gp-com.studio.heroesofthewall" in md
    assert "Charts read: 2026-10-14" in md


def test_empty_shortlist_is_honest():
    assert "No candidate" in render_shortlist_md([])
