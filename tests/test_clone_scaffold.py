"""The clone spec and scaffold: engine choice, the Codex handoff and a runnable skeleton."""

from __future__ import annotations

import json

from gametagger.clone import CloneSpec, scaffold_clone


def _spec():
    return CloneSpec.from_proposal(
        title="Wyrmwall Legends",
        family="role_playing",
        theme="dragons",
        keep=["social tournament system"],
        add=["gacha"],
        directions=["younger dragons a touch cuter, not too young"],
        source_note="From the Heroes of the Wall teardown (radar pick 2026-10-14).",
    )


def test_engine_follows_family():
    assert _spec().engine == "phaser"  # role_playing -> 2D/phaser
    flight = CloneSpec.from_proposal(
        title="Paper Glider", family="action", theme="origami", keep=["glide"], add=[]
    )
    assert flight.engine == "three" and flight.dimensionality == "3d"


def test_slug_is_clean():
    assert _spec().slug == "wyrmwall-legends"


def test_art_assets_are_themed_and_include_family_pieces():
    assets = _spec().art_assets()
    names = {a.name for a in assets}
    assert "hero_portrait" in names  # role_playing family asset
    assert all("dragons" in a.description for a in assets)  # theme applied


def test_scaffold_writes_a_runnable_skeleton_and_handoff(tmp_path):
    written = scaffold_clone(_spec(), tmp_path)
    for label in ("readme", "directions", "art_brief", "manifest", "index", "main"):
        assert written[label].exists()

    index = written["index"].read_text()
    assert "phaser" in index  # the pinned Phaser CDN for a 2D game
    assert "Wyrmwall Legends" in index

    directions = written["directions"].read_text()
    assert "gacha" in directions
    assert "dragons" in directions
    assert "Tetris v. Xio" in directions  # the legal line is always present

    manifest = json.loads(written["manifest"].read_text())
    assert manifest["theme"] == "dragons"
    assert any(a["name"] == "tournament_banner" for a in manifest["assets"])

    art_brief = written["art_brief"].read_text()
    assert "Original art only" in art_brief
    assert "hero_portrait.png" in art_brief
