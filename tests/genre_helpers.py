"""Scripted Jev responses for aggregation tests; no title-based classification logic."""

from typesafe_sdk import SystemOneResponse

from gametagger.decisions.jev import JevDecisionEngine


def distribution(keys, values):
    result = dict.fromkeys(keys, 0.0)
    result.update(values)
    assert abs(sum(result.values()) - 1) < 0.001
    return result


class ScriptedGenreGateway:
    model = "fixture-jev"

    def __init__(self, family, conditional):
        self.family = family
        self.conditional = conditional
        self.calls = []

    def run(self, *, state, specs):
        self.calls.append((state, specs))
        answers = {}
        for key, spec in specs.items():
            values = (
                self.family
                if key == "genre_family"
                else self.conditional.get(
                    key.removeprefix("genre:"), {"insufficient_evidence": 1.0}
                )
            )
            p = distribution(spec.criteria, values)
            answers[key] = {
                "type": "choice",
                "choice": max(p, key=p.get),
                "probabilities": p,
                "confidence": 0.75,
            }
        return SystemOneResponse.model_validate(
            {
                "model": f"fixture-stage-{len(self.calls)}",
                "answers": answers,
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        )


def classify(taxonomy, family, conditional):
    gateway = ScriptedGenreGateway(family, conditional)
    batch = JevDecisionEngine(taxonomy, gateway).decide(
        require_identity=False,
        game_id="anonymous-case",
        game_title=None,
        observations=[],
        blind_media=True,
    )
    return batch, gateway
