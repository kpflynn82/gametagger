"""Wiring the weekly digest into the radar's trend map."""

from __future__ import annotations

from gametagger.radar.digest import (
    digest_terms_or_default,
    extract_hot_terms,
    load_digest_terms,
    newest_digest,
)

SAMPLE = """# Weekly mobile trends digest -- 2026-10-14

## Themes

Merge keeps winning: three of this week's breakouts are merge games, and merge-2 variants are
spreading. Collection albums (sticker albums especially) are still the hottest retention feature,
now appearing in midcore. Social tournaments and guild events drove the quarter's biggest ARPU
lifts. Decorating metas continue in casual.

## Relevance to Blueprint Flight

Watch the merge + album pairing.
"""


def test_extract_counts_and_weights():
    terms = extract_hot_terms(SAMPLE)
    # merge is mentioned repeatedly, so it outweighs a single-mention term.
    assert terms["merge"] > terms["decorating meta"]
    assert "collection album" in terms
    assert "social tournament" in terms
    assert all(0.0 < w <= 1.0 for w in terms.values())


def test_no_midword_false_positive():
    # "emergency" must not count as "merge"; "assortment" must not count as a sort term.
    terms = extract_hot_terms("An emergency assortment of resorts.")
    assert "merge" not in terms


def test_newest_digest_picks_latest_date(tmp_path):
    (tmp_path / "trend-digest-2026-09-30.md").write_text("Merge.")
    (tmp_path / "trend-digest-2026-10-14.md").write_text("Gacha and gacha summon.")
    newest = newest_digest(tmp_path)
    assert newest is not None and "2026-10-14" in newest.name
    terms = load_digest_terms(tmp_path)
    assert "gacha" in terms and "merge" not in terms


def test_fallback_to_defaults_when_no_digest(tmp_path):
    # An empty folder yields no terms, so the caller falls back to the dated built-in map.
    assert load_digest_terms(tmp_path) == {}
    defaults = digest_terms_or_default(tmp_path)
    assert defaults and "collection album" in defaults


def test_file_path_and_floor(tmp_path):
    f = tmp_path / "trend-digest-2026-10-14.md"
    f.write_text(SAMPLE)
    assert len(load_digest_terms(f)) >= 3
    # A digest that mentions nothing in the vocabulary returns empty (below the floor).
    bare = tmp_path / "trend-digest-2026-10-15.md"
    bare.write_text("A quiet week. Funding news only.")
    assert load_digest_terms(bare, floor=1) == {}
