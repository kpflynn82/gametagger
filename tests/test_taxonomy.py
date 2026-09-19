import pytest

from gametagger.taxonomy import load_taxonomy


def test_taxonomy_has_expected_pilot_shape():
    taxonomy = load_taxonomy()
    assert taxonomy.version == "4.1"
    assert len(taxonomy.tags) == 25
    assert len(taxonomy.primary_genres) == 100
    assert len(taxonomy.tags_by_id) == len(taxonomy.tags)
    assert set(taxonomy.tag_states) == {
        "present",
        "absent",
        "insufficient_evidence",
        "conflicting_evidence",
    }


def test_every_tag_has_evidence_policy():
    taxonomy = load_taxonomy()
    for tag in taxonomy.tags:
        assert tag.definition
        assert tag.evidence_class in {"visual", "temporal", "system", "documentary"}
        assert tag.preferred_evidence
        assert tag.allowed_evidence


def test_family_hierarchy_and_genre_fields():
    taxonomy = load_taxonomy()
    assert {f.display_name for f in taxonomy.genre_families} == {
        "Action",
        "Role-Playing",
        "Adventure & Narrative",
        "Strategy",
        "Simulation & Management",
        "Survival & Sandbox",
        "Horror",
        "Puzzle",
        "Racing",
        "Sports",
        "Card & Tabletop",
        "Party & Social",
        "Music & Rhythm",
        "Casual & Idle",
    }
    assert len(taxonomy.genres_by_id) == 100
    for family in taxonomy.genre_families:
        assert family.definition and family.eligible_genres
        for genre in family.genres:
            assert genre.id and genre.display_name and genre.definition
            assert genre.family == family.id
            assert genre.inclusion_criteria and genre.exclusion_notes and genre.example_games
            assert type(genre.primary_eligible) is bool
    for genome_trait in [
        "open_world",
        "crafting",
        "pixel_art",
        "co_op",
        "pvp",
        "f2p",
        "gacha",
        "dark_fantasy",
        "anime",
        "procedural_generation",
    ]:
        assert genome_trait not in taxonomy.genres_by_id


def test_taxonomy_endpoint_exposes_hierarchy():
    from gametagger.api.main import taxonomy

    result = taxonomy()
    assert result["version"] == "4.1"
    assert result["genre_family_count"] == 14
    assert result["primary_genre_count"] == 100
    assert result["genre_families"][0]["genres"][0]["primary_eligible"]


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_id",
        "duplicate_family",
        "wrong_parent",
        "missing_definition",
        "empty_criteria",
        "string_eligibility",
        "no_eligible_children",
        "reserved_id",
    ],
)
def test_invalid_taxonomy_rejected(tmp_path, mutation):
    import yaml

    from gametagger.taxonomy import default_taxonomy_path

    raw = yaml.safe_load(default_taxonomy_path().read_text())
    family = raw["genre_families"][0]
    genre = family["genres"][0]
    if mutation == "duplicate_id":
        family["genres"][1]["id"] = genre["id"]
    elif mutation == "duplicate_family":
        raw["genre_families"].append(family)
    elif mutation == "wrong_parent":
        genre["family"] = "role_playing"
    elif mutation == "missing_definition":
        del genre["definition"]
    elif mutation == "empty_criteria":
        genre["inclusion_criteria"] = []
    elif mutation == "string_eligibility":
        genre["primary_eligible"] = "true"
    elif mutation == "no_eligible_children":
        for item in family["genres"]:
            item["primary_eligible"] = False
    elif mutation == "reserved_id":
        genre["id"] = "insufficient_evidence"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_taxonomy(path)
