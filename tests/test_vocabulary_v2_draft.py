"""The vocabulary v2 draft is well formed and does not collide with v1 or the pilot taxonomy.

The draft is not loaded by the pipeline until the owner approves it (Improvement 7). These checks
keep it buildable while it is reviewed.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from gametagger.domain import EvidenceType
from gametagger.genome.vocabulary import load_vocabulary

DRAFT = Path(__file__).resolve().parents[1] / "taxonomy/drafts/genome_tags_v2_additions.draft.yaml"


def draft():
    return yaml.safe_load(DRAFT.read_text())


def test_draft_tags_are_complete_and_use_known_evidence():
    raw = draft()
    evidence = {e.value for e in EvidenceType}
    assert raw["version"] == "genome-tags-v2-draft"
    for cat in raw["categories"].values():
        assert cat["label"] and cat["description"]
        assert set(cat["allowed_evidence"]) <= evidence
    for tag in raw["tags"]:
        assert set(tag) <= {"id", "label", "category", "definition", "instructions", "requires"}
        assert tag["id"].startswith(tag["category"] + "_") or tag["category"] == "depth"
        assert tag["category"] in raw["categories"]
        assert tag["definition"].strip().endswith(".")
    assert 40 <= len(raw["tags"]) <= 60


def test_draft_does_not_collide_with_v1_or_pilot(taxonomy):
    raw = draft()
    current = load_vocabulary(taxonomy)
    ids = {t.id for t in current.tags}
    labels = {t.label.casefold() for t in current.tags}
    new_ids = [t["id"] for t in raw["tags"]]
    new_labels = [t["label"].casefold() for t in raw["tags"]]
    assert len(set(new_ids)) == len(new_ids) and len(set(new_labels)) == len(new_labels)
    assert not ids & set(new_ids) and not labels & set(new_labels)
    assert not set(raw["categories"]) & {c.id for c in current.categories}


def test_depth_questions_have_a_real_parent(taxonomy):
    raw = draft()
    known = {t.id for t in load_vocabulary(taxonomy).tags} | {t["id"] for t in raw["tags"]}
    depth = [t for t in raw["tags"] if t["category"] == "depth"]
    assert depth and all(t.get("requires") in known for t in depth)
    assert all("requires" not in t for t in raw["tags"] if t["category"] != "depth")
    assert all(t["requires"] != t["id"] for t in depth)
