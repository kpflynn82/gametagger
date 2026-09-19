import hashlib
import json
from pathlib import Path

import pytest

from gametagger.evaluation.replay import ExperimentManifest, intake_record, verify_snapshot
from gametagger.identity import validate_identity

MANIFEST = Path(__file__).parents[1] / "experiments/legacy100/manifest.json"


def test_public_manifest_has_all_original_attempts_and_no_payloads():
    raw = json.loads(MANIFEST.read_text())
    m = ExperimentManifest.model_validate(raw)
    assert len(m.files) == 257 and len(m.attempts) == 112
    assert m.baseline_commit == "8a822308cf52c9a43cc9d8bb9dd7110c5ad48c75"
    assert len({a["attempt_id"] for a in m.attempts}) == 112
    assert len({a["record_id"] for a in m.attempts}) == 100
    inventory = json.dumps(raw["files"], sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(inventory).hexdigest() == m.inventory_sha256
    assert all("description" not in f for f in raw["files"])


def test_missing_raw_artifacts_fail_instead_of_being_invented(tmp_path):
    with pytest.raises(ValueError, match="Missing or changed"):
        verify_snapshot(tmp_path, json.loads(MANIFEST.read_text()))


def test_import_preserves_raw_label_and_does_not_make_human_truth():
    raw = dict(
        id=789,
        game_name="Splatterhouse 3",
        primary_genre="Action",
        source_data={
            "store": {
                "product_id": "product:doom3",
                "title": "DOOM 3",
                "description": "Synthetic fixture text; not original source content",
            }
        },
    )
    m, e = intake_record(raw, imported_at="2026-09-18T00:00:00Z")
    assert m.raw_label == "Splatterhouse 3" and m.subject is None
    assert m.record_kind == "unresolved"
    assert m.sources[0].reported_title == "DOOM 3"
    assert m.sources[0].acquired_at is None
    assert validate_identity(m, e).status == "identity_unresolved"


def test_manifest_inventory_tampering_detected(tmp_path):
    raw = json.loads(MANIFEST.read_text())
    raw["files"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="inventory hash"):
        verify_snapshot(tmp_path, raw)
