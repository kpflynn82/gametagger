"""Saved image descriptions and half-price batch describing for rich mode.

The Observer's Claude requests are deterministic for a given image, model and prompt, so each
request is keyed by a digest of its parameters and its answer is kept on disk. An identical
request later is answered from the store at no cost; the price paid when it was first described
stays on record and is shown against the game that uses it.

Batch describing reuses that store in two passes. ``collect`` walks a game's screenshots and
trailer windows with a client that records each request and answers it with an empty
observation list, so nothing is sent. The recorded requests are submitted together through the
Message Batches API (50% of list price) and the answers are saved. A normal run afterwards finds
every description saved and calls only Jev live. The Observer code, its prompt and its boundary
rules are unchanged; only the transport differs.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

from gametagger.comparison.budget import Ledger, Meter, cost_usd, worst_case_claude

BATCH_DISCOUNT = 0.5  # Message Batches API: 50% of standard prices on all token usage
_TRANSPORT = {"extra_headers", "timeout", "extra_query", "extra_body"}
# Answers used while collecting: valid, empty observation lists for each Observer tool.
_EMPTY_INPUT = {
    "record_observations": {"observations": []},
    "record_window_observations": {"context": "unknown", "observations": []},
}


def request_key(kwargs: dict[str, Any]) -> str:
    """Digest of a request's parameters; transport options (headers, timeouts) are excluded."""
    params = {k: v for k, v in kwargs.items() if k not in _TRANSPORT}
    return hashlib.sha256(
        json.dumps(params, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class DescriptionStore:
    """One JSON file per answered request: the message, its usage and the price paid."""

    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        path = self._path(key)
        return json.loads(path.read_text()) if path.exists() else None

    def put(self, key: str, entry: dict) -> None:
        path = self._path(key)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(entry))
            tmp.replace(path)


def _message(data: dict):
    from anthropic.types import Message

    return Message.model_validate(data)


class _Messages:
    def __init__(self, outer):
        self._outer = outer

    def create(self, **kwargs):
        return self._outer._create(kwargs)


class CachedAnthropic:
    """Answers a request from the store when it was described before, else asks ``inner``.

    ``inner`` is normally a metered client, so a new request is reserved against the cap and
    booked in the ledger as usual. A stored answer is not booked again (it was paid for when
    first described); it is added to the game's own call list with the price it cost then and
    ``cached: true``, so per-game costs stay complete.
    """

    def __init__(self, inner, store: DescriptionStore, meter: Meter | None = None):
        self._inner, self._store, self._meter = inner, store, meter
        self.messages = _Messages(self)

    def with_options(self, **options):
        return CachedAnthropic(self._inner.with_options(**options), self._store, self._meter)

    def _create(self, kwargs):
        key = request_key(kwargs)
        hit = self._store.get(key)
        if hit is not None:
            if self._meter is not None:
                self._meter.calls.append(
                    {
                        "provider": "anthropic",
                        "status": "ok",
                        "cached": True,
                        "batch": hit.get("batch", False),
                        "latency_ms": 0.0,
                        "usage": hit.get("usage"),
                        "cost_usd": hit.get("cost_usd") or 0.0,
                    }
                )
            return _message(hit["message"])
        response = self._inner.messages.create(**kwargs)
        usage = getattr(response, "usage", None)
        counts = (
            {k: getattr(usage, k, None) for k in ("input_tokens", "output_tokens")}
            if usage is not None
            else None
        )
        # Keep only complete answers from the real SDK (test doubles without model_dump are not
        # stored).
        if getattr(response, "stop_reason", None) == "tool_use" and hasattr(response, "model_dump"):
            self._store.put(
                key,
                {
                    "message": response.model_dump(mode="json"),
                    "usage": counts,
                    "cost_usd": cost_usd(getattr(response, "model", None), counts),
                    "batch": False,
                },
            )
        return response


class CollectingAnthropic:
    """Records each request and answers it with an empty observation list; sends nothing."""

    def __init__(self):
        self.requests: dict[str, dict[str, Any]] = {}
        self.messages = _Messages(self)

    def with_options(self, **options):
        return self

    def _create(self, kwargs):
        self.requests[request_key(kwargs)] = {
            k: v for k, v in kwargs.items() if k not in _TRANSPORT
        }
        tool = ((kwargs.get("tool_choice") or {}).get("name")) or "record_observations"
        return _message(
            {
                "id": "msg_collect",
                "type": "message",
                "role": "assistant",
                "model": str(kwargs.get("model") or "collect"),
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_collect",
                        "name": tool,
                        "input": _EMPTY_INPUT.get(tool, {"observations": []}),
                    }
                ],
            }
        )


