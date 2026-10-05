"""Describing images on a Claude subscription through Claude Code, with a fake ``claude`` command.

Nothing here starts a real Claude Code or calls any provider.
"""

from __future__ import annotations

import io
import json
import subprocess
import threading
from pathlib import Path

import pytest
from test_comparison import FakeTypeSafe, sample_dossier

from gametagger.claude_code import (
    ClaudeCodeClient,
    ClaudeCodeError,
    SubscriptionStop,
    check_plan,
    clean_env,
    inline_refs,
)
from gametagger.comparison.budget import Ledger, Meter, MeteredAnthropic
from gametagger.comparison.describe_cache import CachedAnthropic, DescriptionStore
from gametagger.comparison.dossiers import dossier_path
from gametagger.comparison.runner import Runner
from gametagger.genome.cli import save_dossier
from gametagger.observers.anthropic import AnthropicObserver, ObserverResponse

NOW = 1_790_000_000.0
HELP = "  --safe-mode  ...\n  --strict-mcp-config ...\n  --no-session-persistence ..."
FACT = {"kind": "visual_fact", "text": "A grid of coloured tiles.", "metadata_key": None}


def limits(five=0.2, week=0.1, status="allowed", kind="five_hour"):
    return {
        "type": "rate_limit_event",
        "rate_limit_info": {
            "status": status,
            "rateLimitType": kind,
            "resetsAt": NOW + 3600,
            "unifiedWindows": {
                "five_hour": {"utilization": five, "resetsAt": NOW + 3600},
                "seven_day": {"utilization": week, "resetsAt": NOW + 5 * 86400},
            },
        },
    }


def result(structured=None, *, text="", error=None, cost=0.02):
    row = {
        "type": "result",
        "subtype": "success" if error is None else "error_during_execution",
        "is_error": error is not None,
        "result": error or text,
        "num_turns": 2,
        "duration_ms": 2100,
        "total_cost_usd": cost,
        "usage": {
            "input_tokens": 1500,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "output_tokens": 240,
        },
    }
    if structured is not None:
        row["structured_output"] = structured
    return row


HANG = object()  # a reply that never comes


class FakeProc:
    """Stands in for a running ``claude -p``."""

    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0, hang: bool = False):
        self._lines, self._code, self._hang = stdout, returncode, hang
        self._stopped = threading.Event()
        self.returncode: int | None = None
        self.written = io.StringIO()
        self.stdin = self.written
        self.stdin.close = lambda: None
        self.stdout = self._read()
        self.stderr = io.StringIO(stderr)

    def _read(self):
        yield from self._lines.splitlines(keepends=True)
        if self._hang:
            self._stopped.wait(10)

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15
        self._stopped.set()

    kill = terminate

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = self._code
        return self.returncode


class FakeClaude:
    """Stands in for subprocess.run and subprocess.Popen on the ``claude`` command.

    Replies are used in order; ``answer`` (a function of the request) answers every call once
    the scripted replies run out, so parallel callers can share one fake.
    """

    def __init__(self, *replies, answer=None, auth=None):
        self.replies, self.calls, self.answer = list(replies), [], answer
        self.auth = auth or {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max"}
        self._lock = threading.Lock()

    def __call__(self, argv, **kw):
        with self._lock:
            self.calls.append((argv, kw))
        if argv[1:] == ["--help"]:
            return subprocess.CompletedProcess(argv, 0, HELP, "")
        if argv[1:] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, "2.1.290 (Claude Code)\n", "")
        if argv[1:] == ["auth", "status"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.auth), "")
        raise AssertionError(f"unexpected run: {argv}")

    def popen(self, argv, **kw):
        with self._lock:
            reply = self.replies.pop(0) if self.replies else None
            self.calls.append((argv, kw))
        if reply is None:
            schema = json.loads(argv[argv.index("--json-schema") + 1])
            reply = [limits(), result(self.answer(schema))]
        if isinstance(reply, BaseException):
            raise reply
        if reply is HANG:
            proc = FakeProc("", hang=True)
        elif isinstance(reply, subprocess.CompletedProcess):
            proc = FakeProc(reply.stdout, reply.stderr, reply.returncode)
        else:
            proc = FakeProc("\n".join(json.dumps(m) for m in reply) + "\n")
        kw["proc"] = proc
        return proc

    def turns(self):
        return [
            (a, {**kw, "input": kw["proc"].written.getvalue()}) for a, kw in self.calls if "-p" in a
        ]


