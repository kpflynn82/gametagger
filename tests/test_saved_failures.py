import json
from decimal import Decimal
from pathlib import Path

from typesafe_sdk import SystemOneResponse

from gametagger.decisions.execution import validate_choice
from gametagger.decisions.jev import JevQuestionCompiler

FIXTURES = Path(__file__).parent / "fixtures"


def test_actual_saved_failures_are_preserved_and_strictly_rejected(taxonomy):
    saved = json.loads((FIXTURES / "legacy100_failures.json").read_text())
    assert len(saved["first_attempt_failures"]) == 12
    assert all(not f["response_body_available"] for f in saved["first_attempt_failures"])
    compiler = JevQuestionCompiler(taxonomy)
    specs = {**compiler.build_specs(), **compiler.build_genre_specs(list(taxonomy.families_by_id))}
    failures = []
    for item in saved["retry_responses"]:
        parsed = SystemOneResponse.model_validate(item["response"])
        # We can compare saved model_dump JSON with SDK reparsing, NOT the missing wire JSON.
        for key, raw in item["response"]["answers"].items():
            assert parsed.answers[key].probabilities == raw["probabilities"]
            _, error = validate_choice(raw, specs[key])
            if error:
                assert error.code == "probability_total"
                assert sum(Decimal(str(p)) for p in raw["probabilities"].values()) == Decimal(".99")
                failures.append((item["path"], key))
    assert failures == [
        ("retry-raw/1101-stage-1.json", "mechanic_ranged_combat"),
        ("retry-raw/1139-stage-1.json", "genre_family"),
        ("retry-raw/972-stage-2.json", "genre:action"),
    ]


def test_problematic_pairs_are_provenance_cases_not_approved_truth():
    cases = json.loads((FIXTURES / "identity_audit_cases.json").read_text())
    assert {c["record_id"] for c in cases} == {789, 381, 1307, 330, 1003}
    assert all(c["review_status"] == "needs_human_review" for c in cases)
    assert all(len(c["provenance_sha256"]) == 64 for c in cases)
    assert cases[0]["raw_label"] == "Splatterhouse 3"
    assert cases[0]["sources"][0]["reported_title"] == "DOOM 3"
