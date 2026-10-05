"""Describe images on a Claude subscription (Pro or Max) through Claude Code instead of the API.

GameTagger normally calls the Claude API with an API key and pays per token. With
``--use-max-plan`` the Observer's calls run through ``claude -p`` (Claude Code, logged in with
the owner's subscription) instead. They then count against the plan's usage limits, the same
limits as chatting with Claude, and cost nothing per token. Use it for the owner's own testing;
a shared or paid service should use the API with its own key.

How one call maps onto Claude Code (ported from the owner's teardown player):

* the caller's system prompt replaces Claude Code's own (``--system-prompt``), and Claude Code's
  tools are switched off (``--tools ""``), so the model sees only the images and the request;
* the forced tool's input schema becomes ``--json-schema``; Claude Code offers it as a tool
  named StructuredOutput and checks the reply against it;
* images travel as image blocks in a stream-json user message on stdin;
* API credentials are removed from the child's environment, because Claude Code bills an API
  key instead of the subscription whenever one is set.

``ClaudeCodeClient.messages.create(...)`` takes the API call's arguments and returns an
``anthropic.types.Message``, so the Observers, the description store and the meter are
unchanged. Each message carries a ``claude_code`` field with the plan details: ``cost_usd`` is
0 and ``api_equivalent_usd`` is what Claude Code reports the call would have cost on the API.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from gametagger.comparison.budget import BudgetExceeded, cost_usd

# Set any of these and Claude Code bills the API instead of the subscription.
API_CREDENTIALS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "GAMETAGGER_ANTHROPIC_API_KEY",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)
# Flags that trim Claude Code down to a bare model call, used when this version has them.
OPTIONAL_FLAGS = (
    "--safe-mode",  # no CLAUDE.md, skills, plugins, hooks or MCP servers
    "--strict-mcp-config",  # no MCP servers
    "--disable-slash-commands",
    "--no-chrome",  # no Claude in Chrome browser tools
    "--no-session-persistence",  # don't keep a transcript of every screenshot
)
SCALARS = ("string", "number", "integer", "boolean")
DEBUG_RECORDS = 200  # calls written to claude-code.jsonl per run, to diagnose failures
GRACE_SECONDS = 1.0  # after the answer, how long to wait for Claude Code's closing messages
LIMIT_WORDS = ("usage limit", "limit reached", "hit your", "out of extra usage", "weekly limit")
LOGIN_WORDS = ("/login", "not logged in", "invalid api key", "please log in", "oauth token")
PLAN = "subscription"


class SubscriptionStop(BudgetExceeded):
    """The subscription can't (or shouldn't) take more calls now.

    A ``BudgetExceeded``, so it halts a run instead of being booked as one more failed request.
    With ``wait_seconds`` the five-hour window is full and the run can wait for it to reset;
    without, the run stops and resumes later (finished games are kept and skipped).
    """

    def __init__(self, message: str, reason: str, wait_seconds: float | None = None):
        super().__init__(message)
        self.reason, self.wait_seconds = reason, wait_seconds


class ClaudeCodeError(ValueError):
    """One call failed (timeout, crash, unreadable reply). The caller loses that image only."""


def clean_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """The environment for ``claude``: no API credentials, and not marked as nested."""
    env = dict(os.environ if env is None else env)
    for name in (*API_CREDENTIALS, "CLAUDECODE"):
        env.pop(name, None)
    # Describing images needs no extended thinking; keep calls quick and light on usage.
    env.setdefault("MAX_THINKING_TOKENS", "0")
    return env


def inline_refs(schema: Any, defs: dict[str, Any] | None = None) -> Any:
    """The schema with every local ``$ref`` replaced by its definition (pydantic emits $defs)."""
    if defs is None and isinstance(schema, dict):
        defs = schema.get("$defs") or {}
    if isinstance(schema, list):
        return [inline_refs(x, defs) for x in schema]
    if not isinstance(schema, dict):
        return schema
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/") and defs:
        target = defs[ref.removeprefix("#/$defs/")]
        merged = {**target, **{k: v for k, v in schema.items() if k != "$ref"}}
        return inline_refs(merged, defs)
    return {k: inline_refs(v, defs) for k, v in schema.items() if k != "$defs"}


def lenient(schema: Any) -> Any:
    """The schema as the model sees it on the API, except that optional scalars may be null.

    Claude Code checks every reply against the schema and sends the model back on a mismatch;
    "not shown" often comes back as null. The API does not check tool input at all.
    """
    if isinstance(schema, list):
        return [lenient(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    out = {key: lenient(value) for key, value in schema.items() if key != "properties"}
    if isinstance(schema.get("properties"), dict):
        required = set(schema.get("required") or [])
        out["properties"] = {}
        for name, sub in schema["properties"].items():
            sub = lenient(sub)
            if name not in required and isinstance(sub, dict) and sub.get("type") in SCALARS:
                sub = {**sub, "type": [sub["type"], "null"]}
                if "enum" in sub:
                    sub["enum"] = [*sub["enum"], None]
            out["properties"][name] = sub
    return out


def find_claude(executable: str | None = None) -> str | None:
    """The ``claude`` command, including the usual install places a Mac shell may not have on
    its PATH when run from a script."""
    if executable:
        return shutil.which(executable) or (executable if Path(executable).exists() else None)
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    for candidate in (
        home / ".claude" / "local" / "claude",
        home / ".local" / "bin" / "claude",
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _parse_json(text: str) -> dict[str, Any] | None:
    """A JSON object in a text reply (bare, fenced, or the last {...} in the text)."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    for chunk in (text, fenced.group(1) if fenced else None, text[text.find("{") :]):
        if chunk and chunk.startswith("{"):
            try:
                value = json.loads(chunk)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    return None


def _message(data: dict[str, Any]):
    from anthropic.types import Message

    return Message.model_validate(data)


class _Messages:
    def __init__(self, client: ClaudeCodeClient):
        self._client = client

    def create(self, **kwargs: Any):
        return self._client.create(**kwargs)


class ClaudeCodeClient:
    """Stands in for ``anthropic.Anthropic`` and runs each call through ``claude -p``.

    Safe to share between threads: each call runs its own Claude Code process, and the latest
    usage report is kept under a lock.
    """

    plan = PLAN

    def __init__(
        self,
        *,
        executable: str | None = None,
        log_path: Path | None = None,
        timeout: float = 300.0,
        max_turns: int = 4,
        max_5h_share: float = 0.9,
        max_week_share: float = 0.7,
        run=None,
        popen=None,
        now=time.time,
    ):
        found = find_claude(executable)
        if not found:
            raise SystemExit(
                "Claude Code isn't installed (no 'claude' command). Install it, then run "
                "'claude' once and log in with your Claude subscription."
            )
        self.executable, self.log_path, self.timeout = found, log_path, timeout
        self.max_turns, self._now = max_turns, now
        self._run = run or subprocess.run
        self._popen = popen or subprocess.Popen
        # Leave room for the owner's own use of the plan: stop at ``max_5h_share`` of the
        # five-hour window (until it resets) and at ``max_week_share`` of the week.
        self.max_5h_share, self.max_week_share = max_5h_share, max_week_share
        self.limits: dict[str, Any] | None = None  # the latest rate_limit_info Claude Code sent
        self.setup: dict[str, Any] | None = None  # what Claude Code loaded, from its first call
        self._lock = threading.Lock()
        self._debug_left = DEBUG_RECORDS
        self.workdir = Path(tempfile.mkdtemp(prefix="gametagger-claude-"))  # nothing to discover
        self.messages = _Messages(self)
        self._flags: list[str] | None = None

    def with_options(self, **options: Any) -> ClaudeCodeClient:
        return self  # timeouts and headers are API options; Claude Code has its own timeout

    # -- setup ---------------------------------------------------------------------------------

    def _call(self, argv: list[str], *, timeout: float = 30.0):
        return self._run(
            [self.executable, *argv],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=clean_env(),
            cwd=self.workdir,
        )

    def flags(self) -> list[str]:
        """The optional trimming flags this Claude Code version understands."""
        if self._flags is None:
            try:
                help_text = self._call(["--help"]).stdout or ""
            except (OSError, subprocess.SubprocessError):
                help_text = ""
            self._flags = [f for f in OPTIONAL_FLAGS if f in help_text]
        return self._flags

    def version(self) -> str:
        out = self._call(["--version"])
        return (out.stdout or out.stderr or "").strip()

    def auth_status(self) -> dict[str, Any]:
        """``claude auth status`` as GameTagger sees it (API credentials removed)."""
        out = self._call(["auth", "status"])
        try:
            status = json.loads(out.stdout or "{}")
        except ValueError:
            status = {"loggedIn": out.returncode == 0, "detail": (out.stdout or "")[:200]}
        if not isinstance(status, dict):
            status = {"detail": str(status)[:200]}
        status.setdefault("loggedIn", out.returncode == 0)
        return status

    # -- the plan's usage limits -----------------------------------------------------------------

    def window(self, name: str) -> tuple[float | None, float | None]:
        """(share used, reset time) of a usage window: ``five_hour`` or ``seven_day``."""
        limits = self.limits or {}
        info = (limits.get("unifiedWindows") or {}).get(name)
        if info is None and limits.get("rateLimitType") == name:
            info = limits  # older Claude Code reports only the window nearest its limit
        info = info or {}
        return info.get("utilization"), info.get("resetsAt")

    def usage_line(self) -> str:
        used5, _ = self.window("five_hour")
        used7, _ = self.window("seven_day")
        if used5 is None and used7 is None:
            return "Plan usage: not reported yet."
        parts = [
            f"{label} {used:.0%} used"
            for label, used in (("5-hour window", used5), ("week", used7))
            if used is not None
        ]
        return "Plan usage: " + ", ".join(parts) + "."

    def _when(self, epoch: float | None) -> str:
        if not epoch:
            return "later"
        return "at " + datetime.fromtimestamp(epoch).strftime("%a %H:%M")

    def check_limits(self) -> None:
        """Refuse a call that would eat into the headroom kept for the owner."""
        now = self._now()
        used7, reset7 = self.window("seven_day")
        if used7 is not None and used7 >= self.max_week_share and (reset7 or now + 1) > now:
            raise SubscriptionStop(
                f"your plan's weekly usage is at {used7:.0%} (GameTagger stops at "
                f"{self.max_week_share:.0%}); it resets {self._when(reset7)}",
                "weekly_limit",
            )
        used5, reset5 = self.window("five_hour")
        if used5 is not None and used5 >= self.max_5h_share and reset5 and reset5 > now:
            raise SubscriptionStop(
                f"your plan's 5-hour window is at {used5:.0%} (GameTagger pauses at "
                f"{self.max_5h_share:.0%}); it resets {self._when(reset5)}",
                "five_hour_limit",
                wait_seconds=reset5 - now + 60,
            )

    def _stop_for(self, text: str, turn_limits: dict[str, Any]) -> SubscriptionStop | None:
        low = text.lower()
        if turn_limits.get("status") == "rejected" or any(w in low for w in LIMIT_WORDS):
            info = turn_limits or self.limits or {}
            kind = str(info.get("rateLimitType") or "")
            reset = info.get("resetsAt")
            if kind == "five_hour" and reset and reset > self._now():
                return SubscriptionStop(
                    f"the plan's 5-hour limit was reached; it resets {self._when(reset)}",
                    "five_hour_limit",
                    wait_seconds=reset - self._now() + 60,
                )
            return SubscriptionStop(
                f"the plan's usage limit was reached: {text[:200]}", "usage_limit"
            )
        if any(w in low for w in LOGIN_WORDS):
            return SubscriptionStop(
                f"Claude Code is not logged in to a subscription: {text[:200]}", "not_logged_in"
            )
        return None

    # -- one call --------------------------------------------------------------------------------

    def argv(self, *, model: str, system: str, schema: dict[str, Any] | None) -> list[str]:
        argv = [
            "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--model", model,
            "--system-prompt", system,
            "--tools", "",
            "--max-turns", str(self.max_turns),
            *self.flags(),
        ]  # fmt: skip
        if schema is not None:
            loose = lenient(inline_refs(schema))
            argv += ["--json-schema", json.dumps(loose, separators=(",", ":"))]
        return argv

    def create(self, **kwargs: Any):
        model = kwargs["model"]
        system = kwargs.get("system") or ""
        if isinstance(system, list):
            system = "\n\n".join(b.get("text", "") for b in system if isinstance(b, dict))
        messages = kwargs.get("messages") or []
        content = messages[-1]["content"] if messages else ""
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        content = [dict(b) for b in content]
        tool, schema = None, None
        choice = kwargs.get("tool_choice") or {}
        if choice.get("type") == "tool":
            tool = next((t for t in kwargs.get("tools") or [] if t["name"] == choice["name"]), None)
            schema = tool["input_schema"] if tool else None
        if tool is not None:
            system += (
                f"\n\nHere the {tool['name']} tool is named StructuredOutput. Call it exactly "
                "once, straight away, with no text before it, and then stop. "
                f"{tool.get('description') or ''}"
            ).rstrip()
            if content and content[-1].get("type") == "text":
                content[-1]["text"] += "\n\nReply now with the StructuredOutput call only, no text."
            else:
                content.append(
                    {"type": "text", "text": "Reply now with the StructuredOutput call only."}
                )
        self.check_limits()
        line = json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": content},
                "parent_tool_use_id": None,
                "session_id": "",
            }
        )
        start = perf_counter()
        turn = self._turn(
            self.argv(model=model, system=system, schema=schema),
            line,
            want_answer=tool is not None,
        )
        raw = turn["usage"]
        result = turn["result"] or {}
        usage = {
            "input_tokens": int(raw.get("input_tokens") or 0),
            "output_tokens": int(raw.get("output_tokens") or 0),
            "cache_creation_input_tokens": int(raw.get("cache_creation_input_tokens") or 0),
            "cache_read_input_tokens": int(raw.get("cache_read_input_tokens") or 0),
        }
        returned = turn["model"] or model
        plan = {
            "plan": PLAN,
            "cost_usd": 0.0,
            "api_equivalent_usd": result.get("total_cost_usd") or cost_usd(model, usage),
            "plan_5h_used": self.window("five_hour")[0],
            "plan_week_used": self.window("seven_day")[0],
            "latency_ms": round((perf_counter() - start) * 1000),
            "claude_ms": result.get("duration_ms"),
            "turns": result.get("num_turns"),
            "cut_short": turn["cut_short"] or None,
        }
        envelope = {
            "id": f"msg_claude_code_{int(time.time() * 1000)}",
            "type": "message",
            "role": "assistant",
            "model": returned,
            "stop_sequence": None,
            "usage": usage,
            "claude_code": {k: v for k, v in plan.items() if v is not None},
        }
        text = turn["text"]
        if tool is None:
            return _message(
                envelope | {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}
            )
        data = turn["answer"]
        if not isinstance(data, dict):
            data = result.get("structured_output")
        if not isinstance(data, dict):
            data = _parse_json(text)
        if not isinstance(data, dict):
            raise ClaudeCodeError(f"Claude Code returned no structured answer ({text[:120]!r})")
        block = {"type": "tool_use", "id": "toolu_claude_code", "name": tool["name"], "input": data}
        return _message(envelope | {"stop_reason": "tool_use", "content": [block]})

    def _setup_from(self, message: dict[str, Any]) -> None:
        with self._lock:
            if self.setup is not None:
                return
            self.setup = {
                "purpose": "setup",
                "claude_code_version": message.get("claude_code_version"),
                "api_key_source": message.get("apiKeySource"),
                "model": message.get("model"),
                "tools": message.get("tools"),
                "mcp_servers": [
                    m.get("name") if isinstance(m, dict) else m
                    for m in message.get("mcp_servers") or []
                ],
                "skills": len(message.get("skills") or []),
                "plugins": [
                    x.get("name") for x in message.get("plugins") or [] if isinstance(x, dict)
                ],
                "flags": self.flags(),
            }
        self._debug(self.setup)

    def _turn(self, argv: list[str], line: str, *, want_answer: bool) -> dict[str, Any]:
        """Run one ``claude -p`` and read its stream as it comes.

        The answer is the first StructuredOutput call Claude Code accepts. Older versions let
        the model carry on after it, so Claude Code is stopped as soon as the answer is in."""
        turn_limits: dict[str, Any] = {}
        try:
            proc = self._popen(
                [self.executable, *argv],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=clean_env(),
                cwd=self.workdir,
            )
        except OSError as exc:
            raise ClaudeCodeError(f"Claude Code could not start: {exc}") from None
        lines: queue.Queue[str | None] = queue.Queue()

        def pump() -> None:
            try:
                for raw_line in proc.stdout:
                    lines.put(raw_line)
            finally:
                lines.put(None)

        threading.Thread(target=pump, daemon=True).start()
        try:
            proc.stdin.write(line + "\n")
            proc.stdin.close()
        except OSError:
            pass  # it already quit; its output says why
        deadline = time.monotonic() + self.timeout
        grace: float | None = None  # after the answer: a moment for the closing messages
        answer: dict[str, Any] | None = None
        result: dict[str, Any] | None = None
        offered: dict[str, Any] = {}  # StructuredOutput calls waiting for Claude Code's check
        usage_by_message: dict[str, dict[str, Any]] = {}
        texts: list[str] = []
        model: str | None = None
        trace: list[Any] = []  # what happened in this call, without the images
        timed_out = cut_short = False
        while True:
            remaining = (grace or deadline) - time.monotonic()
            if remaining <= 0:
                timed_out = grace is None
                cut_short = grace is not None
                break
            try:
                raw_line = lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if raw_line is None:
                break
            raw_line = raw_line.strip()
            if not raw_line.startswith("{"):
                continue
            try:
                message = json.loads(raw_line)
            except ValueError:
                continue
            kind = message.get("type")
            if kind == "system" and message.get("subtype") == "init" and self.setup is None:
                self._setup_from(message)
            elif kind == "rate_limit_event":
                info = message.get("rate_limit_info") or {}
                with self._lock:
                    first = self.limits is None
                    self.limits = info or self.limits
                if info and first:
                    self._debug({"rate_limit_info": info})  # its shape varies by version
                turn_limits = info
            elif kind == "result":
                result = message
                break
            elif kind in ("assistant", "user"):
                if kind == "assistant" and answer is not None:
                    cut_short = True  # the model went on past its answer
                    break
                body = message.get("message") or {}
                if kind == "assistant":
                    model = body.get("model") if isinstance(body.get("model"), str) else model
                    if body.get("usage"):
                        key = body.get("id") or str(len(usage_by_message))
                        usage_by_message[key] = body["usage"]
                for b in body.get("content") or []:
                    if not isinstance(b, dict):
                        continue
                    shown = b.get("text") or b.get("name") or str(b.get("content") or "")
                    trace.append([kind, b.get("type"), str(shown)[:300]])
                    if b.get("type") == "text" and kind == "assistant":
                        texts.append(b.get("text") or "")
                    elif b.get("type") == "tool_use" and b.get("name") == "StructuredOutput":
                        offered[b.get("id") or ""] = b.get("input")
                    elif b.get("type") == "tool_result" and not b.get("is_error"):
                        taken = offered.get(b.get("tool_use_id") or "")
                        if answer is None and isinstance(taken, dict) and want_answer:
                            answer, grace = taken, time.monotonic() + GRACE_SECONDS
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        try:
            stderr = proc.stderr.read() or ""
        except (OSError, ValueError):
            stderr = ""
        done = result or {}
        failed = answer is None and (result is None or done.get("is_error"))
        if failed or cut_short or (done.get("num_turns") or 0) > 2:
            self._debug(
                {
                    "turns": done.get("num_turns"),
                    "cut_short": cut_short,
                    "rate_limit": bool(turn_limits),
                    "trace": trace[-12:],
                    "result": str(done.get("result") or stderr or "")[:300],
                }
            )
        if answer is None and result is None:
            detail = " ".join([stderr, *texts]).strip()
            stop = self._stop_for(detail, turn_limits)
            if stop:
                raise stop
            if timed_out:
                raise ClaudeCodeError(f"Claude Code took longer than {self.timeout:g} s")
            raise ClaudeCodeError(
                f"Claude Code exited ({proc.returncode}) without a reply: {detail[:200]}"
            )
        if answer is None and (done.get("is_error") or done.get("subtype") != "success"):
            parts = (done.get("result"), *(done.get("errors") or []), done.get("subtype"))
            detail = " ".join(str(x) for x in parts if x)
            stop = self._stop_for(detail, turn_limits) or (
                self._stop_for(" ".join(texts), turn_limits) if done.get("is_error") else None
            )
            if stop:
                raise stop
            raise ClaudeCodeError(f"Claude Code call failed: {detail[:200]}")
        usage = dict(done.get("usage") or {})
        if not usage:  # stopped before the closing summary: add up what each reply reported
            for part in usage_by_message.values():
                for key, value in part.items():
                    if isinstance(value, int | float) and not isinstance(value, bool):
                        usage[key] = usage.get(key, 0) + value
        text = done.get("result") if isinstance(done.get("result"), str) else ""
        return {
            "answer": answer,
            "result": result,
            "usage": usage,
            "model": model,
            "text": text or "\n".join(texts),
            "cut_short": cut_short,
        }

    def _debug(self, record: dict[str, Any]) -> None:
        """Keep what went on in a call that needed retries or failed (no images, no keys)."""
        if self.log_path is None:
            return
        with self._lock:
            if self._debug_left <= 0:
                return
            self._debug_left -= 1
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(json.dumps(record) + "\n")


