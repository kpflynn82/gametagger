"""Faithful adapter of the original GenomeTagger single-call tagger, run on a rich-mode dossier.

The prompt, the 59-genre list, the tag categories, the JSON parsing and the post-processing are
copied verbatim from ``backend/app/services/tagger.py`` in ``kpflynn82/gametagger-web`` at
commit ``4b710fd6`` (LEGACY_SOURCE). Only the evidence gathering changes: instead of searching
Steam, Xbox and Wikipedia by name, the adapter reads the same dossier rich mode reads, so both
methods see identical inputs. Every adaptation is listed in ADAPTATIONS and recorded with each
result, so this is an honestly labelled *adapted* baseline, never the live production site.

The original silently replaces an unknown primary genre with a guessed one (``Action Adventure``
by default). That behaviour is reproduced because it is part of the old method, but every result
also records how its genre was resolved, so forced fallbacks can be scored separately.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from PIL import Image

from gametagger.genome.dossier import Dossier, TextSource

LEGACY_SOURCE = {
    "repository": "kpflynn82/gametagger-web",
    "commit": "4b710fd6c4086a49f25a573f6c81ebf3efbd2092",
    "path": "backend/app/services/tagger.py",
}
ADAPTER_VERSION = "legacy-adapter-v1"
ADAPTATIONS = (
    "Evidence comes from the shared benchmark dossier (exact store IDs), not a name search.",
    "No Xbox store section: the benchmark dossier has no Xbox source.",
    "Apple App Store and Google Play listings are formatted like the original Xbox section.",
    "Wikipedia 'Developer' line omitted: the dossier keeps genres, modes and platforms only.",
    "Screenshots are the first two per store, re-encoded as 600-pixel-wide JPEG to match the "
    "Steam thumbnails the original sent; YouTube stills are not sent (disabled in production).",
    "Trailer frames are off, as in the original's default (ENABLE_TRAILER_FRAMES unset); the "
    "production value of that flag is unverified.",
    "The Anthropic workspace header is sent when ANTHROPIC_WORKSPACE_ID is set.",
)

# --------------------------------------------------------------------------- verbatim copies

# VGMS Schema
VGMS_CATEGORIES = {
    "gameplay": [
        "action", "adventure", "rpg", "strategy", "simulation", "sports",
        "platformer", "puzzle", "shooter", "stealth", "survival", "rhythm",
        "party", "roguelike", "fighting", "racing",
    ],
    "narrative": ["horror", "comedy", "mystery", "scifi", "fantasy", "historical", "western"],
    "theme": [
        "war", "exploration", "survival", "crime", "family", "revenge",
        "coming_of_age", "politics", "environmental",
    ],
    "setting": [
        "fantasy", "scifi", "contemporary", "historical", "post_apocalyptic",
        "urban", "rural", "underwater", "space",
    ],
    "mechanic": [
        "leveling", "crafting", "farming", "building", "collection", "inventory",
        "permadeath", "time_management", "resource_management", "stealth",
        "parkour", "dialogue_choices", "moral_choices", "romance",
    ],
    "visual": ["realistic", "stylized", "pixel_art", "minimalist", "hand_drawn"],
    "features": ["multiplayer", "open_world", "procedural", "story_driven"],
    # Nitrogen-specific categories
    "engagement": [
        "gacha", "daily_rewards", "energy_system", "pvp", "guild",
        "events", "battle_pass", "auto_play",
    ],
    "monetization": ["free_to_play", "premium", "subscription", "iap"],
    "protagonist": ["customizable", "predefined", "ensemble", "non_human"],
    # Accessibility features
    "accessibility": [
        "colorblind_modes", "subtitle_options", "difficulty_options",
        "motor_accessibility", "cognitive_assist",
    ],
    # Demographic appeal
    "demographic": [
        "family_friendly", "teen_focused", "mature_audience",
        "female_protagonist", "diverse_cast", "nostalgia_retro",
    ],
}  # fmt: skip

# Standardized primary genres (must match expanded_taxonomy.py v3.2 - 50 genres)
PRIMARY_GENRES_LIST = [
    # Action-based (no generic "Action" - use specific sub-genres)
    "Action RPG", "Action Adventure", "First-Person Shooter", "Third-Person Shooter",
    "Bullet Hell", "Beat 'em Up",
    # Shooter sub-genres (distinct by progression/risk model)
    "Looter Shooter",  # Persistent gear, PvE grind (Destiny, Borderlands, The Division)
    "Extraction Shooter",  # Gear at risk, PvPvE sessions (Tarkov, Hunt: Showdown, The Finals)
    # RPG variants
    "JRPG", "Turn-Based RPG", "Tactical RPG", "MMORPG", "Roguelike",
    # Platformers
    "2D Platformer", "3D Platformer", "Metroidvania",
    # Strategy
    "Real-Time Strategy", "Turn-Based Strategy", "Tower Defense", "4X Strategy",
    "Grand Strategy",
    "Auto Battler",  # Automated combat, strategic setup (Teamfight Tactics, Dota Underlords)
    "MOBA",  # Lane-pushing team PvP (League of Legends, Dota 2, Smite)
    # Simulation
    "Life Simulation", "Farm Simulation", "Management Simulation", "Racing Simulation",
    "Flight Simulation", "City Builder",
    # Puzzle
    "Puzzle", "Puzzle Platformer", "Match-3", "Physics Puzzle",
    # Adventure
    "Adventure", "Narrative Adventure", "Visual Novel",
    # Fighting
    "2D Fighting", "3D Fighting",
    # Racing
    "Arcade Racing", "Kart Racing", "Rally Racing",
    # Sports & Horror
    "Sports", "Horror",
    # Card/Board
    "Card Game", "Deck Builder", "Board Game", "Digital TCG",
    # Multiplayer-focused
    "Battle Royale",  # Last standing, no gear persistence (Fortnite, PUBG, Apex Legends)
    "Party Game",
    # Sandbox/Survival
    "Sandbox",
    "Survival",
    "Open World Survival Craft",  # Building + crafting + survival (Minecraft, Valheim, Rust)
    # Other
    "Arcade", "Rhythm Game", "Cozy Game", "Idle Game", "Souls-like", "Immersive Sim",
    "Educational",
]  # fmt: skip

ANALYSIS_PROMPT = """Analyze this game and classify it using VGMS (Video Game Metadata Schema).

