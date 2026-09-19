"""Validate independent questions before accepting them; retry only missing/invalid work."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, ValidationError
from typesafe_sdk import ChoiceAnswer

from gametagger.domain import ExecutionError, QuestionExecution, RequestAttempt
from gametagger.identity import digest


class RawEnvelope(BaseModel):
    # Keep answers unparsed until they can be validated independently.
    model_config = ConfigDict(extra="allow")
    model: object = None
    answers: object = None
    usage: object = None


def validate_choice(raw, spec) -> tuple[ChoiceAnswer | None, ExecutionError | None]:
    def error(code, message):
        return None, ExecutionError(code=code, message=message)

    if not isinstance(raw, dict) or raw.get("type") != "choice":
        return error("answer_shape", "Missing or malformed Choice answer")
    p = raw.get("probabilities")
    if not isinstance(p, dict) or set(p) != set(spec.criteria):
        return error("option_set", "Missing or unexpected probability options")
    if any(
        type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in p.values()
    ):
        return error("probability_range", "Probabilities must be finite numbers in [0,1]")
    total = math.fsum(p.values())
    if not math.isclose(total, 1.0, rel_tol=0, abs_tol=0.001):
        return error("probability_total", f"Probability total {total:.12g} exceeds tolerance 0.001")
    choice = raw.get("choice")
    if not isinstance(choice, str) or choice not in p or p[choice] < max(p.values()):
        return error("selected_option", "Selected option must have maximal probability")
    confidence = raw.get("confidence")
    if (
        type(confidence) not in (int, float)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        return error("confidence", "Invalid confidence")
    try:
        return ChoiceAnswer.model_validate(raw), None
    except ValidationError:
        return error("answer_shape", "Malformed Choice answer")


def envelope_error(raw, requested, pinned=None):
    if not isinstance(raw, dict) or not isinstance(raw.get("model"), str) or not raw["model"]:
        return "Missing model in response envelope"
    if pinned and raw["model"] != pinned:
        return "Returned model differs from pinned version"
    if not isinstance(raw.get("answers"), dict) or set(raw["answers"]) - set(requested):
        return "Malformed answers mapping or unsolicited question IDs"
    usage = raw.get("usage")
    if not isinstance(usage, dict) or any(
        usage.get(k) is not None and (type(usage[k]) is not int or usage[k] < 0)
        for k in ("input_tokens", "output_tokens")
    ):
        return "Malformed or missing usage envelope"
    return None


class QuestionExecutor:
    def __init__(self, gateway, *, max_attempts=2):
        if not 1 <= max_attempts <= 3:
            raise ValueError("Bounded retry budget must be between one and three attempts")
        self.gateway, self.max_attempts = gateway, max_attempts
        self.attempts = []
        self.pinned_model = None
        # Duck-typed fixtures are supported, but do not pretend they honor pinning.
        self.can_pin = callable(getattr(type(gateway), "run_pinned", None))

    def execute(self, specs, states, *, stage, evidence_ids):
        outcomes = {}
        groups = defaultdict(dict)
        for key, spec in specs.items():
            if key not in states:
                outcomes[key] = QuestionExecution(
                    status="not_evaluated",
                    error=ExecutionError(
                        code="no_eligible_source",
                        message="No identity-eligible source for this property",
                    ),
                )
            else:
                groups[states[key]][key] = spec
        for state, group in groups.items():
            pending = dict(group)
            fixed_specs = {k: digest(vars(s)) for k, s in group.items()}
            for ordinal in range(1, self.max_attempts + 1):
                attempt_id = str(uuid4())
                requested_model = self.pinned_model or self.gateway.model
                was_pinned = self.pinned_model is not None
                start, started = perf_counter(), datetime.now(timezone.utc)
                raw, error, usage, returned, retryable = None, None, None, None, True
                try:
                    if any(digest(vars(s)) != fixed_specs[k] for k, s in pending.items()):
                        raise ValueError("Question specification changed during retry")
                    if self.can_pin:
                        response = self.gateway.run_pinned(
                            state=state, specs=pending, model=requested_model
                        )
                    else:
                        response = self.gateway.run(state=state, specs=pending)
                    raw = (
                        response
                        if isinstance(response, dict)
                        else response.model_dump(mode="python")
                    )
                    if any(digest(vars(s)) != fixed_specs[k] for k, s in pending.items()):
                        raise ValueError("Question specification changed during request")
                    # Reported usage is operational data even when another envelope field fails.
                    if isinstance(raw, dict):
                        returned = raw.get("model") if isinstance(raw.get("model"), str) else None
                        counts = raw.get("usage")
                        if isinstance(counts, dict) and all(
                            counts.get(k) is None or (type(counts[k]) is int and counts[k] >= 0)
                            for k in ("input_tokens", "output_tokens")
                        ):
                            usage = counts
                    reason = envelope_error(
                        raw, pending, self.pinned_model if self.can_pin else None
                    )
                    if reason:
                        error = ExecutionError(code="envelope", message=reason)
                    else:
                        if (
                            self.can_pin
                            and self.pinned_model is None
                            and not returned.endswith("-latest")
                        ):
                            self.pinned_model = returned
                except Exception as exc:
                    # Exception bodies can contain credentials/context. Never echo them.
                    status = getattr(exc, "status", None)
                    auth = status in (401, 403)
                    error = ExecutionError(
                        code="authentication" if auth else "transport_or_envelope",
                        message=f"{type(exc).__name__}; HTTP status {status}; details withheld",
                    )
                    retryable = not auth
                failed = {}
                for key, spec in pending.items():
                    answer, failure = (
                        (None, error) if error else validate_choice(raw["answers"].get(key), spec)
                    )
                    if failure:
                        failed[key] = failure
                        outcomes[key] = QuestionExecution(
                            status="error",
                            error=failure,
                            context_evidence_ids=evidence_ids.get(key, []),
                        )
                    else:
                        outcomes[key] = QuestionExecution(
                            status="valid",
                            answer=answer.model_dump(),
                            model=returned,
                            selected_attempt_id=attempt_id,
                            context_evidence_ids=evidence_ids.get(key, []),
                        )
                wire = getattr(self.gateway, "last_transport", {}) if self.can_pin else {}
                self.attempts.append(
                    RequestAttempt(
                        id=attempt_id,
                        stage=stage,
                        ordinal=ordinal,
                        question_ids=list(pending),
                        evidence_hash=digest(state),
                        spec_hashes={k: fixed_specs[k] for k in pending},
                        requested_model=requested_model,
                        returned_model=returned,
                        pinning=(
                            "requested-version"
                            if was_pinned
                            else "resolved-after-response"
                            if self.pinned_model
                            else "unavailable"
                        ),
                        started_at=started,
                        latency_ms=(perf_counter() - start) * 1000,
                        usage=usage,
                        error=error,
                        question_errors=failed,
                        raw_answers=raw.get("answers")
                        if isinstance(raw, dict) and isinstance(raw.get("answers"), dict)
                        else None,
                        response_sha256=wire.get("response_sha256")
                        or (digest(raw) if raw else None),
                        request_id_sha256=wire.get("request_id_sha256"),
                        response_representation=wire.get("representation", "sdk_parsed"),
                    )
                )
                pending = {k: s for k, s in pending.items() if k in failed}
                if not pending or not retryable:
                    break
        return outcomes

    def usage_total(self, stage=None):
        attempts = [a for a in self.attempts if stage is None or a.stage == stage]
        return {
            key: sum(a.usage[key] for a in attempts)
            if attempts
            and all(a.usage is not None and a.usage.get(key) is not None for a in attempts)
            else None
            for key in ("input_tokens", "output_tokens")
        }
