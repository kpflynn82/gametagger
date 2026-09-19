"""Synthetic video/response fixtures test contracts only, not recognition quality."""

import hashlib
import json
import subprocess
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from test_workspace import HEAD, project, start

from gametagger.observers.anthropic_ordered import PROMPT_SHA256, PROMPT_VERSION, request_digest
from gametagger.observers.ordered import OrderedWindow, WindowAttempt, WindowOutput, digest
from gametagger.workspace.app import create_app
from gametagger.workspace.media import video_available


@pytest.fixture
def replay_case(tmp_path):
    if not video_available():
        pytest.skip("Local FFmpeg unavailable; no fake video fixture")
    source = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=12",
            "-t",
            "4",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            str(source),
        ],
        check=True,
        timeout=15,
    )
    root = tmp_path / "private"
    with TestClient(create_app(root=root, local_dev=True, role="reviewer")) as client:
        p = project(client)
        uploaded = client.post(
            f"/api/projects/{p['id']}/assets?name=synthetic.mp4&kind=video",
            content=source.read_bytes(),
            headers=HEAD,
        )
        assert uploaded.status_code == 200
        run = start(client, p["id"])
        manifest = client.get(f"/api/runs/{run['id']}/observation-request").json()
        assert len(manifest["windows"]) == 3
        attempts = []
        for i, view in enumerate(manifest["windows"][:2]):
            w = OrderedWindow.model_validate(
                {
                    k: v
                    for k, v in view.items()
                    if k not in {"asset_id", "frame_indices", "window_sha256"}
                }
            )
            out = WindowOutput(
                context="unknown",
                observations=[
                    {
                        "kind": "visual_text",
                        "text": "Merge",
                        "frame_ids": [w.frames[0].evidence_id],
                        "image_region": {"x": 0, "y": 0, "width": 0.5, "height": 0.2},
                    }
                ],
            )
            # Deliberately scripted text (not actually on testsrc), unmistakably illustrative.
            attempts.append(
                WindowAttempt(
                    status="valid" if i == 0 else "error",
                    window_sha256=w.sha256,
                    request_sha256=request_digest(w, "fixture-model"),
                    requested_model="fixture-model",
                    returned_model="fixture-resolved",
                    prompt_version=PROMPT_VERSION,
                    prompt_sha256=PROMPT_SHA256,
                    sdk_version="fixture",
                    response_sha256=digest(out.model_dump(mode="json")),
                    output_sha256=digest(out.model_dump(mode="json")) if i == 0 else None,
                    output=out if i == 0 else None,
                    error_code="observation_contract" if i else None,
                    usage={"input_tokens": 10, "output_tokens": None},
                    latency_ms=12,
                ).model_dump(mode="json")
            )
        bundle = {
            "schema_version": "ordered-observation-replay-v1",
            "kind": "illustrative",
            "input_sha256": manifest["input_sha256"],
            "taxonomy_sha256": manifest["taxonomy_sha256"],
            "attempts": attempts,
        }
        yield client, run, bundle, root


def submit(c, run, bundle, key="saved-replay-key"):
    return c.post(
        f"/api/runs/{run['id']}/observation-replay",
        headers=HEAD,
        json={"idempotency_key": key, "replay": bundle},
    )


def test_valid_partial_replay_is_immutable_durable_and_not_classification(replay_case):
    c, parent, bundle, root = replay_case
    r = submit(c, parent, bundle)
    assert r.status_code == 201, r.text
    child = r.json()
    assert child["id"] != parent["id"] and child["status"] == "partial"
    assert child["mode"] == "observation_replay" and child["dataset"] == "demo"
    assert child["primary_genre"] is None
    assert {e["status"] for e in child["observation_executions"]} == {
        "valid",
        "error",
        "not_evaluated",
    }
    claim = next(o for o in child["observations"] if o["kind"] == "visual_text")
    assert claim["text"] == "Merge" and claim["timestamp_start"] == 0
    assert claim["support_status"] == "Context only; no classification support assessed"
    assert child["provenance"]["provider_calls"] == 0
    assert child["provenance"]["historical_observer_attempts"][1]["usage"]["input_tokens"] == 10
    assert child["provenance"]["usage"] is None
    assert all(t["state"] is None and t["execution"] == "not_evaluated" for t in child["tags"])
    assert submit(c, parent, bundle).json()["id"] == child["id"]
    assert c.get(f"/api/runs/{parent['id']}").json()["observations"] == parent["observations"]
    assert submit(c, child, bundle).status_code == 409
    exported = c.get(f"/api/runs/{child['id']}/export").json()
    assert exported["observations"] == [] and "Merge" not in json.dumps(exported)
    frames = child["assets"][0]["frames"]
    assert hashlib.sha256(c.get(frames[0]["url"]).content).hexdigest() == frames[0]["sha256"]
    # A second process is intentionally not concurrent; Store read verifies disk persistence.
    from gametagger.workspace.store import Store

    assert Store(root).run(child["id"], "local-owner")["observation_replay"] == bundle


def test_mismatched_replays_and_tampered_content_cannot_attach(replay_case):
    c, r, bundle, root = replay_case
    changes = [
        ("input_sha256", "f" * 64),
        ("taxonomy_sha256", "f" * 64),
        ("window_sha256", "f" * 64),
        ("prompt_sha256", "f" * 64),
        ("prompt_version", "different"),
        ("requested_model", "different"),
        ("request_sha256", "f" * 64),
    ]
    for key, value in changes:
        modified = deepcopy(bundle)
        target = modified if key in {"input_sha256", "taxonomy_sha256"} else modified["attempts"][0]
        target[key] = value
        assert submit(c, r, modified).status_code == 409
    bad = deepcopy(bundle)
    bad["attempts"][0]["output"]["observations"][0]["text"] = "Changed"
    assert submit(c, r, bad).status_code == 422  # Structured-output digest retained.
    bad = deepcopy(bundle)
    bad["attempts"][0]["output"]["observations"][0].update(
        kind="visual_fact", text="Souls-like", image_region=None
    )
    bad["attempts"][0]["output_sha256"] = digest(bad["attempts"][0]["output"])
    assert submit(c, r, bad).status_code == 409
    bad = deepcopy(bundle)
    bad["attempts"].append(bad["attempts"][0])
    assert submit(c, r, bad).status_code == 422
    assert len(c.get("/api/runs").json()) == 1
    from gametagger.workspace.store import Store

    store = Store(root)
    a = store.run(r["id"], "local-owner")["assets"][0]
    frame = store.assets / a["frame_directory"] / a["video"]["frames"][0]["file"]
    frame.write_bytes(b"tampered")
    assert submit(c, r, bundle).status_code == 409


def test_replay_roles_identity_and_dataset_remain_separate(replay_case):
    c, r, bundle, root = replay_case
    from gametagger.workspace.store import Store

    store = Store(root)
    # Verify role/owner via independent roots, avoiding a second active workspace instance.
    with TestClient(
        create_app(root=root.parent / "other", local_dev=True, role="viewer")
    ) as viewer:
        assert submit(viewer, r, bundle).status_code == 403
    with TestClient(
        create_app(root=root.parent / "other-owner", local_dev=True, role="reviewer", owner="other")
    ) as other:
        assert submit(other, r, bundle).status_code == 404
    original = store.run(r["id"], "local-owner")
    original["snapshot"]["entry"] = "publisher_project"
    store.save_run(original)
    assert submit(c, r, bundle).status_code == 409
    original["snapshot"]["entry"] = "demo"
    original["snapshot"]["identity_status"] = "unresolved"
    store.save_run(original)
    assert submit(c, r, bundle).status_code == 409