GAME: {game_name}

{context}

Based on all available information, return a JSON object with:

1. Boolean tags for each category (prefix_tag format):
   - gameplay_action, gameplay_adventure, gameplay_rpg, gameplay_strategy, etc.
   - narrative_horror, narrative_comedy, narrative_scifi, narrative_fantasy, etc.
   - theme_war, theme_exploration, theme_survival, etc.
   - setting_fantasy, setting_scifi, setting_contemporary, etc.
   - mechanic_leveling, mechanic_crafting, mechanic_building, etc.
   - visual_realistic, visual_stylized, visual_pixel_art, etc.
   - multiplayer, open_world, procedural, story_driven
   - engagement_gacha, engagement_daily_rewards, engagement_energy_system, engagement_pvp, engagement_guild, engagement_events, engagement_battle_pass, engagement_auto_play
   - monetization_free_to_play, monetization_premium, monetization_subscription, monetization_iap
   - protagonist_customizable, protagonist_predefined, protagonist_ensemble, protagonist_non_human
   - accessibility_colorblind_modes, accessibility_subtitle_options, accessibility_difficulty_options, accessibility_motor_accessibility, accessibility_cognitive_assist
   - demographic_family_friendly, demographic_teen_focused, demographic_mature_audience, demographic_female_protagonist, demographic_diverse_cast, demographic_nostalgia_retro

2. Metadata:
   - detected_game: The game name you identified
   - confidence: "high", "medium", or "low"
   - primary_genre: MUST be one of these exact values: {genres}
   - secondary_genres: A list of up to 2 OTHER genres from that exact same list that also strongly apply (most relevant first). Do NOT repeat the primary genre. Use [] if the game is essentially a single genre.
   - analysis_notes: Brief notes about classification reasoning

