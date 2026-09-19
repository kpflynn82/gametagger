import io
import json
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from gametagger.workspace.app import create_app

HEAD = {"X-GameTagger-Request": "1"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(root=tmp_path, local_dev=True, role="reviewer")) as c:
        yield c


def project(c, **changes):
    body = {
        "title": "Synthetic test project",
        "entry": "demo",
        "association_confirmed": True,
        "description": "Two shapes appear beside a row of buttons.",
    }
    body.update(changes)
    r = c.post("/api/projects", json=body, headers=HEAD)
    assert r.status_code == 201, r.text
    return r.json()


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (32, 24), "gray").save(output, "PNG")
    return output.getvalue()


def wait(c, rid):
    for _ in range(100):
        r = c.get("/api/runs/" + rid).json()
        if r["status"] in {"partial", "failed", "cancelled", "interrupted"}:
            return r
        time.sleep(0.01)
    pytest.fail("Job did not reach a terminal checkpoint")


def start(c, pid, key="same-input-key"):
    r = c.post("/api/runs", json={"project_id": pid, "idempotency_key": key}, headers=HEAD)
    assert r.status_code == 202, r.text
    return wait(c, r.json()["id"])


def test_upload_run_review_reopen_export_and_demo_isolation(client):
    p = project(client)
    a = client.post(
        f"/api/projects/{p['id']}/assets?name=frame.png", content=image_bytes(), headers=HEAD
    )
    assert a.status_code == 200, a.text
    duplicate = client.post(
        f"/api/projects/{p['id']}/assets?name=other.png", content=image_bytes(), headers=HEAD
    )
    assert duplicate.json()["id"] == a.json()["id"]
    r = start(client, p["id"])
    assert r["status"] == "partial"
    assert r["primary_genre"] is None
    assert all(t["execution"] == "not_evaluated" and t["probabilities"] is None for t in r["tags"])
    assert r["provenance"]["provider_calls"] == 0
    assert client.get("/api/overview").json()["projects"] == 0
    assert client.get("/api/overview?dataset=demo").json()["projects"] == 1
    assert start(client, p["id"])["id"] == r["id"]
    reviewed = client.post(
        f"/api/projects/{p['id']}/reviews",
        headers=HEAD,
        json={
            "kind": "primary",
            "value": "puzzle",
            "reason": "Synthetic fixture approval, not real-world truth",
            "expected_version": 0,
        },
    )
    assert reviewed.status_code == 200
    again = start(client, p["id"], "new-analysis-key")
    assert again["primary_genre"] == "puzzle"
    assert again["primary_status"] == "Human-approved catalog primary"
    assert len(again["reviews"]) == 1
    assert client.get("/api/projects?dataset=demo&genre=puzzle").json()["total"] == 1
    assert (
        client.get("/api/projects?dataset=demo&attribute=mechanic_parry&state=absent").json()[
            "total"
        ]
        == 0
    )
    exported = client.get(f"/api/runs/{r['id']}/export").json()
    assert exported["observations"] == [] and exported["assets"] == []
    assert "Two shapes" not in json.dumps(exported)


def test_identity_unresolved_is_not_a_fallback_and_cannot_publish(client):
    p = project(client, entry="game_reference", reference_url="https://example.com/store")
    r = start(client, p["id"])
    assert r["identity_status"] == "unresolved" and r["primary_genre"] is None
    assert r["observations"] == []
    assert "Identity needs review" in r["blocker"]
    assert (
        client.post(
            f"/api/projects/{p['id']}/reviews",
            headers=HEAD,
            json={
                "kind": "primary",
                "value": "puzzle",
                "reason": "Not authorized identity",
                "expected_version": 0,
            },
        ).status_code
        == 409
    )


