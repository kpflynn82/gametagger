"""Vocabulary v2: v1 plus 51 mobile tags, and follow-up questions asked only after their parent.

v2 extends v1 without changing a single v1 tag, so v1 results stay comparable. Follow-ups
("depth" tags) are held back until their parent is decided present (strong or likely); otherwise
they are reported as not evaluated, never absent. No network or paid calls.
"""

from __future__ import annotations

import pytest
import yaml
from test_genome import ScriptedGateway, dossier  # noqa: F401  (dossier is a fixture)

from gametagger.domain import EvidenceType
from gametagger.genome.engine import GenomeEngine, GenomePipeline
from gametagger.genome.vocabulary import default_vocabulary_path, load_vocabulary

V2 = default_vocabulary_path("v2")


def raw_v2():
    return yaml.safe_load(V2.read_text())


@pytest.fixture
def v1(taxonomy):
    return load_vocabulary(taxonomy)


@pytest.fixture
def v2(taxonomy):
    return load_vocabulary(taxonomy, V2)


def test_v2_file_is_complete_and_uses_known_evidence():
    raw = raw_v2()
    evidence = {e.value for e in EvidenceType}
    assert raw["version"] == "genome-tags-v2" and raw["extends"] == "genome_tags_v1.yaml"
    for cat in raw["categories"].values():
        assert cat["label"] and cat["description"]
        assert set(cat["allowed_evidence"]) <= evidence
    for tag in raw["tags"]:
        assert set(tag) <= {"id", "label", "category", "definition", "instructions", "requires"}
        assert tag["id"].startswith(tag["category"] + "_")
        assert tag["category"] in raw["categories"]
        assert tag["definition"].strip().endswith(".")
    assert len(raw["tags"]) == 51


def test_v2_keeps_every_v1_tag_unchanged_and_adds_four_categories(v1, v2):
    assert v2.version == "genome-tags-v2"
    assert v2.tags[: len(v1.tags)] == v1.tags  # same tags, same order, same definitions
    assert len(v2.tags) == len(v1.tags) + 51 == 240
    assert [c.id for c in v2.categories][: len(v1.categories)] == [c.id for c in v1.categories]
    assert [c.id for c in v2.categories][len(v1.categories) :] == [
        "meta",
        "liveops",
        "ads",
        "depth",
    ]
    assert len({t.label.casefold() for t in v2.tags}) == len(v2.tags)
    assert not v1.requires


def test_follow_ups_name_a_first_round_parent(v2):
    depth = [t.id for t in v2.tags if t.category == "depth"]
    assert sorted(v2.requires) == sorted(depth) and len(depth) == 12
    for child, parent in v2.requires.items():
        assert parent in v2.tags_by_id and parent not in v2.requires and parent != child