Return ONLY valid JSON, no other text.
"""  # noqa: E501

# Standard uses Haiku for cost efficiency; deep uses Opus for highest accuracy (original values).
QUALITY_SETTINGS = {
    "standard": {"model": "claude-haiku-4-5-20251001", "max_tokens": 2000, "timeout": 120},
    "deep": {"model": "claude-opus-4-8", "max_tokens": 4000, "timeout": 180},
}
Quality = Literal["standard", "deep"]

# Metadata keys the original returns alongside boolean tags.
METADATA_KEYS = {
    "detected_game",
    "confidence",
    "primary_genre",
    "secondary_genres",
    "analysis_notes",
    "error",
}

# --------------------------------------------------------------------------- evidence -> prompt

STORE_HEADINGS = {
    "steam": "STEAM STORE",
    "appstore": "APPLE APP STORE",
    "googleplay": "GOOGLE PLAY",
}
THUMBNAIL_WIDTH = 600  # Steam's path_thumbnail width, which the original downloaded
SCREENSHOTS_PER_STORE = 2  # original: screenshots[:(1 if trailer_frames else 2)]


def _join(values: list[str] | None) -> str:
    return ", ".join(values or [])


def _steam_section(source: TextSource) -> list[str]:
    # The original's Steam "Description" is short_description, which the dossier keeps as the
    # first line of the Steam text (short description, then the full "about" text).
    description = source.text.split("\n", 1)[0]
    return [
        "STEAM STORE:",
        f"  Title: {source.reported_title or 'Unknown'}",
        f"  Genres: {_join(source.fields.get('store_genres'))}",
        f"  Categories: {_join(source.fields.get('store_features'))}",
        f"  Description: {description[:1000]}",
    ]


def _store_section(source: TextSource) -> list[str]:
    # Adapted: mobile stores use the original Xbox section's layout.
    return [
        f"{STORE_HEADINGS.get(source.id, source.provider.upper())}:",
        f"  Title: {source.reported_title or 'Unknown'}",
        f"  Categories: {_join(source.fields.get('store_genres'))}",
        f"  Description: {source.text[:1000]}",
    ]


def _wikipedia_section(source: TextSource) -> list[str]:
    lines = ["WIKIPEDIA:", f"  Article: {source.reported_title or 'Unknown'}"]
    if source.fields.get("genres"):
        lines.append(f"  Genres (from infobox): {_join(source.fields['genres'])}")
    if source.fields.get("modes"):
        lines.append(f"  Game Modes: {_join(source.fields['modes'])}")
    if source.fields.get("platforms"):
        lines.append(f"  Platforms: {_join(source.fields['platforms'])}")
    if source.text:
        lines.append(f"  Description: {source.text[:1500][:1000]}")
    return lines


def thumbnail(path: str | Path, width: int = THUMBNAIL_WIDTH) -> bytes:
    """Decode an image and re-encode it as a JPEG no wider than ``width`` (quality 85)."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        if image.width > width:
            image = image.resize((width, max(1, round(image.height * width / image.width))))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=85)
        return out.getvalue()


@dataclass
class LegacyInput:
    """Exactly what the old method is shown for one game."""

    prompt: str
    image_ids: list[str]
    images: list[bytes]
    sections: list[str]
    omitted_sources: list[str]

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.prompt.encode()).hexdigest()


def build_input(dossier: Dossier, *, game_name: str | None = None) -> LegacyInput:
    """Order follows the original: Steam, then the other stores (Xbox's slot), then Wikipedia."""
    by_id = {s.id: s for s in dossier.sources}
    order = ["steam", "appstore", "googleplay", "wikipedia"]
    context, sections = [], []
    for sid in order:
        source = by_id.get(sid)
        if source is None:
            continue
        if sid == "steam":
            context += _steam_section(source)
        elif sid == "wikipedia":
            context += _wikipedia_section(source)
        else:
            context += _store_section(source)
        sections.append(sid)
    omitted = [s.id for s in dossier.sources if s.id not in order]
    image_ids, images = [], []
    for provider_prefix in ("Steam", "Apple App Store", "Google Play"):
        shots = [
            i
            for i in dossier.images
            if i.role == "store_screenshot" and i.provider.startswith(provider_prefix)
        ]
        for image in shots[:SCREENSHOTS_PER_STORE]:
            image_ids.append(image.id)
            images.append(thumbnail(image.path))
    genres = ", ".join(f'"{g}"' for g in PRIMARY_GENRES_LIST)
    prompt = ANALYSIS_PROMPT.format(
        game_name=game_name or dossier.title or dossier.game_id,
        context="\n".join(context),
        genres=genres,
    )
    return LegacyInput(prompt, image_ids, images, sections, omitted)


