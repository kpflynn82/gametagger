from genometagger_v2.taxonomy import load_taxonomy


def test_taxonomy_has_expected_pilot_shape():
    taxonomy = load_taxonomy()
    assert taxonomy.version == "4.0-pilot"
    assert len(taxonomy.tags) == 25
    assert len(taxonomy.primary_genres) == 59
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
