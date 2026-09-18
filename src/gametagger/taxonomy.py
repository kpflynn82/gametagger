from __future__ import annotations

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
class Taxonomy:
    version: str
    tag_states: tuple[str, ...]
    tags: tuple[TagDefinition, ...]
    primary_genres: tuple[str, ...]

    @property
    def tags_by_id(self) -> dict[str, TagDefinition]:
        return {tag.id: tag for tag in self.tags}


def default_taxonomy_path() -> Path:
    bundled = Path(__file__).resolve().parent / "data" / "vgms_v4.yaml"
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parents[2] / "taxonomy" / "vgms_v4.yaml"


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
    return Taxonomy(
        version=str(raw["version"]),
        tag_states=tuple(raw["tag_states"]),
        tags=tags,
        primary_genres=tuple(raw["primary_genres"]),
    )