def request_content(legacy_input: LegacyInput) -> list[dict[str, Any]]:
    """The original inserts the prompt first, then every image."""
    content: list[dict[str, Any]] = [{"type": "text", "text": legacy_input.prompt}]
    for data in legacy_input.images:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(data).decode("ascii"),
                },
            }
        )
    return content


# --------------------------------------------------------------------------- response handling


def parse_response(response_text: str) -> dict[str, Any]:
    """The original's parser: first '{' to last '}', then flatten nested ``*_tags`` objects."""
    json_match = re.search(r"\{[\s\S]*\}", response_text)
    if not json_match:
        return {"error": "Could not parse response"}
    try:
        result = json.loads(json_match.group())
    except ValueError as exc:
        return {"error": f"Analysis failed ({type(exc).__name__}): {exc}"}
    if not isinstance(result, dict):
        return {"error": "Analysis failed (TypeError): response is not a JSON object"}
    flattened = {}
    for key, value in result.items():
        if isinstance(value, dict) and key.endswith("_tags"):
            for tag_key, tag_value in value.items():
                flattened[tag_key] = tag_value
        else:
            flattened[key] = value
    return flattened


GenreResolution = Literal["exact", "matched_case_or_substring", "forced_fallback", "missing"]


def postprocess(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply the original's validation; return (legacy result, audit of what was changed)."""
    result = dict(result)
    audit: dict[str, Any] = {"raw_primary_genre": result.get("primary_genre")}
    tag_count = sum(1 for v in result.values() if isinstance(v, bool) and v)
    if tag_count == 0 and result.get("confidence") != "low":
        result["confidence"] = "low"
        result["analysis_notes"] = (
            result.get("analysis_notes", "")
            + " [Warning: No tags extracted, confidence downgraded to low]"
        ).strip()
    if result.get("confidence") not in ("high", "medium", "low"):
        result["confidence"] = "medium" if tag_count > 0 else "low"

    resolution: GenreResolution = "missing"
    current_genre = result.get("primary_genre", "")
    if current_genre and current_genre in PRIMARY_GENRES_LIST:
        resolution = "exact"
    elif current_genre:
        genre_lower = str(current_genre).lower()
        matched = None
        for allowed in PRIMARY_GENRES_LIST:
            if allowed.lower() == genre_lower:
                matched = allowed
                break
            if allowed.lower() in genre_lower or genre_lower in allowed.lower():
                matched = allowed
                break
        if matched:
            result["primary_genre"] = matched
            resolution = "matched_case_or_substring"
        else:
            resolution = "forced_fallback"
            if result.get("gameplay_shooter") or result.get("gameplay_fps"):
                result["primary_genre"] = "First-Person Shooter"
            elif result.get("gameplay_rpg"):
                result["primary_genre"] = "Action RPG"
            elif result.get("gameplay_platformer"):
                result["primary_genre"] = "2D Platformer"
            elif result.get("gameplay_strategy"):
                result["primary_genre"] = "Real-Time Strategy"
            elif result.get("gameplay_puzzle"):
                result["primary_genre"] = "Puzzle"
            elif result.get("gameplay_adventure"):
                result["primary_genre"] = "Adventure"
            elif result.get("gameplay_simulation"):
                result["primary_genre"] = "Life Simulation"
            elif result.get("gameplay_fighting"):
                result["primary_genre"] = "2D Fighting"
            elif result.get("gameplay_racing"):
                result["primary_genre"] = "Arcade Racing"
            else:
                result["primary_genre"] = "Action Adventure"  # Safe default
    audit["primary_genre_resolution"] = resolution

    raw_secondary = result.get("secondary_genres")
    cleaned_secondary: list[str] = []
    if isinstance(raw_secondary, list):
        primary = result.get("primary_genre", "")
        for g in raw_secondary:
            if (
                isinstance(g, str)
                and g in PRIMARY_GENRES_LIST
                and g != primary
                and g not in cleaned_secondary
            ):
                cleaned_secondary.append(g)
            if len(cleaned_secondary) >= 2:
                break
    audit["raw_secondary_genres"] = raw_secondary
    result["secondary_genres"] = cleaned_secondary
    audit["true_tag_count"] = tag_count
    return result, audit


def boolean_tags(result: dict[str, Any]) -> dict[str, bool]:
    """Tag keys the model answered with a JSON boolean. Missing keys are unknown, never False."""
    return {k: v for k, v in result.items() if isinstance(v, bool) and k not in METADATA_KEYS}


# --------------------------------------------------------------------------- the call


@dataclass
class LegacyRun:
    quality: Quality
    requested_model: str
    returned_model: str | None = None
    status: Literal["valid", "parse_error", "provider_error"] = "valid"
    result: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int | None] | None = None
    stop_reason: str | None = None
    latency_ms: dict[str, float] = field(default_factory=dict)
    prompt_sha256: str | None = None
    image_ids: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    omitted_sources: list[str] = field(default_factory=list)
    error: str | None = None
    raw_text: str | None = None

    def to_json(self) -> dict[str, Any]:
        data = dict(vars(self))
        data["adapter_version"] = ADAPTER_VERSION
        data["legacy_source"] = LEGACY_SOURCE
        data["adaptations"] = list(ADAPTATIONS)
        return data


