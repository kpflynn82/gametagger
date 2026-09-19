from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class TagDefinition:
    id: str
    label: str
    category: str
    definition: str
    evidence_class: str
    preferred_evidence: tuple[str, ...]
    allowed_evidence: tuple[str, ...]
    instructions: str


@dataclass(frozen=True)
class GenreDefinition:
    id: str
    display_name: str
    family: str
    definition: str
    inclusion_criteria: tuple[str, ...]
    exclusion_notes: tuple[str, ...]
    example_games: tuple[str, ...]
    primary_eligible: bool


@dataclass(frozen=True)
class GenreFamily:
    id: str
    display_name: str
    definition: str
    genres: tuple[GenreDefinition, ...]

    @property
    def eligible_genres(self) -> tuple[GenreDefinition, ...]:
        return tuple(g for g in self.genres if g.primary_eligible)


@dataclass(frozen=True)
class Taxonomy:
    version: str
    tag_states: tuple[str, ...]
    tags: tuple[TagDefinition, ...]
    genre_families: tuple[GenreFamily, ...]

    @property
    def tags_by_id(self) -> dict[str, TagDefinition]:
        return {tag.id: tag for tag in self.tags}

    @property
    def families_by_id(self) -> dict[str, GenreFamily]:
        return {family.id: family for family in self.genre_families}

    @property
    def genres_by_id(self) -> dict[str, GenreDefinition]:
        return {genre.id: genre for family in self.genre_families for genre in family.genres}

    @property
    def primary_genres(self) -> tuple[str, ...]:
        """Display-name vocabulary for the existing Observer guard, not a flat classifier."""
        return tuple(g.display_name for g in self.genres_by_id.values() if g.primary_eligible)


def default_taxonomy_path() -> Path:
    bundled = Path(__file__).resolve().parent / "data" / "vgms_v4.yaml"
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parents[2] / "taxonomy" / "vgms_v4.yaml"


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Taxonomy text must be nonempty")
    return value


def _identifier(value: Any) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", _text(value)) or value == "insufficient_evidence":
        raise ValueError("Invalid or reserved taxonomy ID")
    return value


def _texts(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("Taxonomy criteria, notes, and examples must be nonempty lists")
    return tuple(_text(v) for v in value)


def load_taxonomy(path: str | Path | None = None) -> Taxonomy:
    target = Path(path) if path else default_taxonomy_path()
    raw: dict[str, Any] = yaml.safe_load(target.read_text())
    tags = tuple(
        TagDefinition(
            id=item["id"],
            label=item["label"],
            category=item["category"],
            definition=item["definition"],
            evidence_class=item["evidence_class"],
            preferred_evidence=tuple(item.get("preferred_evidence", [])),
            allowed_evidence=tuple(item.get("allowed_evidence", [])),
            instructions=item.get("instructions", ""),
        )
        for item in raw["tags"]
    )
    families = []
    family_ids, genre_ids, names = set(), set(), set()
    for family in raw["genre_families"]:
        if set(family) != {"id", "display_name", "definition", "genres"}:
            raise ValueError("Genre family has missing or unexpected fields")
        fid = _identifier(family["id"])
        if fid in family_ids:
            raise ValueError("Duplicate genre family ID")
        family_ids.add(fid)
        genres = []
        for item in family["genres"]:
            if set(item) != set(GenreDefinition.__dataclass_fields__):
                raise ValueError("Genre definition has missing or unexpected fields")
            gid = _identifier(item["id"])
            name = _text(item["display_name"])
            if gid in genre_ids or name in names:
                raise ValueError("Duplicate genre ID or display name")
            if item["family"] != fid:
                raise ValueError("Genre family must match its containing family")
            if type(item["primary_eligible"]) is not bool:
                raise ValueError("primary_eligible must be a boolean")
            genre_ids.add(gid)
            names.add(name)
            genres.append(
                GenreDefinition(
                    id=gid,
                    display_name=name,
                    family=fid,
                    definition=_text(item["definition"]),
                    inclusion_criteria=_texts(item["inclusion_criteria"]),
                    exclusion_notes=_texts(item["exclusion_notes"]),
                    example_games=_texts(item["example_games"]),
                    primary_eligible=item["primary_eligible"],
                )
            )
        if not any(g.primary_eligible for g in genres):
            raise ValueError("Each classified family must have an eligible genre")
        families.append(
            GenreFamily(
                id=fid,
                display_name=_text(family["display_name"]),
                definition=_text(family["definition"]),
                genres=tuple(genres),
            )
        )
    if len(families) < 2:
        raise ValueError("Hierarchical classification requires at least two families")
    return Taxonomy(
        version=str(raw["version"]),
        tag_states=tuple(raw["tag_states"]),
        tags=tags,
        genre_families=tuple(families),
    )