@pytest.mark.parametrize(
    "requires",
    ["engagement_nothing", "depth_pass_free_track", "depth_guild_help"],
)
def test_bad_parents_are_rejected(taxonomy, tmp_path, requires):
    raw = raw_v2()
    child = next(t for t in raw["tags"] if t["id"] == "depth_guild_help")
    child["requires"] = requires  # unknown, another follow-up, or itself
    (tmp_path / "genome_tags_v1.yaml").write_text(default_vocabulary_path().read_text())
    (tmp_path / "v2.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="requires"):
        load_vocabulary(taxonomy, tmp_path / "v2.yaml")


def test_extends_cannot_redefine_a_category_or_leave_the_folder(taxonomy, tmp_path):
    (tmp_path / "genome_tags_v1.yaml").write_text(default_vocabulary_path().read_text())
    raw = raw_v2()
    raw["categories"]["mechanic"] = raw["categories"]["meta"]
    (tmp_path / "v2.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="redefines"):
        load_vocabulary(taxonomy, tmp_path / "v2.yaml")
    raw = raw_v2() | {"extends": "../genome_tags_v1.yaml"}
    (tmp_path / "v2.yaml").write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="same folder"):
        load_vocabulary(taxonomy, tmp_path / "v2.yaml")


def test_unknown_vocabulary_name():
    with pytest.raises(ValueError, match="Unknown vocabulary"):
        default_vocabulary_path("v9")


# --------------------------------------------------------------------------- follow-up asking


def analyze(taxonomy, v2, dossier, choices):  # noqa: F811
    gateway = ScriptedGateway(choices)
    engine = GenomeEngine(taxonomy, v2, gateway, categories=["engagement", "ads", "depth"])
    return GenomePipeline(engine).analyze(dossier, offline=True), gateway


def test_follow_ups_wait_for_their_parent(taxonomy, v2, dossier):  # noqa: F811
    profile, gateway = analyze(
        taxonomy,
        v2,
        dossier,
        {
            "engagement_battle_pass": ("present", 0.95),  # strong
            "engagement_gacha": ("present", 0.6),  # likely: also unlocks its follow-ups
            "engagement_guilds": ("absent", 0.9),
        },
    )
    tags = {t.tag_id: t for t in profile.tags}
    sent = [r["questions"] for r in gateway.requests]
    depth_rounds = [i for i, qs in enumerate(sent) if any(q.startswith("depth_") for q in qs)]
    first_round = [i for i, qs in enumerate(sent) if any(q.startswith("engagement_") for q in qs)]
    assert len(depth_rounds) == 1 and max(first_round) < depth_rounds[0]  # parents first
    second = sent[depth_rounds[0]]
    assert sorted(second) == sorted(
        [
            "depth_pass_free_track",
            "depth_pass_upper_tier",
            "depth_gacha_rates_shown",
            "depth_gacha_pity",
            "depth_gacha_duplicates_convert",
        ]
    )
    assert tags["depth_pass_free_track"].tier == "unknown"  # asked, and Jev said not enough
    guild = tags["depth_guild_chat"]
    assert guild.tier == "not_evaluated" and guild.state is None  # never "absent"
    assert guild.error.code == "parent_not_present"
    assert "'Guilds or clans'" in guild.error.message and "absent" in guild.error.message
    energy = tags["depth_energy_as_lives"]
    assert energy.tier == "not_evaluated" and "insufficient evidence" in energy.error.message
    assert profile.provenance["followups_held"] == 12
    assert profile.provenance["followups_asked"] == 5
    # Only questions actually sent count as asked; held-back ones never asked are not failures.
    assert profile.provenance["questions_asked"] == sum(
        len(r["questions"]) for r in gateway.requests
    )


def test_no_follow_up_round_when_no_parent_is_present(taxonomy, v2, dossier):  # noqa: F811
    profile, gateway = analyze(taxonomy, v2, dossier, {})
    assert not any(q.startswith("depth_") for r in gateway.requests for q in r["questions"])
    depth = [t for t in profile.tags if t.category == "depth"]
    assert len(depth) == 12 and all(t.tier == "not_evaluated" for t in depth)
    assert profile.counts["absent"] == 0


def test_a_parent_outside_the_chosen_categories_leaves_its_follow_ups_unasked(
    taxonomy,
    v2,
    dossier,  # noqa: F811
):
    gateway = ScriptedGateway({"engagement_battle_pass": ("present", 0.99)})
    engine = GenomeEngine(taxonomy, v2, gateway, categories=["depth"])
    profile = GenomePipeline(engine).analyze(dossier, offline=True)
    free = next(t for t in profile.tags if t.tag_id == "depth_pass_free_track")
    assert free.tier == "not_evaluated" and "not asked in this run" in free.error.message


def test_estimate_counts_follow_ups_as_a_worst_case(taxonomy, v2, dossier):  # noqa: F811
    engine = GenomeEngine(taxonomy, v2, ScriptedGateway())
    prepared = GenomePipeline(engine).prepare(dossier, observe=False)
    plan = engine.plan(prepared.claims, prepared.evidence)
    assert len(plan.followups) == 12
    assert not any(k in plan.followups for batch in plan.batches for k in batch)
    rows = plan.estimate()["requests"]
    assert rows[-1]["questions"] == "12 follow-ups at most"