def test_fail_closed_auth_origin_host_review_and_spend(tmp_path):
    with TestClient(create_app(root=tmp_path, local_dev=False)) as c:
        assert c.get("/api/capabilities").status_code == 403
    with TestClient(create_app(root=tmp_path, local_dev=True, role="viewer")) as c:
        p = project(c)
        assert c.get("/api/review").status_code == 403
        assert c.get("/api/experiments").status_code == 403
        assert c.post("/api/projects", json={"title": "x"}).status_code == 403
        assert (
            c.post(
                "/api/projects",
                json={"title": "x"},
                headers={**HEAD, "Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert c.get("/api/capabilities", headers={"Host": "evil.example"}).status_code == 403
        assert (
            c.post(
                "/api/runs",
                headers=HEAD,
                json={"project_id": p["id"], "mode": "live", "idempotency_key": "live-test-key"},
            ).status_code
            == 403
        )
        assert (
            c.post(
                f"/api/projects/{p['id']}/reviews",
                headers=HEAD,
                json={
                    "kind": "primary",
                    "value": "puzzle",
                    "reason": "viewer cannot approve",
                    "expected_version": 0,
                },
            ).status_code
            == 403
        )


def test_owner_isolation_and_restart_recovery(tmp_path):
    with TestClient(create_app(root=tmp_path, local_dev=True, owner="alice")) as c:
        p = project(c)
        r = start(c, p["id"])
        w = c.app.state.workspace
        pending = w.store.run(r["id"], "alice")
        pending["status"] = "observing"
        w.store.save_run(pending)
    with TestClient(create_app(root=tmp_path, local_dev=True, owner="bob")) as c:
        assert c.get("/api/projects/" + p["id"]).status_code == 404
        assert c.get("/api/runs/" + r["id"]).status_code == 404
    with TestClient(create_app(root=tmp_path, local_dev=True, owner="alice")) as c:
        restored = c.get("/api/runs/" + r["id"]).json()
        assert restored["status"] == "interrupted"
        assert "Process stopped" in restored["blocker"]


@pytest.mark.parametrize(
    "name,data",
    [
        ("../secret.png", b"x"),
        ("frame.png", b"<html>not an image</html>"),
        ("frame.png", image_bytes() + b"<script>bad()</script>"),
    ],
)
def test_invalid_media_and_traversal(client, name, data):
    p = project(client)
    r = client.post(
        f"/api/projects/{p['id']}/assets", params={"name": name}, content=data, headers=HEAD
    )
    assert r.status_code == 422
    assert client.get("/api/projects/" + p["id"]).json()["assets"] == []


def test_limits_bulk_versions_and_csv_formula(client):
    p = project(client, title="=2+2")
    assert (
        client.post(
            f"/api/projects/{p['id']}/assets",
            content=b"x",
            headers={**HEAD, "Content-Length": str(43 * 1024 * 1024)},
        ).status_code
        == 413
    )
    assert client.post("/api/bulk/dry-run", json=[{}] * 101, headers=HEAD).status_code == 422
    bulk = client.post(
        "/api/bulk/dry-run", json=[{"title": "x"}, {"title": "x"}, {}], headers=HEAD
    ).json()
    assert [r["status"] for r in bulk["rows"]] == [
        "valid_budget_blocked",
        "duplicate_warning",
        "invalid",
    ]
    assert bulk["created"] == 0 and bulk["provider_calls"] == 0
    r = start(client, p["id"])
    assert "'=2+2" in client.get(f"/api/runs/{r['id']}/export?format=csv").text
    review = {
        "kind": "primary",
        "value": "puzzle",
        "reason": "Synthetic reviewed decision",
        "expected_version": 0,
    }
    assert (
        client.post(f"/api/projects/{p['id']}/reviews", json=review, headers=HEAD).status_code
        == 200
    )
    assert (
        client.post(f"/api/projects/{p['id']}/reviews", json=review, headers=HEAD).status_code
        == 409
    )


def test_experiments_are_redacted_unmeasured_and_complete(client):
    r = client.get("/api/experiments").json()
    assert all(m["change"] is None and m["paired_n"] == 0 for m in r["scorecard"])
    assert len(r["case_ledger"]) == 100
    assert sum(c["status"] == "error" for c in r["case_ledger"]) == 3
    assert "description" not in json.dumps(r)
    assert r["recommendation"] == "Inconclusive"


def test_csv_dry_run_and_chunked_body_limit(client):
    r = client.post(
        "/api/bulk/dry-run",
        content="title,platform\nExample,mobile\nExample,mobile",
        headers={**HEAD, "Content-Type": "text/csv"},
    )
    assert r.status_code == 200
    assert [row["status"] for row in r.json()["rows"]] == [
        "valid_budget_blocked",
        "duplicate_warning",
    ]
    assert client.post("/api/bulk/dry-run", content="{invalid", headers=HEAD).status_code == 422
    chunks = (b"x" * 500_000 for _ in range(3))
    assert client.post("/api/projects", content=chunks, headers=HEAD).status_code == 413


def test_changed_asset_fails_explicitly_without_semantic_answers(client):
    p = project(client)
    a = client.post(
        f"/api/projects/{p['id']}/assets?name=frame.png", content=image_bytes(), headers=HEAD
    ).json()
    root = client.app.state.workspace.store.assets
    (root / (a["id"] + ".bin")).write_bytes(b"tampered after intake")
    r = start(client, p["id"])
    assert r["status"] == "failed"
    assert "ValueError" in r["blocker"]
    assert r["primary_genre"] is None
    assert all(t["state"] is None and t["probabilities"] is None for t in r["tags"])


def test_filtered_catalog_export_is_scoped_and_redacted(client):
    project(client, title="=1+1", entry="demo", platform="mobile")
    project(client, title="Workspace project", entry="publisher_project", platform="pc")
    value = client.get("/api/catalog/export?dataset=demo&platform=mobile").json()
    assert len(value["records"]) == 1 and value["records"][0]["title"] == "=1+1"
    assert "description" not in str(value) and "assets" not in str(value)
    csv = client.get("/api/catalog/export?dataset=demo&format=csv").text
    assert "'=1+1" in csv and "Workspace project" not in csv


def test_full_asset_set_still_deduplicates_and_refuses_a_ninth(client):
    p = project(client)
    for i in range(8):
        out = io.BytesIO()
        Image.new("RGB", (8, 8), (i, 0, 0)).save(out, "PNG")
        r = client.post(
            f"/api/projects/{p['id']}/assets?name=synthetic.png",
            content=out.getvalue(),
            headers=HEAD,
        )
        assert r.status_code == 200
    same = client.post(
        f"/api/projects/{p['id']}/assets?name=duplicate.png", content=out.getvalue(), headers=HEAD
    )
    assert same.status_code == 200
    excess = client.post(
        f"/api/projects/{p['id']}/assets?name=ninth.png", content=image_bytes(), headers=HEAD
    )
    assert excess.status_code == 409
    assert len(client.get("/api/projects/" + p["id"]).json()["assets"]) == 8
