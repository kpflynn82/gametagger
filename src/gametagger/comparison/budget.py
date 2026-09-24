"""List prices, a persistent spend ledger, and metered provider clients with a hard cap.

Every Claude and Jev request goes through a meter. Before a request, its worst-case cost (its
input estimate plus the full ``max_tokens`` of output) is reserved; the request is refused when
spent + reserved + worst case would pass the cap. After it, the reported token usage is priced
and appended to ``ledger.jsonl``, which persists across runs so a pilot and the full run share
one cap. Costs are computed from list prices, not read from an invoice.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

# USD per million tokens: (input, output). Cache writes cost 1.25x input and reads 0.1x input.
PRICES = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "jev": (0.042, 0.0),  # TypeSafe: charged per input token; output tokens are free
}
PRICE_SOURCES = {
    "anthropic": "Anthropic list prices (claude-api reference table, cached 2026-06-24)",
    "typesafe": "TypeSafe list price for jev-1.13 (docs.typesafe.ai/models, read 2026-09-24)",
}
IMAGE_TOKENS_WORST = 3300  # a 1568 x 1568 image at (width x height) / 750
TEXT_CHARS_PER_TOKEN_WORST = 2.5  # conservative; newer tokenizers use more tokens per character


class BudgetExceeded(BaseException):
    """A request was refused because it could push spend past the cap.

    Deliberately not an ``Exception``: provider code records ordinary exceptions as failed
    requests (the old-method adapter, the window Observer and Jev's question executor all do),
    and a budget stop must halt the run instead of being booked as one more failure, much as
    ``KeyboardInterrupt`` passes through ``except Exception``.
    """


class AccountStopped(BudgetExceeded):
    """The provider refused for an account reason (no credit left), so every request would.

    Stops the run like the cap does, instead of booking each remaining game as a failure.
    """


# Provider messages that mean the account, not this request, is the problem.
ACCOUNT_STOP_MESSAGES = ("credit balance is too low",)


def price_key(model: str | None) -> str | None:
    model = (model or "").lower()
    if model.startswith("jev"):
        return "jev"
    return next((k for k in PRICES if k != "jev" and model.startswith(k)), None)


def cost_usd(model: str | None, usage: dict | None) -> float | None:
    """Priced usage, or None when the model or the usage report is unknown."""
    key = price_key(model)
    if key is None or not usage or usage.get("input_tokens") is None:
        return None
    rate_in, rate_out = PRICES[key]
    total = usage["input_tokens"] * rate_in + (usage.get("output_tokens") or 0) * rate_out
    total += (usage.get("cache_creation_input_tokens") or 0) * rate_in * 1.25
    total += (usage.get("cache_read_input_tokens") or 0) * rate_in * 0.1
    return total / 1_000_000


def worst_case_claude(kwargs: dict[str, Any]) -> float:
    """Upper-bound cost of one messages.create call before it is sent."""
    chars, images = len(str(kwargs.get("system") or "")), 0
    chars += len(json.dumps(kwargs.get("tools") or []))
    for message in kwargs.get("messages") or []:
        content = message.get("content")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        for block in blocks:
            if block.get("type") == "image":
                images += 1
            else:
                chars += len(str(block.get("text") or ""))
    usage = {
        "input_tokens": int(chars / TEXT_CHARS_PER_TOKEN_WORST) + images * IMAGE_TOKENS_WORST,
        "output_tokens": int(kwargs.get("max_tokens") or 4096),
    }
    return cost_usd(kwargs.get("model"), usage) or float("inf")


class Ledger:
    def __init__(self, path: Path, cap_usd: float):
        if cap_usd <= 0:
            raise ValueError("The spending cap must be a positive number of dollars")
        self.path, self.cap = path, cap_usd
        self._lock = threading.Lock()
        self._reserved = 0.0
        self.spent = 0.0
        self.unpriced = 0
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    entry = json.loads(line)
                    if entry.get("cost_usd") is None:
                        self.unpriced += 1
                    self.spent += entry.get("cost_usd") or 0.0

    def reserve(self, worst_usd: float) -> float:
        with self._lock:
            if self.spent + self._reserved + worst_usd > self.cap:
                raise BudgetExceeded(
                    f"Refused: spent ${self.spent:.2f} + in flight ${self._reserved:.2f} + "
                    f"this request up to ${worst_usd:.2f} would pass the ${self.cap:.2f} cap"
                )
            self._reserved += worst_usd
            return worst_usd

    def settle(self, reserved: float, entry: dict[str, Any]) -> None:
        with self._lock:
            self._reserved -= reserved
            cost = entry.get("cost_usd")
            if cost is None:
                # Unknown cost: keep the worst case as spent so the cap stays safe.
                self.unpriced += 1
                entry["cost_usd_assumed_worst_case"] = reserved
                self.spent += reserved
            else:
                self.spent += cost
            entry["time"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(entry) + "\n")

    def summary(self) -> dict[str, Any]:
        return {
            "cap_usd": self.cap,
            "spent_usd": round(self.spent, 4),
            "remaining_usd": round(self.cap - self.spent, 4),
            "unpriced_requests": self.unpriced,
        }


@dataclass
class Meter:
    """Where a request's cost is booked."""

    ledger: Ledger
    arm: str
    game_id: str
    calls: list[dict[str, Any]]


class _MeteredMessages:
    def __init__(self, inner, meter: Meter):
        self._inner, self._meter = inner, meter

    def create(self, **kwargs):
        reserved = self._meter.ledger.reserve(worst_case_claude(kwargs))
        start = perf_counter()
        entry: dict[str, Any] = {
            "arm": self._meter.arm,
            "game_id": self._meter.game_id,
            "provider": "anthropic",
            "requested_model": kwargs.get("model"),
            "images": sum(
                1
                for m in kwargs.get("messages") or []
                if isinstance(m.get("content"), list)
                for b in m["content"]
                if b.get("type") == "image"
            ),
        }
        try:
            response = self._inner.create(**kwargs)
        except Exception as exc:
            # A failed request may still be billed; nothing is known, so book zero but record it.
            entry.update(status="error", error=type(exc).__name__, cost_usd=0.0)
            entry["latency_ms"] = (perf_counter() - start) * 1000
            self._meter.ledger.settle(reserved, entry)
            self._meter.calls.append(entry)
            if any(m in str(exc) for m in ACCOUNT_STOP_MESSAGES):
                raise AccountStopped(f"Stopped: Anthropic refused the account: {exc}") from exc
            raise
        usage = getattr(response, "usage", None)
        counts = (
            {
                k: getattr(usage, k, None)
                for k in (
                    "input_tokens",
                    "output_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
            }
            if usage is not None
            else None
        )
        model = getattr(response, "model", None) or kwargs.get("model")
        entry.update(
            status="ok",
            returned_model=getattr(response, "model", None),
            usage=counts,
            cost_usd=cost_usd(model, counts),
            latency_ms=(perf_counter() - start) * 1000,
        )
        self._meter.ledger.settle(reserved, entry)
        self._meter.calls.append(entry)
        return response


class MeteredAnthropic:
    """Wraps an Anthropic client: ``messages.create`` and ``with_options`` are metered."""

    def __init__(self, client, meter: Meter):
        self._client, self._meter = client, meter
        self.messages = _MeteredMessages(client.messages, meter)

    def with_options(self, **options):
        return MeteredAnthropic(self._client.with_options(**options), self._meter)


def jev_worst_case(state: str, specs: dict) -> float:
    chars = len(state) + sum(len(json.dumps(vars(s))) + len(k) for k, s in specs.items())
    usage = {"input_tokens": int(chars / TEXT_CHARS_PER_TOKEN_WORST), "output_tokens": 0}
    return cost_usd("jev", usage) or 0.0


def metered_jev_gateway(meter: Meter, model: str):
    """A TypeSafeGateway whose every request is reserved against and booked to the ledger."""
    from gametagger.decisions.jev import TypeSafeGateway

    class MeteredTypeSafeGateway(TypeSafeGateway):
        def run_pinned(self, *, state, specs, model):
            reserved = meter.ledger.reserve(jev_worst_case(state, specs))
            start = perf_counter()
            entry: dict[str, Any] = {
                "arm": meter.arm,
                "game_id": meter.game_id,
                "provider": "typesafe",
                "requested_model": model,
                "questions": len(specs),
            }
            try:
                response = super().run_pinned(state=state, specs=specs, model=model)
            except Exception as exc:
                entry.update(status="error", error=type(exc).__name__, cost_usd=0.0)
                entry["latency_ms"] = (perf_counter() - start) * 1000
                meter.ledger.settle(reserved, entry)
                meter.calls.append(entry)
                raise
            raw = response.model_dump() if hasattr(response, "model_dump") else {}
            usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else None
            returned = raw.get("model") if isinstance(raw.get("model"), str) else None
            entry.update(
                status="ok",
                returned_model=returned,
                usage=usage,
                cost_usd=cost_usd("jev", usage),
                latency_ms=(perf_counter() - start) * 1000,
            )
            meter.ledger.settle(reserved, entry)
            meter.calls.append(entry)
            return response

    return MeteredTypeSafeGateway(model=model)