def client(fake, tmp_path=None, **kw):
    log = tmp_path / "claude-code.jsonl" if tmp_path else None
    return ClaudeCodeClient(
        executable="/bin/sh", log_path=log, run=fake, popen=fake.popen, now=lambda: NOW, **kw
    )


def observe(c, taxonomy, evidence, **kw):
    from gametagger.evidence import prepare_evidence

    evidence, data = prepare_evidence(evidence)
    observer = AnthropicObserver(taxonomy, model="claude-sonnet-5", client=c, **kw)
    return observer.observe(evidence, image=data)


def test_the_observer_describes_a_screenshot_on_the_subscription(
    tmp_path, monkeypatch, taxonomy, evidence
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    tool_use = {"type": "tool_use", "id": "t1", "name": "StructuredOutput", "input": {}}
    fake = FakeClaude(
        [
            {"type": "system", "subtype": "init", "tools": ["StructuredOutput"]},
            {"type": "assistant", "message": {"model": "claude-sonnet-5", "content": [tool_use]}},
            limits(five=0.31, week=0.12),
            result({"observations": [FACT]}),
        ]
    )
    c = client(fake, tmp_path)
    observations = observe(c, taxonomy, evidence, enforce_boundary=False)
    assert [o.text for o in observations] == ["A grid of coloured tiles."]
    assert observations[0].observer_model == "claude-sonnet-5"

    argv, kw = fake.turns()[0]
    # The API key never reaches Claude Code, or it would bill the API instead of the plan.
    assert "ANTHROPIC_API_KEY" not in kw["env"]
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5"
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert "$defs" not in json.dumps(schema) and "$ref" not in json.dumps(schema)
    system = argv[argv.index("--system-prompt") + 1]
    assert system.startswith("You are GameTagger's factual evidence observer")
    assert "StructuredOutput" in system
    assert "--safe-mode" in argv and "--disable-slash-commands" not in argv
    message = json.loads(kw["input"])
    assert [b["type"] for b in message["message"]["content"]] == ["image", "text"]
    assert c.usage_line() == "Plan usage: 5-hour window 31% used, week 12% used."


def test_metered_calls_cost_nothing_against_the_cap_but_record_the_api_price(
    tmp_path, taxonomy, evidence
):
    fake = FakeClaude([limits(five=0.4), result({"observations": [FACT]}, cost=0.0123)])
    ledger = Ledger(tmp_path / "ledger.jsonl", 0.001)  # far below one API image description
    meter = Meter(ledger, "rich", "gp-x", [])
    store = DescriptionStore(tmp_path / "descriptions")
    metered = CachedAnthropic(MeteredAnthropic(client(fake), meter), store, meter)
    observe(metered, taxonomy, evidence, enforce_boundary=False)
    entry = json.loads((tmp_path / "ledger.jsonl").read_text())
    assert entry["plan"] == "subscription" and entry["cost_usd"] == 0.0
    assert entry["api_equivalent_usd"] == 0.0123 and entry["plan_5h_used"] == 0.4
    assert ledger.spent == 0.0 and Ledger(tmp_path / "ledger.jsonl", 1.0).spent == 0.0
    # The description is saved for reuse, booked at what it cost: nothing.
    (saved,) = (tmp_path / "descriptions").rglob("*.json")
    stored = json.loads(saved.read_text())
    assert stored["cost_usd"] == 0.0 and stored["plan"] == "subscription"
    again = observe(metered, taxonomy, evidence, enforce_boundary=False)
    assert again and len(fake.turns()) == 1  # answered from the store
    assert meter.calls[-1]["cached"] and meter.calls[-1]["plan"] == "subscription"


def test_a_reply_without_structured_output_falls_back_to_its_json_text(taxonomy, evidence):
    reply = 'Here:\n```json\n{"observations": []}\n```'
    assert observe(client(FakeClaude([result(text=reply)])), taxonomy, evidence) == []
    with pytest.raises(ClaudeCodeError):  # a ValueError: the pipeline loses this image only
        observe(client(FakeClaude([result(text="I can't see it.")])), taxonomy, evidence)


def test_plain_text_calls_return_text():
    fake = FakeClaude([result(text="hello")])
    reply = client(fake).messages.create(
        model="claude-haiku-4-5",
        max_tokens=100,
        system="Say hello.",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert reply.stop_reason == "end_turn" and reply.content[0].text == "hello"
    argv, kw = fake.turns()[0]
    assert "--json-schema" not in argv


def test_the_plan_keeps_room_for_the_owner(taxonomy, evidence):
    fake = FakeClaude([limits(five=0.93), result({"observations": []})])
    c = client(fake)
    observe(c, taxonomy, evidence)  # this call pushed the 5-hour window past 90%
    with pytest.raises(SubscriptionStop) as stop:
        observe(c, taxonomy, evidence)
    assert stop.value.reason == "five_hour_limit"
    assert stop.value.wait_seconds == pytest.approx(3660)
    assert len(fake.turns()) == 1  # refused before starting Claude Code

    fake = FakeClaude([limits(week=0.75), result({"observations": []})])
    c = client(fake)
    observe(c, taxonomy, evidence)
    with pytest.raises(SubscriptionStop) as stop:
        observe(c, taxonomy, evidence)
    assert stop.value.reason == "weekly_limit" and stop.value.wait_seconds is None


def test_limits_logins_and_crashes_are_told_apart(taxonomy, evidence):
    hit = [limits(five=1.0, status="rejected"), result(error="Claude AI usage limit reached")]
    with pytest.raises(SubscriptionStop) as stop:
        observe(client(FakeClaude(hit)), taxonomy, evidence)
    assert stop.value.reason == "five_hour_limit" and stop.value.wait_seconds is not None

    out = subprocess.CompletedProcess([], 1, "", "Invalid API key · Please run /login")
    with pytest.raises(SubscriptionStop) as stop:
        observe(client(FakeClaude(out)), taxonomy, evidence)
    assert stop.value.reason == "not_logged_in"

    crash = subprocess.CompletedProcess([], 1, "", "Error: something broke")
    with pytest.raises(ClaudeCodeError):
        observe(client(FakeClaude(crash)), taxonomy, evidence)
    with pytest.raises(ClaudeCodeError, match="longer than"):
        observe(client(FakeClaude(HANG), timeout=0.2), taxonomy, evidence)
    with pytest.raises(ClaudeCodeError, match="could not start"):
        observe(client(FakeClaude(FileNotFoundError("claude"))), taxonomy, evidence)


def test_clean_env_drops_every_api_credential():
    env = clean_env(
        {
            "PATH": "/bin",
            "ANTHROPIC_API_KEY": "x",
            "ANTHROPIC_AUTH_TOKEN": "y",
            "GAMETAGGER_ANTHROPIC_API_KEY": "z",
            "CLAUDECODE": "1",
        }
    )
    assert env == {"PATH": "/bin", "MAX_THINKING_TOKENS": "0"}


def test_schemas_are_inlined_for_claude_code():
    schema = ObserverResponse.model_json_schema()
    assert "$defs" in schema
    flat = inline_refs(schema)
    statement = flat["properties"]["observations"]["items"]
    assert statement["properties"]["kind"]["enum"] == [
        "visual_fact",
        "visual_text",
        "metadata_quote",
    ]
    assert "$ref" not in json.dumps(flat)


def test_check_plan_reports_the_login_and_a_test_call():
    lines = []
    fake = FakeClaude([limits(five=0.4, week=0.2), result({"value": 4})])
    assert check_plan(client(fake), model="claude-haiku-4-5", out=lines.append)
    assert "Logged in (claude.ai, max plan)." in lines
    assert "answered 4" in lines[-1] and "5-hour window 40% used" in lines[-1]

    lines = []
    fake = FakeClaude(auth={"loggedIn": True, "authMethod": "console"})
    assert not check_plan(client(fake), model="claude-haiku-4-5", out=lines.append)
    assert "not a Claude subscription" in lines[-1] and not fake.turns()


def test_a_mobile_retag_runs_on_the_plan_with_jev_under_the_cap(tmp_path, monkeypatch):
    """End to end: v2 tags, the Observer on the plan, Jev metered against a small cap."""
    import gametagger.comparison.runner as runner_module

    original = runner_module.metered_jev_gateway

    def with_fake_client(meter, model):
        gateway = original(meter, model)
        gateway._client = FakeTypeSafe()
        return gateway

    monkeypatch.setattr(runner_module, "metered_jev_gateway", with_fake_client)
    game = {"game_id": "gp-com.x", "list": "mobile", "title": "Orchard Match", "ids": {}}
    path = dossier_path(tmp_path, game["game_id"])
    path.parent.mkdir(parents=True)
    save_dossier(sample_dossier(path.parent, game["game_id"], game["title"]), path)
    path.with_name("gather.json").write_text(json.dumps({"gather_timings": {"total_ms": 1}}))

    fake = FakeClaude(answer=lambda schema: {"observations": [FACT]})
    runner = Runner(
        tmp_path,
        Ledger(tmp_path / "ledger.jsonl", 1.0),
        anthropic_client=client(fake, tmp_path),
        store=DescriptionStore(tmp_path / "descriptions"),
        vocabulary="v2",
    )
    summary = runner.run([game], ["rich"], workers=1, log=lambda m: None)
    assert summary["completed"] == 1 and not summary["stopped_by_budget"]
    record = json.loads(runner.result_path(game["game_id"], "rich").read_text())
    assert record["vocabulary_version"] == "genome-tags-v2"
    assert len(record["tags"]) == 240 and record["status"] in ("complete", "partial")
    assert record["cost_usd"]["anthropic"] == 0.0 and record["cost_usd"]["typesafe"] > 0
    assert record["cost_usd"]["anthropic_on_subscription_api_equivalent"] == pytest.approx(0.06)
    assert {r.get("plan") for r in record["requests"] if r["provider"] == "anthropic"} == {
        "subscription"
    }
    assert runner.ledger.spent == pytest.approx(record["cost_usd"]["typesafe"])
    depth = {k: v for k, v in record["tags"].items() if k.startswith("depth_")}
    assert len(depth) == 12 and all(v["state"] != "absent" for v in depth.values())

    # The shareable summary reads these results (tag states and counts only).
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "experiments/mobile-retag-v2/summarize.py"
    spec = importlib.util.spec_from_file_location("summarize_retag", script)
    summarize = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(summarize)
    summary = summarize.summarize(summarize.load(tmp_path), runner.vocabulary)
    assert summary["games_with_tags"] == 1 and summary["new_tags"]["count"] == 51
    assert sum(summary["new_tags"]["answers"].values()) == 51
    assert summary["per_tag"]["depth_guild_chat"]["requires"] == "engagement_guilds"
    assert summary["umbrella_tags"]["monetization_ads"]["specific_tags"][0] == "ads_rewarded_video"
    assert summary["cost_usd"]["claude_api"] == 0.0
