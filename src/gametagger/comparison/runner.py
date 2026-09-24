"""Run the compared methods on shared dossiers, with per-stage timing, tokens and a hard cap.

Arms:
* ``rich``            vision Observer (Claude) on screenshots and trailer bursts, then Jev
* ``legacy-standard`` the old single call on Claude Haiku 4.5 (the old site's "standard")
* ``legacy-deep``     the old single call on Claude Opus 4.8 (the old site's "deep")

Each (game, arm) result is written once and skipped on later runs, so an interrupted run
resumes. Full responses go to ``<workdir>/raw``; ``<workdir>/results`` holds compact records
without third-party text. Provider failures are recorded as results and stay in denominators.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import perf_counter
from typing import Any

from gametagger.comparison.budget import (
    PRICE_SOURCES,
    BudgetExceeded,
    Ledger,
    Meter,
    MeteredAnthropic,
    metered_jev_gateway,
)
from gametagger.comparison.dossiers import dossier_path, safe_id
from gametagger.genome.dossier import Dossier

ARMS = ("rich", "legacy-standard", "legacy-deep")
# Provider or network failures (not answers) that justify re-running a (game, arm) once asked.
TRANSIENT = (
    "RateLimitError",
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "OverloadedError",
    "ServiceUnavailableError",
    "TypeSafeAPIConnectionError",
    "TypeSafeTimeoutError",
    "TypeSafeAPIError",
)


def transient_failure(record: dict) -> bool:
    """True when a stored result was degraded by the provider or network, not by the method."""
    errors = (
        [record.get("error") or ""] if record.get("status") in ("failed", "provider_error") else []
    )
    errors += [
        str(c.get("error") or "")
        for c in record.get("requests") or []
        if c.get("status") == "error"
    ]
    return any(name in e for e in errors for name in TRANSIENT)


DEFAULT_OBSERVER_MODEL = "claude-sonnet-5"


def load_dossier(path: Path) -> Dossier:
    dossier = Dossier.model_validate_json(path.read_text())
    root = path.resolve().parent
    return dossier.model_copy(
        update={
            "images": [
                i.model_copy(update={"path": str((root / i.path).resolve())})
                for i in dossier.images
            ],
            "videos": [
                v.model_copy(update={"path": str((root / v.path).resolve())})
                for v in dossier.videos
            ],
        }
    )


def interleaved(cohort: dict) -> list[dict]:
    """Steam #1, mobile #1, Steam #2, ... so a small --limit samples both lists evenly."""
    steam = [g for g in cohort["games"] if g["list"] == "steam"]
    mobile = [g for g in cohort["games"] if g["list"] == "mobile"]
    order = []
    for i in range(max(len(steam), len(mobile))):
        order += [x[i] for x in (steam, mobile) if i < len(x)]
    return order


def _sum_usage(calls: list[dict], provider: str) -> dict[str, int]:
    total = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    for call in calls:
        if call["provider"] != provider:
            continue
        total["requests"] += 1
        for key in ("input_tokens", "output_tokens"):
            total[key] += ((call.get("usage") or {}).get(key)) or 0
    return total


def _cost(calls: list[dict], provider: str | None = None) -> float:
    return sum(
        c.get("cost_usd") or c.get("cost_usd_assumed_worst_case") or 0.0
        for c in calls
        if provider is None or c["provider"] == provider
    )