def check_plan(client: ClaudeCodeClient, *, model: str, out=print) -> bool:
    """Check Claude Code is installed, logged in to a subscription, and answers one tiny call."""
    out(f"Claude Code: {client.executable} ({client.version() or 'version unknown'})")
    status = client.auth_status()
    if not status.get("loggedIn"):
        out("Not logged in. Run 'claude' once and log in with your Claude subscription.")
        return False
    method = status.get("authMethod") or "unknown login"
    plan = status.get("subscriptionType")
    out(f"Logged in ({method}{', ' + str(plan) + ' plan' if plan else ''}).")
    if method not in ("claude.ai", "oauth_token") and not plan:
        out("This login is not a Claude subscription, so calls would not count against a plan.")
        return False
    try:
        reply = client.messages.create(
            model=model,
            max_tokens=50,
            system="Answer the arithmetic question.",
            messages=[{"role": "user", "content": "What is 2 + 2?"}],
            tools=[
                {
                    "name": "answer",
                    "description": "Give the number.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"value": {"type": "integer"}},
                        "required": ["value"],
                    },
                }
            ],
            tool_choice={"type": "tool", "name": "answer"},
        )
    except (ClaudeCodeError, SubscriptionStop) as exc:
        out(f"The test call failed: {exc}")
        return False
    value = reply.content[0].input.get("value")
    out(f"Test call on {model}: answered {value}. {client.usage_line()}")
    return value == 4
