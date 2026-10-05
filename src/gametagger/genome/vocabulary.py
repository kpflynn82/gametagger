"""Extended Genome vocabulary for rich mode; the frozen pilot taxonomy file is never modified."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gametagger.domain import EvidenceType
from gametagger.taxonomy import TagDefinition, Taxonomy

VOCABULARY_FILE = "genome_tags_v1.yaml"
# Named vocabularies. v2 extends v1 (every v1 tag unchanged) with the mobile tags of Improvement 7.
VOCABULARIES = {"v1": "genome_tags_v1.yaml", "v2": "genome_tags_v2.yaml"}
EVIDENCE_POLICY_VERSION = "rich-evidence-v1"
TEXT_EVIDENCE = ("store_metadata", "developer_documentation", "wikipedia")
EVIDENCE_CLASSES = {"visual", "temporal", "system", "documentary"}


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    description: str


@dataclass(frozen=True)
class GenomeVocabulary:
    version: str
    categories: tuple[Category, ...]
    pilot_tags: tuple[TagDefinition, ...]
    extended_tags: tuple[TagDefinition, ...]
    # Follow-up questions: tag ID -> the parent tag ID that must be present before it is asked.
    requires: dict[str, str] = field(default_factory=dict)

    @property
    def tags(self) -> tuple[TagDefinition, ...]:
        return self.pilot_tags + self.extended_tags

    @property
    def tags_by_id(self) -> dict[str, TagDefinition]:
        return {tag.id: tag for tag in self.tags}

    @property
    def categories_by_id(self) -> dict[str, Category]:
        return {category.id: category for category in self.categories}

    def select(self, category_ids: list[str] | None) -> tuple[TagDefinition, ...]:
        """Tags in category display order, optionally limited to some categories."""
        if category_ids:
            unknown = set(category_ids) - set(self.categories_by_id)
            if unknown:
                raise ValueError(f"Unknown Genome categories: {', '.join(sorted(unknown))}")
        wanted = [c.id for c in self.categories if not category_ids or c.id in category_ids]
        return tuple(t for cid in wanted for t in self.tags if t.category == cid)


def default_vocabulary_path(name: str = "v1") -> Path:
    """The file of a named vocabulary (``v1`` or ``v2``), bundled or in the source tree."""
    if name not in VOCABULARIES:
        raise ValueError(f"Unknown vocabulary {name!r}; choose from {', '.join(VOCABULARIES)}")
    filename = VOCABULARIES[name]
    bundled = Path(__file__).resolve().parents[1] / "data" / filename
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parents[3] / "taxonomy" / filename


def _raw(path: Path, seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    """A vocabulary file, with the categories and tags of any file it ``extends`` first."""
    path = path.resolve()
    if path in seen:
        raise ValueError("Genome vocabulary files extend each other in a loop")
    raw = yaml.safe_load(path.read_text())
    base_name = raw.get("extends")
    if base_name is None:
        return raw
    if not isinstance(base_name, str) or "/" in base_name or "\\" in base_name:
        raise ValueError("'extends' must name a vocabulary file in the same folder")
    base = _raw(path.parent / base_name, (*seen, path))
    if clash := set(raw.get("categories") or {}) & set(base["categories"]):
        raise ValueError(f"Extending vocabulary redefines categories: {sorted(clash)}")
    return {
        **raw,
        "categories": {**base["categories"], **(raw.get("categories") or {})},
        "tags": [*base["tags"], *(raw.get("tags") or [])],
    }


def _text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Genome vocabulary field '{key}' must be nonempty text")
    return value.strip()


def _evidence(values: Any) -> tuple[str, ...]:
    allowed = {e.value for e in EvidenceType}
    if not isinstance(values, list) or not values or any(v not in allowed for v in values):
        raise ValueError("Genome vocabulary evidence lists must name known evidence types")
    return tuple(values)


def load_vocabulary(taxonomy: Taxonomy, path: str | Path | None = None) -> GenomeVocabulary:
    raw = _raw(Path(path or default_vocabulary_path()))
    categories, defaults = [], {}
    for cid, item in raw["categories"].items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", cid):
            raise ValueError("Invalid Genome category ID")
        if item.get("evidence_class") not in EVIDENCE_CLASSES:
            raise ValueError(f"Category {cid} needs a known evidence class")
        categories.append(Category(cid, _text(item, "label"), _text(item, "description")))
        defaults[cid] = item
    category_ids = {c.id for c in categories}
    if missing := {t.category for t in taxonomy.tags} - category_ids:
        raise ValueError(f"Pilot tag categories lack a display category: {sorted(missing)}")

    seen_ids = {t.id for t in taxonomy.tags}
    seen_labels = {t.label.casefold() for t in taxonomy.tags}
    extended, requires = [], {}
    for item in raw["tags"]:
        if set(item) - {
            "id",
            "label",
            "category",
            "definition",
            "instructions",
            "evidence_class",
            "allowed_evidence",
            "preferred_evidence",
            "requires",
        }:
            raise ValueError("Genome tag has unexpected fields")
        tid = _text(item, "id")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", tid) or tid == "insufficient_evidence":
            raise ValueError(f"Invalid Genome tag ID: {tid}")
        label = _text(item, "label")
        if tid in seen_ids or label.casefold() in seen_labels:
            raise ValueError(f"Duplicate Genome tag ID or label: {tid}")
        seen_ids.add(tid)
        seen_labels.add(label.casefold())
        category = _text(item, "category")
        if category not in category_ids:
            raise ValueError(f"Genome tag {tid} uses unknown category {category}")
        base = defaults[category]
        evidence_class = item.get("evidence_class", base["evidence_class"])
        if evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(f"Genome tag {tid} has an unknown evidence class")
        allowed = _evidence(item.get("allowed_evidence", base["allowed_evidence"]))
        if "requires" in item:
            requires[tid] = _text(item, "requires")
        extended.append(
            TagDefinition(
                id=tid,
                label=label,
                category=category,
                definition=_text(item, "definition"),
                evidence_class=evidence_class,
                preferred_evidence=_evidence(item.get("preferred_evidence", list(allowed))),
                allowed_evidence=allowed,
                instructions=str(item.get("instructions", "")).strip(),
            )
        )
    for child, parent in requires.items():
        # One level only: a follow-up's parent is an ordinary question, asked in the first round.
        if parent not in seen_ids or parent == child or parent in requires:
            raise ValueError(
                f"Genome tag {child} requires {parent}, which is not a first-round tag"
            )
    return GenomeVocabulary(
        version=_text(raw, "version"),
        categories=tuple(categories),
        pilot_tags=taxonomy.tags,
        extended_tags=tuple(extended),
        requires=requires,
    )


def rich_allowed_evidence(tag: TagDefinition, vocabulary: GenomeVocabulary) -> tuple[str, ...]:
    """Evidence types rich mode may show Jev for one tag (policy rich-evidence-v1).

    Extended tags use their own reviewed lists. Pilot tags keep their frozen lists; for pilot
    tags that describe systems, features, modes or timing (not appearance), attributed store,
    developer and encyclopedia text is added. A documented claim can support such a feature even
    though a still image cannot show it; the claim stays labelled as a claim, never a visual fact.
    """
    if tag not in vocabulary.pilot_tags or tag.evidence_class == "visual":
        return tag.allowed_evidence
    return tuple(dict.fromkeys([*tag.allowed_evidence, *TEXT_EVIDENCE]))