def _booked(ledger: Ledger, batch_id: str) -> set[str]:
    """Request ids of this batch already booked in the ledger (so collecting twice is safe)."""
    if not ledger.path.exists():
        return set()
    booked = set()
    for line in ledger.path.read_text().splitlines():
        if line.strip() and f'"{batch_id}"' in line:
            entry = json.loads(line)
            if entry.get("batch_id") == batch_id and entry.get("custom_id"):
                booked.add(entry["custom_id"])
    return booked


def collect_batch(
    client,
    batch_id: str,
    store: DescriptionStore,
    ledger: Ledger,
    *,
    worst: dict[str, float] | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Book and store the answers of a finished batch. Safe to repeat: booked ids are skipped.

    Also resumes a batch whose submitting process stopped before its results were read.
    """
    worst = worst or {}
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    booked = _booked(ledger, batch_id)
    succeeded = failed = skipped = 0
    spent = 0.0
    seen: set[str] = set()
    for result in client.messages.batches.results(
        batch_id, **({"extra_headers": headers} if headers else {})
    ):
        key = result.custom_id
        seen.add(key)
        if key in booked:
            skipped += 1
            continue
        entry = {
            "arm": "batch-describe",
            "game_id": None,
            "provider": "anthropic",
            "batch": True,
            "batch_id": batch_id,
            "custom_id": key,
        }
        if result.result.type != "succeeded":
            failed += 1
            entry.update(status="error", error=result.result.type, cost_usd=0.0)
            ledger.settle(worst.get(key, 0.0), entry)
            continue
        message = result.result.message
        usage = message.usage
        counts = {k: getattr(usage, k, None) for k in ("input_tokens", "output_tokens")}
        price = (cost_usd(message.model, counts) or 0.0) * BATCH_DISCOUNT
        entry.update(
            status="ok",
            requested_model=message.model,
            returned_model=message.model,
            usage=counts,
            cost_usd=price,
            latency_ms=0.0,
        )
        ledger.settle(worst.get(key, 0.0), entry)
        spent += price
        if message.stop_reason == "tool_use":
            store.put(
                key,
                {
                    "message": message.model_dump(mode="json"),
                    "usage": counts,
                    "cost_usd": price,
                    "batch": True,
                    "batch_id": batch_id,
                },
            )
            succeeded += 1
        else:
            failed += 1  # incomplete answer: left unstored, so a run describes it live
    return {
        "succeeded": succeeded,
        "failed": failed,
        "already_booked": skipped,
        "cost_usd": round(spent, 6),
        "seen": seen,
    }


def describe_in_batch(
    client,
    requests: dict[str, dict[str, Any]],
    store: DescriptionStore,
    ledger: Ledger,
    *,
    workspace_id: str | None = None,
    poll_seconds: float = 30.0,
    log=lambda m: print(m, file=sys.stderr),
    sleep=time.sleep,
) -> dict[str, Any]:
    """Submit requests not yet stored as one batch at half price, wait, and store the answers.

    The worst case of every request (at the batch price) is reserved against the cap before
    anything is sent; each answer is then booked in the ledger with its real usage.
    """
    todo = {k: v for k, v in requests.items() if store.get(k) is None}
    if not todo:
        return {"submitted": 0, "succeeded": 0, "failed": 0, "cost_usd": 0.0}
    worst = {k: worst_case_claude(v) * BATCH_DISCOUNT for k, v in todo.items()}
    ledger.reserve(sum(worst.values()))
    headers = {"anthropic-workspace-id": workspace_id} if workspace_id else None
    try:
        batch = client.messages.batches.create(
            requests=[{"custom_id": k, "params": v} for k, v in todo.items()],
            **({"extra_headers": headers} if headers else {}),
        )
    except BaseException:
        ledger.release(sum(worst.values()))
        raise
    log(f"Batch {batch.id}: {len(todo)} descriptions submitted at half price")
    started = time.monotonic()
    while batch.processing_status != "ended":
        sleep(poll_seconds)
        batch = client.messages.batches.retrieve(
            batch.id, **({"extra_headers": headers} if headers else {})
        )
        counts = batch.request_counts
        log(f"Batch {batch.id}: {counts.succeeded} done, {counts.processing} processing")
    collected = collect_batch(
        client, batch.id, store, ledger, worst=worst, workspace_id=workspace_id
    )
    for key in set(todo) - collected["seen"]:  # never reported back: release the reservation
        ledger.release(worst[key])
    succeeded, failed, spent = collected["succeeded"], collected["failed"], collected["cost_usd"]
    return {
        "batch_id": batch.id,
        "submitted": len(todo),
        "succeeded": succeeded,
        "failed": failed,
        "cost_usd": round(spent, 6),
        "wall_seconds": round(time.monotonic() - started, 1),
    }
