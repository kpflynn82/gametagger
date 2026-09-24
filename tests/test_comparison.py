"""Offline tests for the Jev-versus-previous-method comparison tools. No network, no paid calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from gametagger.comparison import answer_key, charts, identity
from gametagger.comparison.budget import (
    BudgetExceeded,
    Ledger,
    Meter,
    MeteredAnthropic,
    cost_usd,
    worst_case_claude,
)
from gametagger.comparison.crosswalk import load_crosswalks
from gametagger.comparison.dossiers import dossier_path
from gametagger.comparison.report import render_report, render_social_card, social_post
from gametagger.comparison.review import build_review
from gametagger.comparison.runner import Runner, interleaved
from gametagger.comparison.scoring import load_results, normalize, score
from gametagger.config import anthropic_api_key
from gametagger.decisions import legacy
from gametagger.genome.cli import save_dossier
from gametagger.genome.dossier import Dossier, ImageSource, TextSource
from gametagger.genome.net import SourceError
from gametagger.genome.sources import google_play_source
from gametagger.genome.vocabulary import load_vocabulary
from gametagger.taxonomy import load_taxonomy

TAXONOMY = load_taxonomy()
VOCABULARY = load_vocabulary(TAXONOMY)
CROSSWALKS = load_crosswalks(TAXONOMY, VOCABULARY)
NAMES = {g.id: g.display_name for g in TAXONOMY.genres_by_id.values()}

# --------------------------------------------------------------------------- charts


def test_steam_chart_parsing_orders_by_rank_and_dates_the_rollup():
    date, ranks = charts.parse_steam_chart(
        {
            "response": {
                "rollup_date": 1790121600,
                "ranks": [
                    {"rank": 2, "appid": 570, "peak_in_game": 5},
                    {"rank": 1, "appid": 730, "peak_in_game": 9},
                ],
            }
        }
    )
    assert date == "2026-09-23"
    assert [r["appid"] for r in ranks] == [730, 570]
    with pytest.raises(SourceError):
        charts.parse_steam_chart({"response": {"ranks": []}})


APPBRAIN_ROW = """<tr><td class="ranking-rank">{rank}</td><td class="ranking-app-cell">
<a href="/app/{slug}/{package}">{title}</a><div class="ranking-app-cell-creator">
by <a href="/dev/x/">{dev}</a></div></td></tr>"""


def appbrain_page(rows):
    body = "".join(APPBRAIN_ROW.format(**r) for r in rows)
    return f"<div>Last updated: <time>September 24, 2026</time></div><table>{body}</table>"


def test_appbrain_parsing_reads_rank_package_title_and_developer():
    date, rows = charts.parse_appbrain(
        appbrain_page(
            [
                {
                    "rank": 1,
                    "slug": "a",
                    "package": "com.a.game",
                    "title": "A &amp; B",
                    "dev": "Dev",
                },
                {"rank": 2, "slug": "b", "package": "com.b.game", "title": "B", "dev": "Other"},
            ]
        )
    )
    assert date == "2026-09-24"
    assert rows[0] == {"rank": 1, "package": "com.a.game", "title": "A & B", "developer": "Dev"}
    with pytest.raises(SourceError):
        charts.parse_appbrain("<html></html>")


def test_cohort_skips_software_editions_and_cross_list_duplicates():
    chart = {
        "response": {
            "rollup_date": 1790121600,
            "ranks": [{"rank": n, "appid": n} for n in range(1, 7)],
        }
    }
    apps = {
        1: {"name": "Shooter", "type": "game", "genres": [{"id": "1"}]},
        2: {"name": "Wallpaper Tool", "type": "game", "genres": [{"id": "57"}, {"id": "4"}]},
        3: {"name": "Server Hub", "type": "advertising", "genres": []},
        4: {"name": "Big City Legacy", "type": "game", "genres": []},
        5: {"name": "Big City Enhanced", "type": "game", "genres": []},
        6: {"name": "Match Mania", "type": "game", "genres": []},
    }

    def fetch(url):
        if "GetMostPlayedGames" in url:
            return chart
        appid = int(url.split("appids=")[1].split("&")[0])
        return {str(appid): {"success": True, "data": apps[appid]}}

    page = appbrain_page(
        [
            {"rank": 1, "slug": "m", "package": "com.m.mania", "title": "Match Mania", "dev": "D"},
            {"rank": 2, "slug": "p", "package": "com.p.puzzle", "title": "Puzzle", "dev": "D"},
        ]
    )
    cohort = charts.build_cohort(
        steam_count=3, mobile_count=1, fetch=fetch, fetch_page=lambda url: page
    )
    assert [g["title"] for g in cohort["games"]] == [
        "Shooter",
        "Big City Legacy",
        "Match Mania",
        "Puzzle",
    ]
    reasons = {s.get("title"): s["reason"] for s in cohort["skipped"]}
    assert "software genres: Utilities" in reasons["Wallpaper Tool"]
    assert "advertising" in reasons["Server Hub"]
    assert "another edition" in reasons["Big City Enhanced"]
    assert "same game as steam-6" in reasons["Match Mania"]


# --------------------------------------------------------------------------- identity


def wikidata_fetch(items, entities):
    def fetch(url):
        if "list=search" in url:
            for needle, qids in items.items():
                if needle in url:
                    return {"query": {"search": [{"title": q} for q in qids]}}
            return {"query": {"search": []}}
        qid = url.rsplit("/", 1)[1].removesuffix(".json")
        return {"entities": {qid: entities[qid]}}

    return fetch


def entity(label, enwiki=None, **claims):
    props = {"steam_app": "P1733", "google_play": "P3418", "app_store": "P3861"}
    return {
        "labels": {"en": {"value": label}},
        "sitelinks": {"enwiki": {"title": enwiki}} if enwiki else {},
        "claims": {
            props[k]: [{"rank": "normal", "mainsnak": {"datavalue": {"value": v}}} for v in vs]
            for k, vs in claims.items()
        },
    }


def test_identity_links_exact_store_ids_and_refuses_to_guess():
    game = {"game_id": "steam-730", "list": "steam", "title": "Counter-Strike 2"}
    game["ids"] = {"steam_app": "730"}
    fetch = wikidata_fetch(
        {"P1733%3D730": ["Q1", "Q2"]},
        {
            "Q1": entity("Counter-Strike: Global Offensive", "CS:GO"),
            "Q2": entity("Counter-Strike 2", "Counter-Strike 2"),
        },
    )
    found = identity.resolve_wikidata(game, fetch=fetch)
    assert found["status"] == "matched" and found["wikipedia"] == "Counter-Strike 2"
    game["title"] = "Something else"
    assert identity.resolve_wikidata(game, fetch=fetch)["status"] == "ambiguous"


def test_mobile_identity_uses_wikidata_then_strict_app_store_search():
    cohort = {
        "games": [
            {
                "game_id": "gp-a",
                "list": "mobile",
                "title": "Alpha",
                "developers": ["Studio"],
                "ids": {"google_play": "com.a"},
            },
            {
                "game_id": "gp-b",
                "list": "mobile",
                "title": "Beta Quest",
                "developers": ["Beta Co"],
                "ids": {"google_play": "com.b"},
            },
        ]
    }
    wiki = wikidata_fetch(
        {"P3418%3Dcom.a": ["Q9"]},
        {"Q9": entity("Alpha", "Alpha (video game)", app_store=["111"], steam_app=["222"])},
    )

    def fetch(url):
        if "itunes.apple.com/search" in url:
            return {
                "results": [
                    {"trackName": "Beta Quest", "artistName": "Beta Co", "trackId": 333},
                    {"trackName": "Beta Quest", "artistName": "Copycat Ltd", "trackId": 444},
                ]
            }
        return wiki(url)

    identity.resolve_cohort(cohort, fetch=fetch, log=lambda m: None, sleep=lambda s: None)
    a, b = cohort["games"]
    assert a["ids"] == {
        "google_play": "com.a",
        "wikipedia": "Alpha (video game)",
        "app_store": "111",
        "steam_app": "222",
    }
    assert b["ids"]["app_store"] == "333"
    assert b["identity"]["app_store_search"]["needs_owner_review"] is True


def test_polite_fetch_retries_rate_limits_only():
    calls = []

    def flaky(url):
        calls.append(url)
        if len(calls) < 3:
            raise SourceError("www.wikidata.org returned HTTP 429")
        return {"ok": True}

    assert identity.polite(flaky, sleep=lambda s: None)("u") == {"ok": True}
    with pytest.raises(SourceError, match="404"):
        identity.polite(lambda u: (_ for _ in ()).throw(SourceError("HTTP 404")))("u")


# --------------------------------------------------------------------------- answer key


def test_steam_user_tags_are_parsed_with_votes_and_rank():
    page = (
        'x InitAppTagModal( 413150,\n\t[{"tagid":1,"name":"Farming Sim","count":90},'
        '{"tagid":2,"name":"Pixel Graphics","count":95}],\n "x", 1);'
    )
    tags = answer_key.parse_user_tags(page)
    assert tags == [
        {"name": "Pixel Graphics", "votes": 95, "rank": 1},
        {"name": "Farming Sim", "votes": 90, "rank": 2},
    ]
    assert answer_key.parse_user_tags("<html>age check</html>") == []


def test_answer_key_only_covers_games_with_a_steam_listing():
    cohort = {
        "games": [
            {"game_id": "steam-1", "ids": {"steam_app": "1"}},
            {"game_id": "gp-x", "ids": {"google_play": "com.x"}},
        ]
    }
    seen = []

    def fetch_page(url, headers=None):
        seen.append(headers)
        return 'InitAppTagModal( 1, [{"name":"Open World","count":3}], 1'

    key = answer_key.build_answer_key(
        cohort, fetch_page=fetch_page, sleep=lambda s: None, log=lambda m: None
    )
    assert list(key["games"]) == ["steam-1"]
    assert "birthtime" in seen[0]["Cookie"]


# --------------------------------------------------------------------------- Google Play


PLAY_PAGE = """<script type="application/ld+json">{"@type":"SoftwareApplication","name":"Tile &amp; Tale",
"applicationCategory":"GAME_ROLE_PLAYING","contentRating":"Teen","author":{"name":"Studio"},
"offers":[{"price":"0"}]}</script>
<div data-g-id="description" inert>Build a town.<br>Play with friends online.</div>
<span class="UIuSk">In-app purchases</span>
<div itemprop="genre"><div class="x"></div><span class="y">Role playing</span></div>
<img src="https://play-lh.googleusercontent.com/abc=w526-h296" srcset="https://play-lh.googleusercontent.com/abc=w1052-h592 2x" alt="Screenshot image">
<img src="https://play-lh.googleusercontent.com/abc=w526-h296" alt="Screenshot image">
<img src="https://evil.example.com/x.png" alt="Screenshot image">
<video><source src="https://play-games.googleusercontent.com/vp/mp4/1280x720/vid.mp4" type="video/mp4"></video>
<button data-trailer-url="https://www.youtube.com/embed/abcdefghijk?vq=large"></button>"""  # noqa: E501


def test_google_play_listing_supplies_text_fields_media_and_trailer():
    fetched = google_play_source("com.studio.tile", fetch_page=lambda url: PLAY_PAGE)
    text = fetched.text
    assert text.id == "googleplay" and text.reported_title == "Tile & Tale"
    assert text.text == "Build a town.\nPlay with friends online."
    assert text.fields["store_genres"] == ["Role playing"]
    assert text.fields["store_features"] == ["In-app purchases"]
    assert text.fields["pricing"] == ["Free"] and text.fields["developers"] == ["Studio"]
    kinds = [(m.kind, m.url) for m in fetched.media]
    assert kinds == [
        ("image", "https://play-lh.googleusercontent.com/abc=w1052-h592"),
        ("video", "https://play-games.googleusercontent.com/vp/mp4/1280x720/vid.mp4"),
    ]
    assert fetched.references[1].uri == "https://www.youtube.com/watch?v=abcdefghijk"
    ids = {r.id for r in fetched.references} | {"googleplay-shot1", "googleplay-trailer"}
    assert len(ids) == 4  # reference IDs never collide with downloaded media IDs
    with pytest.raises(SourceError):
        google_play_source("com.missing", fetch_page=lambda url: "<html></html>")


# --------------------------------------------------------------------------- legacy adapter


def test_legacy_prompt_genres_and_categories_are_verbatim_copies():
    assert len(legacy.PRIMARY_GENRES_LIST) == 59
    assert sum(len(v) for v in legacy.VGMS_CATEGORIES.values()) == 91
    assert legacy.ANALYSIS_PROMPT.startswith(
        "Analyze this game and classify it using VGMS (Video Game Metadata Schema)."
    )
    assert legacy.QUALITY_SETTINGS["standard"]["model"] == "claude-haiku-4-5-20251001"
    assert legacy.QUALITY_SETTINGS["deep"]["model"] == "claude-opus-4-8"


def test_legacy_parser_and_postprocess_match_the_original_rules():
    parsed = legacy.parse_response(
        'Sure! {"gameplay_tags": {"gameplay_rpg": true}, "primary_genre": "Deckbuilder RPG",'
        ' "secondary_genres": ["JRPG", "JRPG", "Nope", "MOBA", "Sandbox"], "confidence": "sure"}'
    )
    assert parsed["gameplay_rpg"] is True
    result, audit = legacy.postprocess(parsed)
    # "Deckbuilder RPG" contains no listed genre and no listed genre contains it -> fallback.
    assert result["primary_genre"] == "Action RPG"
    assert audit["primary_genre_resolution"] == "forced_fallback"
    assert result["secondary_genres"] == ["JRPG", "MOBA"]
    assert result["confidence"] == "medium"
    matched, audit = legacy.postprocess({"primary_genre": "roguelike", "x": True})
    assert matched["primary_genre"] == "Roguelike"
    assert audit["primary_genre_resolution"] == "matched_case_or_substring"
    empty, audit = legacy.postprocess({})
    assert empty["confidence"] == "low" and audit["primary_genre_resolution"] == "missing"
    assert legacy.parse_response("no json here") == {"error": "Could not parse response"}
    assert legacy.boolean_tags({"a": True, "b": False, "confidence": "high", "c": "yes"}) == {
        "a": True,
        "b": False,
    }


def write_png(path: Path, size=(1200, 700)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (30, 90, 160)).save(path)
    return path


def sample_dossier(tmp_path: Path, game_id="steam-1", title="Hollow Orchard") -> Dossier:
    shots = [write_png(tmp_path / "m" / f"s{i}.png") for i in range(3)]
    return Dossier(
        game_id=game_id,
        title=title,
        sources=[
            TextSource(
                id="steam",
                type="store_metadata",
                provider="Steam store listing",
                reported_title=title,
                text="Grow a haunted orchard.\nLong about text " + "x" * 2000,
                fields={"store_genres": ["Indie", "RPG"], "store_features": ["Online Co-op"]},
            ),
            TextSource(
                id="wikipedia",
                type="wikipedia",
                provider="Wikipedia",
                reported_title=title,
                text="W" * 3000,
                fields={"genres": ["Farming"], "modes": ["Single-player"]},
            ),
        ],
        images=[
            ImageSource(
                id=f"steam-shot{i}",
                path=str(p),
                provider="Steam store screenshot",
                role="store_screenshot",
            )
            for i, p in enumerate(shots, start=1)
        ],
    )


def test_legacy_input_follows_the_original_layout(tmp_path):
    built = legacy.build_input(sample_dossier(tmp_path), game_name="Hollow Orchard")
    assert "GAME: Hollow Orchard" in built.prompt
    assert "STEAM STORE:\n  Title: Hollow Orchard\n  Genres: Indie, RPG" in built.prompt
    assert "  Description: Grow a haunted orchard.\n" in built.prompt  # short description only
    assert "  Description: " + "W" * 1000 + "\n" in built.prompt  # Wikipedia capped at 1000
    assert built.sections == ["steam", "wikipedia"]
    assert built.image_ids == ["steam-shot1", "steam-shot2"]  # first two per store
    with Image.open(__import__("io").BytesIO(built.images[0])) as image:
        assert image.format == "JPEG" and image.width == 600


# --------------------------------------------------------------------------- budget


def test_costs_use_list_prices_and_the_cap_refuses_before_spending(tmp_path):
    assert (
        cost_usd("claude-haiku-4-5-20251001", {"input_tokens": 1_000_000, "output_tokens": 0})
        == 1.0
    )
    assert cost_usd(
        "jev-1.13.0", {"input_tokens": 1_000_000, "output_tokens": 999}
    ) == pytest.approx(0.042)
    assert cost_usd("unknown-model", {"input_tokens": 5}) is None
    worst = worst_case_claude(
        {
            "model": "claude-opus-4-8",
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": "hi"}],
        }
    )
    assert worst == pytest.approx(4000 * 25 / 1e6, rel=0.01)
    ledger = Ledger(tmp_path / "ledger.jsonl", cap_usd=0.05)
    ledger.reserve(0.04)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(0.02)
    with pytest.raises(ValueError):
        Ledger(tmp_path / "other.jsonl", cap_usd=0)


def test_ledger_persists_and_unpriced_calls_count_at_worst_case(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = Ledger(path, cap_usd=1.0)
    ledger.settle(ledger.reserve(0.2), {"cost_usd": 0.05})
    ledger.settle(ledger.reserve(0.3), {"cost_usd": None})
    assert ledger.spent == pytest.approx(0.35)
    again = Ledger(path, cap_usd=1.0)
    assert again.spent == pytest.approx(0.05) and again.unpriced == 1


def test_anthropic_key_may_use_the_second_name(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GAMETAGGER_ANTHROPIC_API_KEY", "test-value")
    assert anthropic_api_key() == "test-value"
    monkeypatch.delenv("GAMETAGGER_ANTHROPIC_API_KEY")
    assert anthropic_api_key() is None


# --------------------------------------------------------------------------- end to end (fakes)


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest(), 16)


class FakeClaude:
    """Returns well-formed Observer, window and old-method responses; never contacts anyone."""

    def __init__(self):
        self.messages = self
        self.requests = []

    def with_options(self, **options):
        return self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        usage = SimpleNamespace(input_tokens=1200, output_tokens=300)
        tool = (kwargs.get("tools") or [{}])[0].get("name")
        if tool == "record_observations":
            block = SimpleNamespace(
                type="tool_use",
                name=tool,
                input={
                    "observations": [
                        {
                            "kind": "visual_fact",
                            "text": "Rows of trees under a purple sky.",
                            "metadata_key": None,
                        }
                    ]
                },
            )
            return SimpleNamespace(
                model=kwargs["model"], stop_reason="tool_use", content=[block], usage=usage
            )
        if tool == "record_window_observations":
            block = SimpleNamespace(
                type="tool_use", name=tool, input={"context": "gameplay", "observations": []}
            )
            return SimpleNamespace(
                model=kwargs["model"], stop_reason="tool_use", content=[block], usage=usage
            )
        prompt = kwargs["messages"][0]["content"][0]["text"]
        tags = {k: (_h(prompt, k) % 3 == 0) for k in list(CROSSWALKS.legacy_tags)[:40]}
        answer = {
            **tags,
            "primary_genre": "Farm Simulation",
            "confidence": "high",
            "secondary_genres": [],
        }
        text = SimpleNamespace(type="text", text=json.dumps(answer))
        return SimpleNamespace(
            model=kwargs["model"], stop_reason="end_turn", content=[text], usage=usage
        )


class FakeTypeSafe:
    def system_one(self, *, state, questions, model, response_model, retry):
        answers = {}
        for key, question in questions.items():
            options = list(question.criteria)
            pick = (
                options[_h(state, key) % len(options)]
                if "present" not in options
                else ("present" if _h(key) % 3 == 0 else "insufficient_evidence")
            )
            rest = (1 - 0.9) / (len(options) - 1)
            probs = {o: (0.9 if o == pick else rest) for o in options}
            answers[key] = {
                "type": "choice",
                "choice": pick,
                "confidence": 0.8,
                "probabilities": probs,
            }
        return response_model.model_validate(
            {
                "model": "jev-1.13.0",
                "answers": answers,
                "usage": {"input_tokens": 5000, "output_tokens": 40},
            }
        )


@pytest.fixture
def fake_run(tmp_path, monkeypatch):
    import gametagger.comparison.runner as runner_module

    original = runner_module.metered_jev_gateway

    def with_fake_client(meter, model):
        gateway = original(meter, model)
        gateway._client = FakeTypeSafe()
        return gateway

    monkeypatch.setattr(runner_module, "metered_jev_gateway", with_fake_client)
    cohort = {
        "charts": {"steam": {"chart_date": "2026-09-23"}, "mobile": {"chart_date": "2026-09-24"}},
        "games": [
            {
                "game_id": "steam-1",
                "list": "steam",
                "rank": 1,
                "title": "Hollow Orchard",
                "ids": {"steam_app": "1"},
            },
            {
                "game_id": "gp-com.x",
                "list": "mobile",
                "rank": 1,
                "title": "Orchard Match",
                "ids": {"google_play": "com.x"},
            },
        ],
    }
    for game in cohort["games"]:
        path = dossier_path(tmp_path, game["game_id"])
        path.parent.mkdir(parents=True)
        save_dossier(sample_dossier(path.parent, game["game_id"], game["title"]), path)
        path.with_name("gather.json").write_text(
            json.dumps(
                {
                    "sources": ["steam"],
                    "images": 3,
                    "videos": 0,
                    "gather_timings": {"total_ms": 1500},
                }
            )
        )
    runner = Runner(
        tmp_path, Ledger(tmp_path / "ledger.jsonl", 40.0), anthropic_client=FakeClaude()
    )
    summary = runner.run(
        cohort["games"], ["rich", "legacy-standard", "legacy-deep"], workers=2, log=lambda m: None
    )
    return tmp_path, cohort, runner, summary


def test_fake_end_to_end_run_records_timing_tokens_cost_and_resumes(fake_run):
    workdir, cohort, runner, summary = fake_run
    assert summary["completed"] == 6 and summary["failed"] == 0 and not summary["stopped_by_budget"]
    rich = json.loads(runner.result_path("steam-1", "rich").read_text())
    assert rich["status"] in {"complete", "partial"}
    assert (
        rich["usage"]["typesafe"]["requests"] >= 4 and rich["usage"]["anthropic"]["requests"] == 3
    )
    assert rich["cost_usd"]["typesafe"] > 0 and rich["cost_usd"]["anthropic"] > 0
    assert set(rich["stage_ms"]) == {"observe", "decide", "total"}
    assert rich["evidence_gather_ms"] == 1500
    old = json.loads(runner.result_path("steam-1", "legacy-deep").read_text())
    assert old["requested_model"] == "claude-opus-4-8" and old["primary_genre"] == "Farm Simulation"
    assert old["images_sent"] == 2 and old["usage"]["anthropic"]["requests"] == 1
    # Raw responses are kept apart from the compact, shareable records.
    assert runner.raw_path("steam-1", "legacy-deep").exists()
    assert "claims" not in rich
    spent = runner.ledger.spent
    again = runner.run(cohort["games"], ["rich"], log=lambda m: None)
    assert again["completed"] == 0 and runner.ledger.spent == spent  # resumed, nothing re-bought


def test_budget_stop_is_clean_and_reported(tmp_path):
    workdir = tmp_path
    dossier = sample_dossier(tmp_path / "d")
    path = dossier_path(tmp_path, "steam-1")
    path.parent.mkdir(parents=True)
    save_dossier(dossier, path)
    path.with_name("gather.json").write_text(json.dumps({"gather_timings": {"total_ms": 1}}))
    runner = Runner(
        workdir, Ledger(tmp_path / "ledger.jsonl", 0.001), anthropic_client=FakeClaude()
    )
    game = {"game_id": "steam-1", "list": "steam", "title": "Hollow Orchard", "ids": {}}
    summary = runner.run([game], ["legacy-deep"], log=lambda m: None)
    assert summary["stopped_by_budget"] and "cap" in summary["stopped_by_budget"]
    assert not runner.result_path("steam-1", "legacy-deep").exists()


def test_no_credit_stops_the_run_instead_of_failing_every_game(tmp_path):
    class Broke:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("Your credit balance is too low to access the Anthropic API.")

        def with_options(self, **options):
            return self

    path = dossier_path(tmp_path, "steam-1")
    path.parent.mkdir(parents=True)
    save_dossier(sample_dossier(tmp_path / "d"), path)
    path.with_name("gather.json").write_text(json.dumps({"gather_timings": {"total_ms": 1}}))
    runner = Runner(tmp_path, Ledger(tmp_path / "ledger.jsonl", 40.0), anthropic_client=Broke())
    game = {"game_id": "steam-1", "list": "steam", "title": "Hollow Orchard", "ids": {}}
    summary = runner.run([game], ["legacy-standard", "rich"], workers=1, log=lambda m: None)
    assert summary["stopped_by_budget"] and "credit" in summary["stopped_by_budget"]
    assert summary["failed"] == 0
    assert not runner.result_path("steam-1", "legacy-standard").exists()


def test_scoring_review_and_report_from_a_fake_run(fake_run):
    workdir, cohort, runner, _ = fake_run
    results = load_results(workdir, cohort, ["rich", "legacy-standard", "legacy-deep"])
    key = {
        "games": {
            "steam-1": {
                "status": "ok",
                "tags": [
                    {"name": "Open World", "votes": 9, "rank": 1},
                    {"name": "Farming Sim", "votes": 8, "rank": 2},
                    {"name": "Indie", "votes": 7, "rank": 3},
                    {"name": "Crafting", "votes": 1, "rank": 25},
                ],
            }
        }
    }
    scores = score(cohort, key, results, CROSSWALKS, NAMES)
    assert scores["sample"]["games_compared"] == 2
    assert scores["sample"]["games_with_steam_answer_key"] == 1
    rich = scores["arms"]["rich"]["steam_tags"]["all_mapped"]
    # Open World -> world_open_world; Farming Sim -> mechanic_farming. Rank 25 is ignored.
    assert rich["attributes"] == 2
    old = normalize(results["legacy-deep"]["steam-1"], CROSSWALKS, NAMES)
    assert old.genre_relation == "exact" and old.genre_v4 == ["farm_simulation"]
    assert scores["arms"]["legacy-deep"]["genre_vs_steam_tags"]["consistent_genre"] == 1.0
    assert "legacy-deep" in scores["recall_difference_vs_rich"]

    rows, review_key = build_review(
        cohort, results, CROSSWALKS, VOCABULARY, TAXONOMY, games=2, tags_per_game=5
    )
    assert rows and all(r["your_verdict"] == "" for r in rows)
    assert all("arms" not in r and "rich" not in json.dumps(r) for r in rows)  # blinded
    assert set(review_key["items"]) == {r["item"] for r in rows}

    page = render_report(scores, illustrative=True)
    assert "Illustrative / UI test data" in page and "Sample: 2 games" in page
    assert "<title>Jev vs Old Tagger</title>" in page
    card = render_social_card(scores, illustrative=True)
    assert "Illustrative / UI test data" in card and "2026-09-23" in card
    assert "Steam players' top tags" in social_post(scores)


def test_interleaved_order_alternates_lists():
    cohort = {
        "games": [{"game_id": f"s{i}", "list": "steam"} for i in range(3)]
        + [{"game_id": "m0", "list": "mobile"}]
    }
    assert [g["game_id"] for g in interleaved(cohort)] == ["s0", "m0", "s1", "s2"]


def test_crosswalks_cover_every_old_genre_and_tag():
    assert set(legacy.PRIMARY_GENRES_LIST) == set(CROSSWALKS.legacy_genres)
    keys = {
        (t if c == "features" else f"{c}_{t}")
        for c, ts in legacy.VGMS_CATEGORIES.items()
        for t in ts
    }
    assert keys == set(CROSSWALKS.legacy_tags)
    assert CROSSWALKS.legacy_genre_targets("Sports") == {
        "relation": "family",
        "v4": [],
        "families": ["sports"],
    }
    assert "draft" in CROSSWALKS.versions["steam_tags"]


def test_metered_client_books_usage_to_the_ledger(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl", 1.0)
    meter = Meter(ledger, "legacy-standard", "g", [])
    client = MeteredAnthropic(FakeClaude(), meter)
    client.with_options(timeout=5).messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
    )
    assert meter.calls[0]["usage"]["input_tokens"] == 1200
    assert ledger.spent == pytest.approx((1200 * 1 + 300 * 5) / 1e6)


def test_budget_stop_passes_through_jevs_question_executor(tmp_path, monkeypatch):
    import gametagger.comparison.runner as runner_module

    original = runner_module.metered_jev_gateway

    def with_fake_client(meter, model):
        gateway = original(meter, model)
        gateway._client = FakeTypeSafe()
        return gateway

    monkeypatch.setattr(runner_module, "metered_jev_gateway", with_fake_client)
    text_only = sample_dossier(tmp_path / "d").model_copy(update={"images": []})
    path = dossier_path(tmp_path, "steam-1")
    path.parent.mkdir(parents=True)
    save_dossier(text_only, path)
    path.with_name("gather.json").write_text(json.dumps({"gather_timings": {"total_ms": 1}}))
    runner = Runner(
        tmp_path, Ledger(tmp_path / "ledger.jsonl", 0.0001), anthropic_client=FakeClaude()
    )
    game = {"game_id": "steam-1", "list": "steam", "title": "Hollow Orchard", "ids": {}}
    summary = runner.run([game], ["rich"], log=lambda m: None)
    assert summary["stopped_by_budget"]
    assert not runner.result_path("steam-1", "rich").exists()  # no half-run booked as a result


def test_identity_reads_language_neutral_labels_and_ignores_edition_words():
    fetch = wikidata_fetch(
        {"P1733%3D271590": ["Q1", "Q2"], "P1733%3D2357570": ["Q3", "Q4"]},
        {
            "Q1": {**entity("", "Grand Theft Auto V"), "labels": {"mul": {"value": "GTA V"}}},
            "Q2": entity("Grand Theft Auto Online", "Grand Theft Auto Online"),
            "Q3": entity("", "Overwatch (2023 video game)"),
            "Q4": entity("Overwatch 2: Rose Gold Mercy Bundle"),
        },
    )
    gta = {"game_id": "steam-271590", "list": "steam", "title": "Grand Theft Auto V Legacy"}
    gta["ids"] = {"steam_app": "271590"}
    found = identity.resolve_wikidata(gta, fetch=fetch)
    assert found["status"] == "matched" and found["wikipedia"] == "Grand Theft Auto V"
    assert identity._label(fetch("x/Q1.json")["entities"]["Q1"]) == "GTA V"
    overwatch = {"game_id": "steam-2357570", "list": "steam", "title": "Overwatch®"}
    overwatch["ids"] = {"steam_app": "2357570"}
    found = identity.resolve_wikidata(overwatch, fetch=fetch)
    assert found["wikipedia"] == "Overwatch (2023 video game)"


def test_retry_failed_reruns_only_provider_degraded_results(fake_run):
    from gametagger.comparison.runner import transient_failure

    workdir, cohort, runner, _ = fake_run
    assert not transient_failure({"status": "failed", "error": "ValueError: bad answer"})
    assert transient_failure({"status": "failed", "error": "RateLimitError: slow down"})
    assert transient_failure(
        {"status": "complete", "requests": [{"status": "error", "error": "APITimeoutError"}]}
    )
    path = runner.result_path("steam-1", "legacy-standard")
    degraded = json.loads(path.read_text())
    degraded.update(status="provider_error", error="RateLimitError: 429")
    path.write_text(json.dumps(degraded))
    summary = runner.run(
        cohort["games"], ["legacy-standard"], retry_failed=True, log=lambda m: None
    )
    assert summary["completed"] == 1  # only the degraded one
    fresh = json.loads(path.read_text())
    assert fresh["status"] == "valid" and fresh["attempt"] == 2
    assert path.with_name("legacy-standard.attempt1.json").exists()


WIKI_PAGE = """<html><h1 id="firstHeading" class="firstHeading"><i>Hollow Orchard</i></h1>
<div class="mw-content-ltr mw-parser-output"><table class="infobox ib-video-game">
<tr><th class="infobox-label"><a href="x">Genre(s)</a></th><td class="infobox-data">
<a href="y">Farming sim</a>, <a href="z">RPG</a></td></tr>
<tr><th class="infobox-label">Mode(s)</th><td class="infobox-data">
Single-player<br>multiplayer</td></tr></table>
<p><b>Hollow Orchard</b> is a game by <a href="s">Studio</a>.<sup class="reference">[1]</sup></p>
<p>It has ghosts.</p><div class="mw-heading mw-heading2"><h2>Gameplay</h2></div><p>Later text.</p>
</div></html>"""


def _missing(url):
    raise SourceError("HTTP 404")


def test_wikipedia_falls_back_to_the_article_page_when_the_api_rate_limits():
    from gametagger.genome.sources import wikipedia_source

    def limited(url):
        raise SourceError("en.wikipedia.org returned HTTP 429")

    fetched = wikipedia_source("Hollow Orchard", fetch=limited, fetch_page=lambda url: WIKI_PAGE)
    text = fetched.text
    assert text.reported_title == "Hollow Orchard"
    assert text.text == "Hollow Orchard is a game by Studio.\nIt has ghosts."  # lead only
    assert text.fields == {
        "genres": ["Farming sim", "RPG"],
        "modes": ["Single-player", "multiplayer"],
    }
    with pytest.raises(SourceError, match="404"):
        wikipedia_source("X", fetch=_missing)
