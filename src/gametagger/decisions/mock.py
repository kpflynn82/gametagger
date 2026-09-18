"""Explicitly offline transport fixture; never presented as Jev inference."""

from typesafe_sdk import SystemOneResponse

from gametagger.decisions.jev import QuestionSpec


class MockJevGateway:
    model = "mock-jev-v1"

    def run(self, *, state: str, specs: dict[str, QuestionSpec]) -> SystemOneResponse:
        return SystemOneResponse.model_validate(
            {
                "model": self.model,
                "usage": {},
                "answers": {
                    key: {
                        "type": "choice",
                        "choice": "insufficient_evidence",
                        "confidence": 1.0,
                        "probabilities": {
                            c: float(c == "insufficient_evidence") for c in spec.criteria
                        },
                    }
                    for key, spec in specs.items()
                },
            }
        )