class LegacyTagger:
    """One Claude request per game, as the original site made. The client is injected."""

    def __init__(self, client: Any, *, workspace_id: str | None = None):
        self.client = client
        self.workspace_id = workspace_id

    def tag(self, dossier: Dossier, quality: Quality, *, game_name: str | None = None) -> LegacyRun:
        settings = QUALITY_SETTINGS[quality]
        run = LegacyRun(quality=quality, requested_model=settings["model"])
        start = perf_counter()
        legacy_input = build_input(dossier, game_name=game_name)
        content = request_content(legacy_input)
        run.prompt_sha256 = legacy_input.prompt_sha256
        run.image_ids = legacy_input.image_ids
        run.sections = legacy_input.sections
        run.omitted_sources = legacy_input.omitted_sources
        prepared = perf_counter()
        kwargs: dict[str, Any] = dict(
            model=settings["model"],
            max_tokens=settings["max_tokens"],
            messages=[{"role": "user", "content": content}],
        )
        if self.workspace_id:
            kwargs["extra_headers"] = {"anthropic-workspace-id": self.workspace_id}
        try:
            response = self.client.with_options(timeout=settings["timeout"]).messages.create(
                **kwargs
            )
        except Exception as exc:  # recorded as a provider failure; stays in denominators
            run.status = "provider_error"
            run.error = f"{type(exc).__name__}: {str(exc)[:300]}"
            run.latency_ms = {
                "prepare": (prepared - start) * 1000,
                "call": (perf_counter() - prepared) * 1000,
            }
            run.result, run.audit = postprocess({"error": run.error})
            return run
        called = perf_counter()
        run.returned_model = getattr(response, "model", None)
        run.stop_reason = getattr(response, "stop_reason", None)
        usage = getattr(response, "usage", None)
        if usage is not None:
            run.usage = {
                k: getattr(usage, k, None)
                for k in (
                    "input_tokens",
                    "output_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
            }
        # The original reads content[0].text; keep that, including its failure mode.
        blocks = getattr(response, "content", None) or []
        text = getattr(blocks[0], "text", "") if blocks else ""
        run.raw_text = text
        parsed = parse_response(text or "")
        if "error" in parsed:
            run.status = "parse_error"
            run.error = parsed["error"]
        run.result, run.audit = postprocess(parsed)
        run.latency_ms = {
            "prepare": (prepared - start) * 1000,
            "call": (called - prepared) * 1000,
            "parse": (perf_counter() - called) * 1000,
        }
        return run
