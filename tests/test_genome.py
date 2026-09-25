"""Rich Genome mode: vocabulary, dossier, engine, sources and CLI. No network or paid calls."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from PIL import Image

from gametagger.domain import EvidenceType, TagState
from gametagger.genome import cli
from gametagger.genome.dossier import (
    MAX_CLAIM_CHARS,
    MAX_CLAIMS_PER_SOURCE,
    Dossier,
    ImageSource,
    TextSource,
    build_state,
    claims_from_source,
    source_evidence,
    split_claims,
)
from gametagger.genome.engine import (
    RICH_TAG_CRITERIA,
    GenomeEngine,
    GenomePipeline,
    TierThresholds,
    tier_for,
)
from gametagger.genome.report import render_profile
from gametagger.genome.sources import (
    SourceError,
    fetch_json,
    steam_source,
    wikipedia_source,
)
from gametagger.genome.vocabulary import (
    TEXT_EVIDENCE,
    default_vocabulary_path,
    load_vocabulary,
    rich_allowed_evidence,
)
from gametagger.observers.anthropic import AnthropicObserver
from gametagger.observers.mock import MockObserver

SAMPLE = Path(__file__).resolve().parents[1] / "fixtures" / "genome" / "hollow_orchard.dossier.json"


@pytest.fixture
def vocabulary(taxonomy):
    return load_vocabulary(taxonomy)


@pytest.fixture
def dossier():
    return Dossier.model_validate_json(SAMPLE.read_text())


class ScriptedGateway:
    """Deterministic stand-in for Jev with explicit per-question answers."""

    model = "scripted-jev"

    def __init__(self, choices=None, *, broken=(), fail_batches_with=None):
        self.choices = choices or {}
        self.broken = set(broken)
        self.fail_batches_with = fail_batches_with
        self.requests = []

    def answer(self, key, spec):
        options = list(spec.criteria)
        top, p = self.choices.get(key, ("insufficient_evidence", 0.9))
        if key == "genre_family" and key not in self.choices:
            top, p = "insufficient_evidence", 0.9
        rest = (1 - p) / (len(options) - 1)
        return {
            "type": "choice",
            "choice": top,
            "confidence": 0.8,
            "probabilities": {o: p if o == top else rest for o in options},
        }

    def run(self, *, state, specs):
        self.requests.append({"state": state, "questions": list(specs)})
        if self.fail_batches_with and self.fail_batches_with in specs:
            raise RuntimeError("simulated transport failure")
        answers = {}
        for key, spec in specs.items():
            if key in self.broken:
                answers[key] = {"type": "choice", "choice": "present", "probabilities": {}}
            else:
                answers[key] = self.answer(key, spec)
        return {
            "model": "jev-test-1",
            "usage": {"input_tokens": 10, "output_tokens": 1},
            "answers": answers,
        }


def engine_for(taxonomy, vocabulary, gateway, **kwargs):
    return GenomeEngine(taxonomy, vocabulary, gateway, **kwargs)


# --------------------------------------------------------------------------- vocabulary


def test_vocabulary_extends_frozen_pilot_without_changing_it(taxonomy, vocabulary):
    assert len(taxonomy.tags) == 25
    assert vocabulary.pilot_tags == taxonomy.tags
    assert len(vocabulary.extended_tags) >= 150
    assert len(vocabulary.tags_by_id) == len(vocabulary.tags)
    categories = set(vocabulary.categories_by_id)
    for tag in vocabulary.tags:
        assert tag.definition and tag.allowed_evidence and tag.category in categories
        assert tag.id not in taxonomy.genres_by_id
    assert vocabulary.version == "genome-tags-v1"


def test_category_selection_and_unknown_category(vocabulary):
    chosen = vocabulary.select(["monetization", "setting"])
    assert {t.category for t in chosen} == {"monetization", "setting"}
    order = [c.id for c in vocabulary.categories]
    assert [t.category for t in chosen] == sorted(
        (t.category for t in chosen), key=order.index
    )  # vocabulary display order, not argument order
    with pytest.raises(ValueError, match="Unknown Genome categories"):
        vocabulary.select(["nonsense"])


@pytest.mark.parametrize("mutation", ["pilot_duplicate", "bad_evidence", "bad_category", "extra"])
def test_invalid_vocabulary_rejected(taxonomy, tmp_path, mutation):
    raw = yaml.safe_load(default_vocabulary_path().read_text())
    tag = raw["tags"][0]
    if mutation == "pilot_duplicate":
        tag["id"] = "mechanic_crafting"
    elif mutation == "bad_evidence":
        tag["allowed_evidence"] = ["telepathy"]
    elif mutation == "bad_category":
        tag["category"] = "vibes"
    else:
        tag["genre"] = "rpg"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_vocabulary(taxonomy, path)


def test_rich_evidence_policy(vocabulary):
    by_id = vocabulary.tags_by_id
    # Frozen visual appearance tags stay media-only.
    assert rich_allowed_evidence(by_id["visual_realistic"], vocabulary) == (
        "gameplay_image",
        "gameplay_clip",
    )
    # Documented features may now be supported by attributed text.
    co_op = rich_allowed_evidence(by_id["engagement_co_op"], vocabulary)
    assert set(TEXT_EVIDENCE) <= set(co_op)
    assert set(by_id["engagement_co_op"].allowed_evidence) <= set(co_op)
    extended = by_id["monetization_free_to_play"]
    assert rich_allowed_evidence(extended, vocabulary) == extended.allowed_evidence


# --------------------------------------------------------------------------- dossier


def test_split_claims_strips_markup_and_bounds_length():
    text = "<p>Build a farm.</p><ul><li>Raise goats!</li><li>Fish</li></ul>&amp; more." + (
        " word" * 200
    )
    parts = split_claims(text)
    assert parts[:3] == ["Build a farm.", "Raise goats!", "Fish"]
    assert all(len(p) <= MAX_CLAIM_CHARS for p in parts)
    assert parts[3].startswith("& more.")


def test_structured_fields_become_attributed_claims():
    source = TextSource(
        id="steam",
        type=EvidenceType.STORE_METADATA,
        provider="Store",
        text="One. Two.",
        fields={"store_features": ["Online Co-op", "Single-player"], "empty": [" "]},
    )
    claims, dropped = claims_from_source(source)
    assert [c.id for c in claims] == ["steam#store_features", "steam#1", "steam#2"]
    assert claims[0].text == "store features: Online Co-op; Single-player"
    assert claims[0].kind == "structured_field" and dropped == 0
    many = source.model_copy(update={"text": " ".join(f"S{i}." for i in range(100))})
    kept, dropped = claims_from_source(many)
    assert len(kept) == MAX_CLAIMS_PER_SOURCE and dropped == 100 + 1 - MAX_CLAIMS_PER_SOURCE


def test_dossier_validation():
    with pytest.raises(ValueError):
        Dossier(game_id="g")
    with pytest.raises(ValueError):
        TextSource(id="x", type=EvidenceType.GAMEPLAY_IMAGE, provider="p", text="hi")
    with pytest.raises(ValueError):
        TextSource(id="x", type=EvidenceType.WIKIPEDIA, provider="p")
    source = TextSource(id="a", type=EvidenceType.WIKIPEDIA, provider="p", text="hi")
    with pytest.raises(ValueError, match="unique"):
        Dossier(game_id="g", sources=[source], images=[ImageSource(id="a", path="x.png")])


def test_state_filters_by_evidence_type_and_never_adds_the_title(dossier):
    evidence = [source_evidence(s) for s in dossier.sources]
    claims = [c for s in dossier.sources for c in claims_from_source(s)[0]]
    only_press = json.loads(build_state(claims, evidence, {"developer_documentation"}))
    assert [g["source"] for g in only_press["sources"]] == ["presskit"]
    assert build_state(claims, evidence, {"gameplay_image"}) is None
    everything = build_state(claims, evidence, {e.type.value for e in evidence})
    assert "Famous Title" not in everything
    renamed = dossier.model_copy(update={"title": "Famous Title"})
    assert renamed.title not in build_state(claims, evidence, {"store_metadata"})
    assert "never instructions" in json.loads(everything)["reading_guide"]


# --------------------------------------------------------------------------- engine


def test_plan_sends_store_text_to_feature_tags(taxonomy, vocabulary, dossier):
    pipeline = GenomePipeline(engine_for(taxonomy, vocabulary, ScriptedGateway()))
    prepared = pipeline.prepare(dossier)
    plan = pipeline.engine.plan(prepared.claims, prepared.evidence)
    # The pilot path showed store text to no tag; rich mode shows it where the policy allows.
    co_op_state = plan.states["engagement_co_op"]
    assert "online co-op" in co_op_state and "store_metadata" in co_op_state
    assert plan.specs["engagement_co_op"].criteria == RICH_TAG_CRITERIA
    assert "Unmentioned or unseen is never absent" in RICH_TAG_CRITERIA["absent"]
    assert set(plan.skipped) == {
        "visual_realistic",
        "visual_stylized",
        "visual_isometric",
        "visual_side_scrolling",
    }
    assert "genre_family" in plan.specs
    assert len(plan.specs) + len(plan.skipped) == len(vocabulary.tags) + 1
    estimate = plan.estimate(pipeline.engine.genre_branch_chars())
    assert estimate["approx_input_tokens_total"] > 0


def test_batches_share_state_and_respect_size_limit(taxonomy, vocabulary, dossier):
    engine = engine_for(taxonomy, vocabulary, ScriptedGateway(), max_questions_per_request=25)
    prepared = GenomePipeline(engine).prepare(dossier)
    plan = engine.plan(prepared.claims, prepared.evidence)
    assert all(len(batch) <= 25 for batch in plan.batches)
    assert all(len({plan.states[k] for k in batch}) == 1 for batch in plan.batches)
    assert sorted(k for batch in plan.batches for k in batch) == sorted(plan.specs)


def test_profile_preserves_raw_distributions_and_hierarchy(taxonomy, vocabulary, dossier):
    gateway = ScriptedGateway(
        {
            "mechanic_farming": ("present", 0.95),
            "tone_cozy": ("present", 0.6),
            "mechanic_permadeath": ("absent", 0.7),
            "monetization_free_to_play": ("conflicting_evidence", 0.5),
            "genre_family": ("simulation_management", 0.8),
            "genre:simulation_management": ("farm_simulation", 0.75),
        }
    )
    profile = GenomePipeline(engine_for(taxonomy, vocabulary, gateway)).analyze(
        dossier, offline=True
    )
    tags = {t.tag_id: t for t in profile.tags}
    assert tags["mechanic_farming"].tier == "strong"
    assert tags["tone_cozy"].tier == "likely"
    assert tags["mechanic_permadeath"].tier == "absent"
    assert tags["monetization_free_to_play"].tier == "conflicting"
    assert tags["setting_space"].tier == "unknown"
    assert tags["visual_realistic"].tier == "not_evaluated"
    expected = gateway.answer("mechanic_farming", SimpleNamespace(criteria=RICH_TAG_CRITERIA))
    assert tags["mechanic_farming"].probabilities == expected["probabilities"]
    assert all(not t.publishable for t in profile.tags)  # human review is still required
    assert profile.primary_genre.genre_id == "farm_simulation"
    assert profile.status == "complete"
    assert profile.counts["strong"] == 1 and sum(profile.counts.values()) == len(vocabulary.tags)
    assert profile.provenance["returned_decision_model"] == "jev-test-1"
    # 185 tags + genre family + one conditional branch per positive-probability family.
    branches = len(profile.genre.evaluated_families)
    assert profile.provenance["questions_asked"] == len(vocabulary.tags) - 4 + 1 + branches
    summary = render_profile(profile, vocabulary)
    assert "Primary genre: Farm Simulation" in summary
    assert "Farming (95%)" in summary and "not measured accuracy" in summary


def test_no_fallback_genre_when_evidence_is_insufficient(taxonomy, vocabulary, dossier):
    profile = GenomePipeline(engine_for(taxonomy, vocabulary, ScriptedGateway())).analyze(
        dossier, offline=True
    )
    assert profile.primary_genre is None and profile.secondary_genres == []
    assert profile.genre.global_genre_probabilities["insufficient_evidence"] > 0.5


def test_one_malformed_answer_is_retried_and_isolated(taxonomy, vocabulary, dossier):
    gateway = ScriptedGateway({"tone_cozy": ("present", 0.9)}, broken={"mechanic_farming"})
    profile = GenomePipeline(engine_for(taxonomy, vocabulary, gateway, max_attempts=2)).analyze(
        dossier, offline=True
    )
    tags = {t.tag_id: t for t in profile.tags}
    assert tags["mechanic_farming"].tier == "error"
    assert tags["mechanic_farming"].error.code == "option_set"
    assert tags["tone_cozy"].tier == "strong"
    assert profile.status == "partial"
    retries = [r for r in gateway.requests if r["questions"] == ["mechanic_farming"]]
    assert len(retries) == 1  # only the failed question is re-asked


def test_failed_request_does_not_erase_other_batches(taxonomy, vocabulary, dossier):
    gateway = ScriptedGateway({"tone_cozy": ("present", 0.9)}, fail_batches_with="mechanic_farming")
    engine = engine_for(taxonomy, vocabulary, gateway, max_questions_per_request=20)
    profile = GenomePipeline(engine).analyze(dossier, offline=True)
    tiers = {t.tag_id: t.tier for t in profile.tags}
    assert tiers["mechanic_farming"] == "error"
    assert tiers["tone_cozy"] == "strong"
    assert profile.status == "partial"


def test_tier_thresholds():
    probabilities = {"present": 0.84, "absent": 0.06, "insufficient_evidence": 0.1}
    assert tier_for(TagState.PRESENT, probabilities, TierThresholds()) == "likely"
    assert tier_for(TagState.PRESENT, probabilities, TierThresholds(0.8)) == "strong"


# --------------------------------------------------------------------------- screenshots


@pytest.fixture
def image_dossier(tmp_path, dossier):
    path = tmp_path / "shot.png"
    Image.new("RGB", (16, 16), "gray").save(path)
    return dossier.model_copy(update={"images": [ImageSource(id="shot1", path=str(path))]})


def test_taxonomy_word_quarantines_one_statement_not_the_run(taxonomy, vocabulary, image_dossier):
    observer = MockObserver(
        {
            "shot1": [
                "A small figure stands beside rows of green sprouts.",
                "The scene is drawn in pixel art.",
            ]
        }
    )
    gateway = ScriptedGateway()
    profile = GenomePipeline(engine_for(taxonomy, vocabulary, gateway), observer).analyze(
        image_dossier, offline=True
    )
    assert [q["text"] for q in profile.quarantined_observations] == [
        "The scene is drawn in pixel art."
    ]
    visual = [c for c in profile.claims if c.evidence_id == "shot1"]
    assert [c.text for c in visual] == ["A small figure stands beside rows of green sprouts."]
    assert not any("drawn in pixel art" in r["state"] for r in gateway.requests)
    tags = {t.tag_id: t for t in profile.tags}
    assert tags["visual_realistic"].tier == "unknown"  # now asked: a screenshot exists


def test_unobserved_screenshot_is_reported(taxonomy, vocabulary, image_dossier):
    profile = GenomePipeline(engine_for(taxonomy, vocabulary, ScriptedGateway())).analyze(
        image_dossier, offline=True
    )
    assert any("shot1" in w and "not observed" in w for w in profile.warnings)


def test_anthropic_observer_can_defer_boundary_to_caller(taxonomy, evidence):
    from gametagger.evidence import prepare_evidence

    evidence, data = prepare_evidence(evidence)
    client = Mock()
    client.messages.create.return_value = SimpleNamespace(
        model="vision",
        stop_reason="tool_use",
        content=[
            SimpleNamespace(
                type="tool_use",
                name="record_observations",
                input={
                    "observations": [
                        {"kind": "visual_fact", "text": "Pixel art trees.", "metadata_key": None}
                    ]
                },
            )
        ],
    )
    strict = AnthropicObserver(taxonomy, model="m", client=client)
    with pytest.raises(ValueError):
        strict.observe(evidence, image=data)
    lenient = AnthropicObserver(taxonomy, model="m", client=client, enforce_boundary=False)
    assert [o.text for o in lenient.observe(evidence, image=data)] == ["Pixel art trees."]


def _observer_reply(observations):
    client = Mock()
    client.messages.create.return_value = SimpleNamespace(
        model="vision",
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        content=[
            SimpleNamespace(
                type="tool_use", name="record_observations", input={"observations": observations}
            )
        ],
    )
    return client


def test_anthropic_observer_treats_an_omitted_metadata_key_as_null(taxonomy, evidence):
    from gametagger.evidence import prepare_evidence

    evidence, data = prepare_evidence(evidence)
    region = {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}
    client = _observer_reply([{"kind": "visual_text", "text": "PLAY", "image_region": region}])
    observer = AnthropicObserver(taxonomy, model="m", client=client, enforce_boundary=False)
    [observation] = observer.observe(evidence, image=data)
    assert observation.text == "PLAY" and observation.metadata_key is None


def test_malformed_statement_is_quarantined_alone_in_rich_mode(
    taxonomy, vocabulary, image_dossier, evidence
):
    from gametagger.evidence import prepare_evidence

    region = {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.1}
    client = _observer_reply(
        [
            {"kind": "visual_fact", "text": ""},
            {"kind": "visual_fact", "text": "A red car on a road.", "image_region": region},
            {"kind": "visual_text", "text": "START", "image_region": region},
        ]
    )
    observer = AnthropicObserver(taxonomy, model="m", client=client, enforce_boundary=False)
    profile = GenomePipeline(engine_for(taxonomy, vocabulary, ScriptedGateway()), observer).analyze(
        image_dossier, offline=False
    )
    kept = [c.text for c in profile.claims if c.evidence_id == "shot1"]
    assert len(kept) == 2
    assert any("red car" in k for k in kept) and any("START" in k for k in kept)
    assert [q["reason"] for q in profile.quarantined_observations] == [
        "Malformed statement (ValidationError)"
    ]
    # The website's strict mode still rejects the whole answer.
    item, data = prepare_evidence(evidence)
    with pytest.raises(ValueError):
        AnthropicObserver(taxonomy, model="m", client=client).observe(item, image=data)


def test_truncated_observer_answer_loses_the_screenshot_not_the_game(
    taxonomy, vocabulary, image_dossier
):
    client = _observer_reply([])
    client.messages.create.return_value.stop_reason = "max_tokens"
    observer = AnthropicObserver(taxonomy, model="m", client=client, enforce_boundary=False)
    profile = GenomePipeline(engine_for(taxonomy, vocabulary, ScriptedGateway()), observer).analyze(
        image_dossier, offline=False
    )
    assert any("shot1" in w and "broke the contract" in w for w in profile.warnings)
    assert profile.tags  # the game was still judged


def test_title_mismatch_warning(taxonomy, vocabulary, dossier):
    wrong = dossier.sources[0].model_copy(update={"reported_title": "Hollow Knight"})
    changed = dossier.model_copy(update={"sources": [wrong, *dossier.sources[1:]]})
    profile = GenomePipeline(engine_for(taxonomy, vocabulary, ScriptedGateway())).analyze(
        changed, offline=True
    )
    assert any("Hollow Knight" in w for w in profile.warnings)


# --------------------------------------------------------------------------- sources


STEAM = {
    "12345": {
        "success": True,
        "data": {
            "name": "Synthetic Game",
            "short_description": "Grow crops.",
            "about_the_game": "<p>Farm with friends.</p><br>Fish in rivers.",
            "genres": [{"id": "28", "description": "Simulation"}],
            "categories": [{"id": "38", "description": "Online Co-op"}],
            "is_free": False,
            "controller_support": "full",
            "platforms": {"windows": True, "mac": False},
            "content_descriptors": {"notes": None},
            "developers": ["Studio"],
        },
    }
}


def test_steam_source_parses_listing():
    urls = []

    def fetch(url):
        urls.append(url)
        return STEAM

    source = steam_source("12345", fetch=fetch).text
    assert urls[0].startswith("https://store.steampowered.com/api/appdetails?appids=12345")
    assert source.reported_title == "Synthetic Game"
    assert "Farm with friends." in source.text and "<p>" not in source.text
    assert source.fields["store_features"] == ["Online Co-op"]
    assert source.fields["pricing"] == ["Requires purchase"]
    assert source.fields["platforms"] == ["windows"]
    assert "content_notes" not in source.fields


@pytest.mark.parametrize("app, payload", [("abc", STEAM), ("999", {"999": {"success": False}})])
def test_steam_source_rejects_bad_ids_and_missing_listings(app, payload):
    with pytest.raises(SourceError):
        steam_source(app, fetch=lambda url: payload)


def test_steam_source_accepts_reply_keyed_by_another_id_only_when_appid_matches():
    entry = STEAM["12345"]
    data = {**entry["data"], "steam_appid": 12345}
    rekeyed = {"777": {**entry, "data": data}}
    assert steam_source("12345", fetch=lambda url: rekeyed).text.reported_title == "Synthetic Game"
    other = {"777": {**entry, "data": {**data, "steam_appid": 777}}}
    with pytest.raises(SourceError):
        steam_source("12345", fetch=lambda url: other)


def test_wikipedia_source_parses_intro_and_infobox():
    wikitext = (
        "{{Infobox video game\n| genre = [[Farm simulation|Farming sim]], [[Role-playing game]]"
        "<ref>x</ref>\n| modes = {{hlist|[[Single-player video game|Single-player]]"
        "|[[Multiplayer video game|multiplayer]]}}\n}}"
    )
    payload = {
        "query": {
            "pages": [
                {
                    "title": "Synthetic Game",
                    "extract": "Synthetic Game is a farming game.",
                    "revisions": [{"slots": {"main": {"content": wikitext}}}],
                }
            ]
        }
    }
    source = wikipedia_source("Synthetic Game", fetch=lambda url: payload).text
    assert source.type == EvidenceType.WIKIPEDIA
    assert source.fields["genres"] == ["Farming sim", "Role-playing game"]
    assert source.fields["modes"] == ["Single-player", "multiplayer"]
    assert source.uri == "https://en.wikipedia.org/wiki/Synthetic_Game"
    missing = {"query": {"pages": [{"title": "Nope", "missing": True}]}}
    with pytest.raises(SourceError):
        wikipedia_source("Nope", fetch=lambda url: missing)


@pytest.mark.parametrize(
    "url", ["http://store.steampowered.com/api", "https://example.com/a", "file:///etc/passwd"]
)
def test_fetch_only_contacts_fixed_https_hosts(url):
    with pytest.raises(SourceError):
        fetch_json(url)


# --------------------------------------------------------------------------- CLI


def test_cli_dry_run_makes_no_calls(capsys, monkeypatch):
    monkeypatch.setattr(cli, "TypeSafeGateway", Mock(side_effect=AssertionError("no live")))
    cli.main([str(SAMPLE)])
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "would be asked" in out
    cli.main([str(SAMPLE), "--format", "json", "--categories", "monetization"])
    plan = json.loads(capsys.readouterr().out)
    asked = {k for r in plan["requests"] for k in r["questions"]}
    assert asked == {"genre_family"} | {t for t in asked if t.startswith("monetization_")}


def test_cli_offline_reports_mock_run(capsys, tmp_path):
    output = tmp_path / "result.json"
    cli.main([str(SAMPLE), "--offline", "--output", str(output)])
    assert "OFFLINE MOCK" in capsys.readouterr().out
    result = json.loads(output.read_text())
    assert result["offline"] is True and result["primary_genre"] is None


def test_cli_live_requires_key_and_token_cap(monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        cli.main([str(SAMPLE), "--live"])
    monkeypatch.setenv("TYPESAFE_API_KEY", "placeholder-not-a-key")
    gateway = Mock()
    gateway.return_value.model = "jev-latest"
    monkeypatch.setattr(cli, "TypeSafeGateway", gateway)
    with pytest.raises(SystemExit):
        cli.main([str(SAMPLE), "--live", "--max-estimated-tokens", "100"])
    assert "exceeds" in capsys.readouterr().err
    gateway.return_value.run.assert_not_called()
    gateway.return_value.run_pinned.assert_not_called()


def test_cli_reports_bad_dossier_clearly(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"game_id": "g", "sources": []}')
    with pytest.raises(SystemExit):
        cli.main([str(bad)])
    assert "Could not build the dossier" in capsys.readouterr().err
