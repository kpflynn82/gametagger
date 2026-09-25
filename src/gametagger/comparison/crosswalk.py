"""Draft label crosswalks (old genres, old tags, Steam user tags) loaded and validated.

Every target ID is checked against the v4.1 taxonomy and the Genome vocabulary on load, so a
typo cannot silently drop a mapping. The files are drafts pending owner approval, and every score
that uses them carries their version and status.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from gametagger.genome.vocabulary import GenomeVocabulary
from gametagger.taxonomy import Taxonomy

FILES = {
    "legacy_genres": "legacy59_to_v4.yaml",
    "legacy_tags": "legacy_tags_to_genome.yaml",
    "steam_tags": "steam_tags_to_genome.yaml",
}
GENRE_RELATIONS = {"exact", "one_of", "family", "none"}
TAG_RELATIONS = {"exact", "close", "none"}


def crosswalk_dir() -> Path:
    bundled = Path(__file__).resolve().parents[1] / "data" / "crosswalks"
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parents[3] / "taxonomy" / "crosswalks"


@dataclass(frozen=True)
class Crosswalks:
    legacy_genres: dict[str, dict[str, Any]]
    legacy_tags: dict[str, dict[str, Any]]
    steam_tags: dict[str, dict[str, list[str]]]
    steam_unmapped: frozenset[str]
    versions: dict[str, str]
    family_of: dict[str, str]  # v4 genre id -> family id

    def legacy_genre_targets(self, label: str | None) -> dict[str, Any]:
        """{'relation', 'v4': [...], 'families': [...]} for an old primary-genre label."""
        entry = self.legacy_genres.get(label or "")
        if not entry:
            return {"relation": "unmapped", "v4": [], "families": []}
        v4 = list(entry.get("v4") or [])
        families = sorted(
            {self.family_of[g] for g in v4} | set(filter(None, [entry.get("family")]))
        )
        return {"relation": entry["relation"], "v4": v4, "families": families}

    def legacy_tag_target(self, key: str) -> tuple[str | None, str]:
        entry = self.legacy_tags.get(key)
        if not entry:
            return None, "unmapped"
        return entry.get("genome"), entry["relation"]

    def steam_targets(self, tag: str) -> dict[str, list[str]] | None:
        return self.steam_tags.get(tag)


def load_crosswalks(
    taxonomy: Taxonomy, vocabulary: GenomeVocabulary, directory: Path | None = None
) -> Crosswalks:
    directory = directory or crosswalk_dir()
    raw = {k: yaml.safe_load((directory / f).read_text()) for k, f in FILES.items()}
    genres = set(taxonomy.genres_by_id)
    families = {f.id for f in taxonomy.genre_families}
    tags = set(vocabulary.tags_by_id)
    family_of = {g.id: g.family for g in taxonomy.genres_by_id.values()}

    for label, entry in raw["legacy_genres"]["genres"].items():
        relation = entry.get("relation")
        if relation not in GENRE_RELATIONS:
            raise ValueError(f"Old genre {label}: unknown relation {relation}")
        v4 = entry.get("v4") or []
        if unknown := set(v4) - genres:
            raise ValueError(f"Old genre {label}: unknown v4 genres {sorted(unknown)}")
        if relation == "exact" and len(v4) != 1:
            raise ValueError(f"Old genre {label}: an exact mapping names exactly one genre")
        if relation == "one_of" and len(v4) < 2:
            raise ValueError(f"Old genre {label}: one_of needs at least two genres")
        if relation == "family" and entry.get("family") not in families:
            raise ValueError(f"Old genre {label}: family mapping needs a known family")
    for key, entry in raw["legacy_tags"]["tags"].items():
        if entry.get("relation") not in TAG_RELATIONS:
            raise ValueError(f"Old tag {key}: unknown relation")
        if entry["relation"] != "none" and entry.get("genome") not in tags:
            raise ValueError(f"Old tag {key}: unknown Genome tag {entry.get('genome')}")
    steam = {}
    for name, entry in raw["steam_tags"]["tags"].items():
        genome, mapped_genres = list(entry.get("genome") or []), list(entry.get("genres") or [])
        if unknown := (set(genome) - tags) | (set(mapped_genres) - genres):
            raise ValueError(f"Steam tag {name}: unknown targets {sorted(unknown)}")
        if not genome and not mapped_genres:
            raise ValueError(f"Steam tag {name}: map it to something or list it as unmapped")
        steam[name] = {"genome": genome, "genres": mapped_genres}
    unmapped = frozenset(raw["steam_tags"].get("unmapped") or [])
    if overlap := unmapped & set(steam):
        raise ValueError(f"Steam tags both mapped and unmapped: {sorted(overlap)}")
    return Crosswalks(
        legacy_genres=raw["legacy_genres"]["genres"],
        legacy_tags=raw["legacy_tags"]["tags"],
        steam_tags=steam,
        steam_unmapped=unmapped,
        versions={k: f"{v['version']} ({v['status']})" for k, v in raw.items()},
        family_of=family_of,
    )
