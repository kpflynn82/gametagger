"""The build spec for a clone: mechanics Claude owns, plus the art list Codex fills.

A ``CloneSpec`` is engine-agnostic structured data. It can be built straight from a radar build
proposal (the fast path: Heroes-of-the-Wall -> spec) or from a finished GDD. ``scaffold_clone``
reads it to emit a runnable web skeleton and the Codex art brief.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Dimensionality = Literal["2d", "3d"]
Engine = Literal["phaser", "three"]

# Which web engine suits which genre family for a fast prototype. Unity is the final-build target
# (noted in the scaffold README), not produced here.
FAMILY_ENGINE: dict[str, tuple[Dimensionality, Engine]] = {
    "role_playing": ("2d", "phaser"),
    "strategy": ("2d", "phaser"),
    "puzzle": ("2d", "phaser"),
    "casual_idle": ("2d", "phaser"),
    "simulation_management": ("2d", "phaser"),
    "action": ("3d", "three"),
    "racing": ("3d", "three"),
    "sports": ("3d", "three"),
}

# Baseline art every prototype needs, plus family-specific pieces. Codex generates against this.
BASE_ASSETS: tuple[tuple[str, str, str], ...] = (
    ("background", "1080x1920", "the main play-screen background"),
    ("ui_button_primary", "512x160", "the primary call-to-action button"),
    ("currency_soft_icon", "256x256", "the soft (earned) currency icon"),
    ("currency_hard_icon", "256x256", "the premium (bought) currency icon"),
    ("reward_chest", "512x512", "a closed reward chest, plus an open frame"),
)
FAMILY_ASSETS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "role_playing": (
        ("hero_portrait", "512x512", "the player's hero portrait"),
        ("enemy_sprite", "512x512", "a representative enemy"),
        ("tournament_banner", "1080x420", "the social-tournament header banner"),
    ),
    "strategy": (
        ("base_tile", "512x512", "the player's base/building tile"),
        ("unit_sprite", "384x384", "a marching unit"),
    ),
    "puzzle": (
        ("tile_set", "128x128", "the set of board tiles (one sprite sheet)"),
        ("booster_icons", "256x256", "the booster icon set"),
    ),
    "casual_idle": (
        ("stage_sprite", "512x512", "the thing that evolves/levels up, early stage"),
        ("stage_sprite_max", "512x512", "the same thing at max stage"),
    ),
    "simulation_management": (
        ("plot_tile", "512x512", "a buildable plot/room tile"),
        ("decor_item", "256x256", "a representative decoration"),
    ),
}


@dataclass(frozen=True)
class ArtAsset:
    name: str
    size: str
    description: str

    @property
    def filename(self) -> str:
        return f"{self.name}.png"


@dataclass
class CloneSpec:
    title: str  # the clone's working title (NOT the target's name)
    family: str
    theme: str
    core_loop: str
    keep: list[str] = field(default_factory=list)  # systems cloned faithfully
    add: list[str] = field(default_factory=list)  # added mechanics (e.g. gacha)
    directions: list[str] = field(default_factory=list)  # Kevin's freeform directions
    screens: list[str] = field(default_factory=lambda: ["Home", "Play", "Shop", "Progress"])
    economy: dict = field(default_factory=dict)
    source_note: str = ""  # one line on the teardown this came from (for provenance)

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-") or "clone"

    @property
    def dimensionality(self) -> Dimensionality:
        return FAMILY_ENGINE.get(self.family, ("2d", "phaser"))[0]

    @property
    def engine(self) -> Engine:
        return FAMILY_ENGINE.get(self.family, ("2d", "phaser"))[1]

    def art_assets(self) -> list[ArtAsset]:
        specs = list(BASE_ASSETS) + list(FAMILY_ASSETS.get(self.family, ()))
        themed = []
        for name, size, desc in specs:
            themed.append(ArtAsset(name=name, size=size, description=f"{desc}, {self.theme} theme"))
        return themed

    @classmethod
    def from_proposal(
        cls,
        *,
        title: str,
        family: str,
        theme: str,
        keep: list[str],
        add: list[str],
        core_loop: str = "",
        directions: list[str] | None = None,
        source_note: str = "",
    ) -> CloneSpec:
        return cls(
            title=title,
            family=family or "unknown",
            theme=theme,
            core_loop=core_loop
            or (
                f"Play the core {family.replace('_', ' ')} loop; "
                f"{', '.join(keep) or 'earn, upgrade, return'}."
            ),
            keep=list(keep),
            add=list(add),
            directions=list(directions or []),
            source_note=source_note,
        )