class Runner:
    def __init__(
        self,
        workdir: Path,
        ledger: Ledger,
        *,
        anthropic_client: Any,
        observer_model: str = DEFAULT_OBSERVER_MODEL,
        jev_model: str = "jev-latest",
        workspace_id: str | None = None,
        max_questions_per_request: int = 60,
    ):
        from gametagger.genome.vocabulary import load_vocabulary
        from gametagger.taxonomy import load_taxonomy

        self.workdir, self.ledger = workdir, ledger
        self.client = anthropic_client
        self.observer_model, self.jev_model = observer_model, jev_model
        self.workspace_id = workspace_id
        self.max_questions = max_questions_per_request
        self.taxonomy = load_taxonomy()
        self.vocabulary = load_vocabulary(self.taxonomy)

    def result_path(self, game_id: str, arm: str) -> Path:
        return self.workdir / "results" / safe_id(game_id) / f"{arm}.json"

    def raw_path(self, game_id: str, arm: str) -> Path:
        return self.workdir / "raw" / safe_id(game_id) / f"{arm}.json"

    # ------------------------------------------------------------------ arms

    def _rich(self, game: dict, dossier: Dossier, meter: Meter) -> tuple[dict, dict]:
        from gametagger.genome.engine import GenomeEngine, GenomePipeline
        from gametagger.observers.anthropic import AnthropicObserver
        from gametagger.observers.anthropic_ordered import AnthropicOrderedObserver

        client = MeteredAnthropic(self.client, meter)
        engine = GenomeEngine(
            self.taxonomy,
            self.vocabulary,
            metered_jev_gateway(meter, self.jev_model),
            max_questions_per_request=self.max_questions,
        )
        observer = AnthropicObserver(
            self.taxonomy,
            model=self.observer_model,
            client=client,
            workspace_id=self.workspace_id,
            enforce_boundary=False,
        )
        ordered = AnthropicOrderedObserver(
            self.taxonomy,
            model=self.observer_model,
            client=client,
            workspace_id=self.workspace_id,
            allow_live=True,
            enforce_boundary=False,
        )
        profile = GenomePipeline(engine, observer, ordered).analyze(dossier, offline=False)
        raw = json.loads(profile.model_dump_json())
        provenance = profile.provenance
        record = {
            "status": profile.status,
            "primary_genre": profile.primary_genre.genre_id if profile.primary_genre else None,
            "primary_genre_probability": (
                profile.primary_genre.probability if profile.primary_genre else None
            ),
            "secondary_genres": [g.genre_id for g in profile.secondary_genres],
            "genre_family_probabilities": (
                profile.genre.family_probabilities if profile.genre else None
            ),
            "top_genres": (
                sorted(profile.genre.global_genre_probabilities.items(), key=lambda kv: -kv[1])[:5]
                if profile.genre
                else []
            ),
            "tags": {
                t.tag_id: {
                    "tier": t.tier,
                    "state": t.state.value if t.state else None,
                    "p_present": (t.probabilities or {}).get("present"),
                }
                for t in profile.tags
            },
            "counts": profile.counts,
            "stage_ms": {
                "observe": provenance["latency_ms"]["observe"],
                "decide": provenance["latency_ms"]["decide"],
                "total": provenance["latency_ms"]["total"],
            },
            "questions_asked": provenance["questions_asked"],
            "returned_decision_model": provenance["returned_decision_model"],
            "observer_model": self.observer_model,
            "quarantined_observations": len(profile.quarantined_observations),
            "warnings": profile.warnings,
        }
        return record, raw

    def _legacy(self, game: dict, dossier: Dossier, meter: Meter, quality: str):
        from gametagger.decisions.legacy import LegacyTagger, boolean_tags

        tagger = LegacyTagger(MeteredAnthropic(self.client, meter), workspace_id=self.workspace_id)
        run = tagger.tag(dossier, quality, game_name=game["title"])
        raw = run.to_json()
        record = {
            "status": run.status,
            "primary_genre": run.result.get("primary_genre") or None,
            "primary_genre_resolution": run.audit.get("primary_genre_resolution"),
            "secondary_genres": run.result.get("secondary_genres") or [],
            "confidence": run.result.get("confidence"),
            "tags": boolean_tags(run.result),
            "stage_ms": {
                "prepare": run.latency_ms.get("prepare"),
                "call": run.latency_ms.get("call"),
                "parse": run.latency_ms.get("parse"),
                "total": sum(v for v in run.latency_ms.values() if v is not None),
            },
            "requested_model": run.requested_model,
            "returned_model": run.returned_model,
            "stop_reason": run.stop_reason,
            "images_sent": len(run.image_ids),
            "sections": run.sections,
            "error": run.error,
        }
        return record, raw

    # ------------------------------------------------------------------ one game

    def run_one(
        self, game: dict, arm: str, *, force: bool = False, retry_failed: bool = False
    ) -> dict | None:
        out = self.result_path(game["game_id"], arm)
        attempt = 1
        if out.exists() and not force:
            previous = json.loads(out.read_text())
            if not (retry_failed and transient_failure(previous)):
                return None
            # Keep the degraded attempt on file; the new record says which attempt it is.
            attempt = int(previous.get("attempt", 1)) + 1
            out.rename(out.with_name(f"{arm}.attempt{attempt - 1}.json"))
        path = dossier_path(self.workdir, game["game_id"])
        if not path.exists():
            raise FileNotFoundError(f"No dossier for {game['game_id']}; run 'dossiers' first")
        gather = json.loads(path.with_name("gather.json").read_text())
        dossier = load_dossier(path)
        meter = Meter(self.ledger, arm, game["game_id"], [])
        start = perf_counter()
        try:
            if arm == "rich":
                record, raw = self._rich(game, dossier, meter)
            elif arm in ("legacy-standard", "legacy-deep"):
                quality = "standard" if arm == "legacy-standard" else "deep"
                record, raw = self._legacy(game, dossier, meter, quality)
            else:
                raise ValueError(f"Unknown arm {arm}")
        except BudgetExceeded:
            raise
        except Exception as exc:  # recorded; stays in denominators
            record = {
                "status": "failed",
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "stage_ms": {"total": (perf_counter() - start) * 1000},
            }
            raw = {"traceback": traceback.format_exc()[-4000:]}
        record.update(
            game_id=game["game_id"],
            list=game["list"],
            arm=arm,
            attempt=attempt,
            wall_ms=(perf_counter() - start) * 1000,
            evidence_gather_ms=gather.get("gather_timings", {}).get("total_ms"),
            usage={
                "anthropic": _sum_usage(meter.calls, "anthropic"),
                "typesafe": _sum_usage(meter.calls, "typesafe"),
            },
            cost_usd={
                "anthropic": _cost(meter.calls, "anthropic"),
                "typesafe": _cost(meter.calls, "typesafe"),
                "total": _cost(meter.calls),
            },
            requests=[
                {
                    k: c.get(k)
                    for k in ("provider", "status", "error", "latency_ms", "usage", "cost_usd")
                }
                for c in meter.calls
            ],
            evidence={k: gather.get(k) for k in ("sources", "images", "videos", "text_chars")},
        )
        for target, data in ((self.raw_path(game["game_id"], arm), raw), (out, record)):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(data, indent=2, default=str) + "\n")
        return record

    def run(
        self,
        games: list[dict],
        arms: list[str],
        *,
        workers: int = 3,
        force: bool = False,
        retry_failed: bool = False,
        log=lambda m: print(m, file=sys.stderr),
    ) -> dict[str, Any]:
        jobs = [(g, a) for g in games for a in arms]
        done, failed, stopped = 0, 0, None

        def one(job):
            game, arm = job
            return game, arm, self.run_one(game, arm, force=force, retry_failed=retry_failed)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(one, job) for job in jobs]
            for future in as_completed(futures):
                try:
                    game, arm, record = future.result()
                except BudgetExceeded as exc:
                    stopped = str(exc)
                    for f in futures:
                        f.cancel()
                    continue
                if record is None:
                    continue
                done += 1
                failed += record["status"] in ("failed", "provider_error", "parse_error")
                log(
                    f"{game['game_id']} [{arm}] {record['status']} in "
                    f"{record['wall_ms'] / 1000:.1f}s, ${record['cost_usd']['total']:.4f}; "
                    f"ledger ${self.ledger.spent:.2f} of ${self.ledger.cap:.2f}"
                )
        return {
            "completed": done,
            "failed": failed,
            "stopped_by_budget": stopped,
            "ledger": self.ledger.summary(),
            "price_sources": PRICE_SOURCES,
        }


def make_runner(workdir: Path, cap_usd: float, **kwargs) -> Runner:
    from anthropic import Anthropic

    from gametagger.config import anthropic_api_key

    key = anthropic_api_key()
    if not key:
        raise SystemExit("No Anthropic key: set ANTHROPIC_API_KEY or GAMETAGGER_ANTHROPIC_API_KEY")
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise SystemExit("No TypeSafe key: set TYPESAFE_API_KEY")
    # The old site used the SDK defaults (two automatic retries); keep them for every arm.
    client = Anthropic(api_key=key, timeout=180, max_retries=2)
    ledger = Ledger(workdir / "ledger.jsonl", cap_usd)
    return Runner(
        workdir,
        ledger,
        anthropic_client=client,
        workspace_id=os.environ.get("ANTHROPIC_WORKSPACE_ID"),
        **kwargs,
    )
