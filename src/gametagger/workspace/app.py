import csv
import hashlib
import io
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from gametagger.workspace.contracts import (
    Capabilities,
    CatalogPage,
    ProjectCreate,
    ProjectView,
    ReviewCreate,
    RunCreate,
    RunView,
)
from gametagger.workspace.experiments import ComparisonReport
from gametagger.workspace.media import inspect_image, inspect_video, video_available
from gametagger.workspace.service import SpendDisabled, Workspace
from gametagger.workspace.store import Store, now

REPO = Path(__file__).resolve().parents[3]


def safe_csv(value):
    s = str(value if value is not None else "")
    return "'" + s if s.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else s


def create_app(*, root=None, local_dev=None, role=None, owner="local-owner"):
    enabled = local_dev if local_dev is not None else os.getenv("GAMETAGGER_LOCAL_DEV") == "1"
    selected_role = role or os.getenv("GAMETAGGER_LOCAL_ROLE", "viewer")
    path = Path(root or os.getenv("GAMETAGGER_DATA_DIR", str(REPO / ".local")))
    # No filesystem initialization until explicitly enabled.
    workspace = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal workspace
        if enabled:
            workspace = Workspace(Store(path))
        app.state.workspace = workspace
        yield
        if workspace:
            workspace.close()

    app = FastAPI(title="GameTagger local workspace", version="0.2.0", lifespan=lifespan)

    @app.middleware("http")
    async def local_boundary(request, call_next):
        peer = request.client.host if request.client else ""
        host = request.headers.get("host", "").split(":")[0]
        if (
            not enabled
            or peer not in {"127.0.0.1", "::1", "testclient"}
            or host not in {"127.0.0.1", "localhost", "testserver"}
        ):
            return JSONResponse(
                {"detail": "Private localhost mode is not enabled for this request."},
                status_code=403,
            )
        origin = request.headers.get("origin")
        if origin and origin not in {
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        }:
            return JSONResponse({"detail": "Origin not permitted"}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("x-gametagger-request") != "1":
                return JSONResponse(
                    {"detail": "Same-origin request header required"}, status_code=403
                )
            limit = (
                42 * 1024 * 1024
                if re.fullmatch("/api/projects/[a-f0-9]+/assets", request.url.path)
                else 1_000_000
            )
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "Invalid content length"}, status_code=400)
            if length > limit:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not re.fullmatch(
            "/api/projects/[a-f0-9]+/assets", request.url.path
        ):
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 1_000_000:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
            request._body = bytes(body)  # Starlette cached request, replayed to the route parser.
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    def ws():
        if not workspace:
            raise HTTPException(503, "Workspace has not started")
        return workspace

    def reviewer():
        if selected_role != "reviewer":
            raise HTTPException(403, "Reviewer role required")

    def project(pid):
        p = ws().store.project(pid, owner)
        if not p:
            raise HTTPException(404, "Project not found")
        return p

    def run(rid):
        r = ws().store.run(rid, owner)
        if not r:
            raise HTTPException(404, "Run not found")
        return r

    def asset(aid):
        with ws().store.connect() as db:
            row = db.execute(
                "SELECT a.body FROM assets a JOIN projects p ON p.id=a.project_id "
                "WHERE a.id=? AND p.owner=?",
                (aid, owner),
            ).fetchone()
        if not row:
            raise HTTPException(404, "Asset not found")
        return json.loads(row["body"])

    @app.get("/api/capabilities", response_model=Capabilities)
    def capabilities():
        return Capabilities(
            user=owner,
            role=selected_role,
            video=video_available(),
            providers={
                "jev_key_present": bool(os.getenv("TYPESAFE_API_KEY")),
                "observer_key_present": bool(os.getenv("ANTHROPIC_API_KEY")),
            },
        )

    @app.get("/api/taxonomy")
    def taxonomy():
        t = ws().taxonomy
        return {
            "version": t.version,
            "families": [asdict(f) for f in t.genre_families],
            "tags": [asdict(t) for t in t.tags],
        }

    @app.get("/api/overview")
    def overview(dataset: str = "workspace"):
        demo = dataset == "demo"
        projects = [p for p in ws().store.list_projects(owner) if (p["entry"] == "demo") == demo]
        ids = {p["id"] for p in projects}
        runs = [r for r in ws().store.runs(owner) if r["project_id"] in ids]
        return {
            "projects": len(projects),
            "releases": len(projects),
            "runs": len(runs),
            "published": sum(bool(p.get("approved_primary")) for p in projects),
            "review_count": sum(not p.get("approved_primary") for p in projects),
            "status_counts": {
                s: sum(r["status"] == s for r in runs)
                for s in ["completed", "partial", "failed", "interrupted", "queued"]
            },
            "recent": [ws().run_view(r, owner) for r in runs[:5]],
            "dataset": dataset,
        }

    @app.post("/api/projects", response_model=ProjectView, status_code=201)
    def add_project(data: ProjectCreate):
        if data.reference_url and not data.reference_url.startswith(("https://", "http://")):
            raise HTTPException(422, "Reference must be an HTTP(S) URL; it will not be fetched")
        if len(ws().store.list_projects(owner)) >= 1000:
            raise HTTPException(409, "Local limit: 1000 projects")
        p = data.model_dump() | {
            "id": uuid4().hex,
            "created_at": now(),
            "review_version": 0,
            "identity_status": "associated_project"
            if data.association_confirmed and data.entry != "game_reference"
            else "unresolved",
        }
        with ws().store.connect() as db:
            db.execute(
                "INSERT INTO projects VALUES (?,?,?,?)",
                (p["id"], owner, json.dumps(p), p["created_at"]),
            )
        return ws().project_view(p, owner)

    @app.get("/api/projects", response_model=CatalogPage)
    def catalog(
        q: str = "",
        platform: str = "",
        genre: str = "",
        family: str = "",
        review: str = "",
        input_type: str = "",
        attribute: str = "",
        state: str = "present",
        dataset: str = "workspace",
        page: int = 1,
        page_size: int = 12,
        sort: str = "newest",
        after: str = "",
    ):
        if not 1 <= page <= 10000 or not 1 <= page_size <= 100:
            raise HTTPException(422, "Invalid pagination")
        items = []
        for p in ws().store.list_projects(owner):
            if (p["entry"] == "demo") != (dataset == "demo"):
                continue
            if q.casefold() not in (p["title"] + " " + p["release"]).casefold():
                continue
            if platform and p["platform"] != platform:
                continue
            if genre and p.get("approved_primary") != genre:
                continue
            g = ws().taxonomy.genres_by_id.get(p.get("approved_primary"))
            if family and (not g or g.family != family):
                continue
            if review == "approved" and not g:
                continue
            if review == "pending" and g:
                continue
            if input_type and not any(
                a["kind"] == input_type for a in ws().store.asset_list(p["id"])
            ):
                continue
            if after and p["created_at"][:10] < after:
                continue
            if attribute and p.get("approved_attributes", {}).get(attribute) != state:
                continue
            items.append(ws().project_view(p, owner))
        if sort == "title":
            items.sort(key=lambda p: p.title.casefold())
        return CatalogPage(
            items=items[(page - 1) * page_size : page * page_size],
            total=len(items),
            page=page,
            page_size=page_size,
        )

    @app.get("/api/catalog/export")
    def export_catalog(request: Request, format: str = "json"):
        params = dict(request.query_params)
        for key in ("format", "page", "page_size"):
            params.pop(key, None)
        if set(params) - {
            "q",
            "platform",
            "genre",
            "family",
            "review",
            "input_type",
            "attribute",
            "state",
            "dataset",
            "sort",
            "after",
        }:
            raise HTTPException(422, "Unknown catalog filter")
        selected = []
        for page in range(1, 11):
            result = catalog(**params, page=page, page_size=100)
            selected.extend(result.items)
            if page * 100 >= result.total:
                break
        keys = (
            "id",
            "title",
            "release",
            "platform",
            "approved_primary",
            "approved_primary_label",
            "identity_status",
            "review_version",
            "run_count",
        )
        rows = [{k: p.model_dump()[k] for k in keys} for p in selected]
        if format == "json":
            content, media = json.dumps({"filters": params, "records": rows}), "application/json"
        elif format == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(keys)
            for row in rows:
                writer.writerow([safe_csv(row[k]) for k in keys])
            content, media = buf.getvalue(), "text/csv"
        else:
            raise HTTPException(422, "Choose json or csv")
        return Response(
            content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="gametagger-catalog.{format}"'},
        )

    @app.get("/api/projects/{pid}", response_model=ProjectView)
    def get_project(pid: str):
        return ws().project_view(project(pid), owner)

    @app.post("/api/projects/{pid}/assets")
    async def upload(pid: str, request: Request, name: str = "upload", kind: str = "image"):
        project(pid)
        if kind not in {"image", "video"}:
            raise HTTPException(422, "Unsupported media type")
        if len(ws().store.asset_list(pid)) >= 8:
            raise HTTPException(409, "Limit: 8 assets per project")
        if "/" in name or "\\" in name or ".." in name or len(name) > 200:
            raise HTTPException(422, "Unsafe filename")
        limit = 5 * 1024 * 1024 if kind == "image" else 40 * 1024 * 1024
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > limit:
                raise HTTPException(413, "Media exceeds configured size limit")
        used = sum(p.stat().st_size for p in ws().store.assets.rglob("*") if p.is_file())
        if used + len(data) > 1024 * 1024 * 1024:
            raise HTTPException(413, "Local asset quota: 1 GiB")
        sha = hashlib.sha256(data).hexdigest()
        for a in ws().store.asset_list(pid):
            if a["sha256"] == sha:
                return ws().asset_view(a)
        aid = uuid4().hex
        file = aid + (".bin" if kind == "image" else ".mp4")
        path = ws().store.assets / file
        path.write_bytes(data)
        path.chmod(0o600)
        try:
            if kind == "image":
                width, height, preview = inspect_image(bytes(data))
                duration = None
                (ws().store.assets / (aid + ".jpg")).write_bytes(preview)
            else:
                duration, width, height = inspect_video(path)
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(422, "Invalid media: " + type(exc).__name__) from exc
        a = {
            "id": aid,
            "project_id": pid,
            "name": name,
            "kind": kind,
            "sha256": sha,
            "bytes": len(data),
            "file": file,
            "width": width,
            "height": height,
            "duration": duration,
        }
        with ws().store.connect() as db:
            db.execute("INSERT INTO assets VALUES (?,?,?)", (aid, pid, json.dumps(a)))
        return ws().asset_view(a)

    @app.get("/api/assets/{aid}/content")
    def media(aid: str):
        a = asset(aid)
        file = a["file"] if a["kind"] == "video" else aid + ".jpg"
        return FileResponse(
            ws().store.assets / file,
            media_type="video/mp4" if a["kind"] == "video" else "image/jpeg",
        )

    @app.get("/api/assets/{aid}/frames/{index}")
    def frame(aid: str, index: int):
        a = asset(aid)
        frames = a.get("video", {}).get("frames", [])
        if index < 0 or index >= len(frames):
            raise HTTPException(404, "Frame not found")
        return FileResponse(
            ws().store.assets / a["frame_directory"] / frames[index]["file"],
            media_type="image/jpeg",
        )

    @app.get("/api/runs/{rid}/assets/{aid}/frames/{index}")
    def run_frame(rid: str, aid: str, index: int):
        r = run(rid)
        a = next((a for a in r["assets"] if a["id"] == aid), None)
        frames = a.get("video", {}).get("frames", []) if a else []
        if index < 0 or index >= len(frames):
            raise HTTPException(404, "Frame not found")
        return FileResponse(
            ws().store.assets / a["frame_directory"] / frames[index]["file"],
            media_type="image/jpeg",
        )

    @app.post("/api/runs", response_model=RunView, status_code=202)
    def create_run(data: RunCreate):
        try:
            r = ws().enqueue(project(data.project_id), owner, data.idempotency_key, data.mode)
        except SpendDisabled as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return ws().run_view(r, owner)

    @app.get("/api/runs", response_model=list[RunView])
    def history(project_id: str | None = None):
        return [
            ws().run_view(r, owner)
            for r in ws().store.runs(owner)
            if not project_id or r["project_id"] == project_id
        ][:100]

    @app.get("/api/runs/{rid}", response_model=RunView)
    def get_run(rid: str):
        return ws().run_view(run(rid), owner)

    @app.post("/api/runs/{rid}/cancel", response_model=RunView)
    def cancel(rid: str):
        r = run(rid)
        if r["status"] not in {"completed", "partial", "failed", "interrupted", "cancelled"}:
            r["status"] = "cancelled"
            r["events"].append({"stage": "cancelled", "at": now()})
            ws().store.save_run(r)
        return ws().run_view(r, owner)

    @app.get("/api/runs/{rid}/export")
    def export(rid: str, format: str = "json"):
        value = ws().run_view(run(rid), owner).model_dump(mode="json")
        # Export no raw source text, paths, media, provider payloads or secret-bearing errors.
        value["observations"] = []
        value["assets"] = []
        value["reviews"] = []
        if format == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                ["game", "release", "primary", "status", "tag", "semantic_state", "execution"]
            )
            for t in value["tags"]:
                writer.writerow(
                    map(
                        safe_csv,
                        [
                            value["title"],
                            value["release"],
                            value["primary_label"],
                            value["status"],
                            t["label"],
                            t["state"],
                            t["execution"],
                        ],
                    )
                )
            content = buf.getvalue()
            media = "text/csv"
            ext = "csv"
        elif format == "json":
            content = json.dumps(value, indent=2)
            media = "application/json"
            ext = "json"
        else:
            raise HTTPException(422, "Choose json or csv")
        return Response(
            content,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="gametagger-{rid}.{ext}"'},
        )

    @app.get("/api/review")
    def queue():
        reviewer()
        return {
            "identity": [
                ws().project_view(p, owner)
                for p in ws().store.list_projects(owner)
                if p["identity_status"] == "unresolved"
            ],
            "genre": [
                ws().project_view(p, owner)
                for p in ws().store.list_projects(owner)
                if not p.get("approved_primary")
            ],
            "execution": [
                ws().run_view(r, owner)
                for r in ws().store.runs(owner)
                if r["status"] in {"partial", "failed", "interrupted"}
            ],
            "attributes": [],
        }

    @app.post("/api/projects/{pid}/reviews", response_model=ProjectView)
    def review(pid: str, data: ReviewCreate):
        reviewer()
        project(pid)
        with ws().store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            p = json.loads(
                db.execute(
                    "SELECT body FROM projects WHERE id=? AND owner=?", (pid, owner)
                ).fetchone()["body"]
            )
            if p.get("review_version", 0) != data.expected_version:
                raise HTTPException(409, "Review changed; reload before saving")
            before = {
                k: p.get(k) for k in ("identity_status", "approved_primary", "approved_attributes")
            }
            if data.kind == "identity":
                if data.value != "associated_project":
                    raise HTTPException(422, "Only explicit project association is supported here")
                p["identity_status"] = "associated_project"
            elif data.kind == "primary":
                if p["identity_status"] != "associated_project":
                    raise HTTPException(409, "Resolve identity before publishing")
                if data.value not in ws().taxonomy.genres_by_id:
                    raise HTTPException(422, "Choose a canonical primary genre")
                p["approved_primary"] = data.value
            else:
                if p["identity_status"] != "associated_project":
                    raise HTTPException(409, "Resolve identity before approving attributes")
                if data.property_id not in ws().taxonomy.tags_by_id or data.value not in {
                    "present",
                    "absent",
                    "insufficient_evidence",
                    "conflicting_evidence",
                }:
                    raise HTTPException(422, "Invalid attribute decision")
                p.setdefault("approved_attributes", {})[data.property_id] = data.value
            p["review_version"] = p.get("review_version", 0) + 1
            audit = {
                "version": p["review_version"],
                "reviewer": owner,
                "role": selected_role,
                "kind": data.kind,
                "property_id": data.property_id,
                "before": before,
                "after": data.value,
                "reason": data.reason,
                "at": now(),
            }
            db.execute(
                "INSERT INTO reviews(project_id,owner,body,created_at) VALUES(?,?,?,?)",
                (pid, owner, json.dumps(audit), now()),
            )
            db.execute("UPDATE projects SET body=? WHERE id=?", (json.dumps(p), pid))
        return ws().project_view(p, owner)

    @app.post("/api/bulk/dry-run")
    async def bulk(request: Request):
        reviewer()
        try:
            if request.headers.get("content-type", "").split(";")[0] == "text/csv":
                data = list(csv.DictReader(io.StringIO((await request.body()).decode("utf-8-sig"))))
            else:
                data = await request.json()
        except (ValueError, UnicodeError, csv.Error) as exc:
            raise HTTPException(422, "Malformed CSV/JSON manifest") from exc
        if not isinstance(data, list) or len(data) > 100:
            raise HTTPException(422, "Supply at most 100 CSV/JSON rows")
        seen = set()
        rows = []
        for index, item in enumerate(data):
            try:
                p = ProjectCreate.model_validate(item)
                label = p.title.casefold()
                rows.append(
                    {
                        "row": index + 1,
                        "title": p.title,
                        "status": "duplicate_warning" if label in seen else "valid_budget_blocked",
                        "message": "Validated only; no record created and no provider called.",
                    }
                )
                seen.add(label)
            except Exception:
                rows.append(
                    {
                        "row": index + 1,
                        "status": "invalid",
                        "message": "Row does not match project contract",
                    }
                )
        return {"rows": rows, "provider_calls": 0, "created": 0}

    @app.get("/api/roadmap")
    def roadmap():
        reviewer()
        return json.loads((REPO / "docs/execution-status.json").read_text())

    @app.get("/api/experiments")
    def experiments():
        reviewer()
        audit = json.loads((REPO / "experiments/legacy100/pr_b_audit.json").read_text())
        original = json.loads((REPO / "experiments/legacy100/manifest.json").read_text())
        reports, report_errors = [], []
        for saved in sorted((ws().store.root / "reports").glob("*.json"))[:20]:
            try:
                if saved.stat().st_size > 2_000_000:
                    raise ValueError("Report exceeds size limit")
                reports.append(ComparisonReport.model_validate_json(saved.read_bytes()).view())
            except (ValueError, OSError):
                report_errors.append("A saved report failed validation; excluded from scorecards.")
        return {
            "reports": reports,
            "report_errors": report_errors,
            "case_ledger": json.loads(
                (REPO / "experiments/legacy100/case-ledger.json").read_text()
            ),
            "recommendation": "Inconclusive",
            "reason": (
                "No matched, human-reviewed comparison exists. Jev effectiveness is not measured."
            ),
            "scorecard": [
                {
                    "metric": m,
                    "baseline": None,
                    "candidate": None,
                    "change": None,
                    "paired_n": 0,
                    "status": "Not measured",
                }
                for m in [
                    "Actual primary correctness",
                    "Accepted attribute precision",
                    "End-to-end recall",
                    "Useful coverage",
                    "Median total latency",
                    "p95 total latency",
                    "Cost per useful result",
                    "Execution error rate",
                ]
            ],
            "historical": {
                k: audit[k]
                for k in (
                    "records",
                    "new_outcomes_all_tags",
                    "operational",
                    "per_tag",
                    "text_bearing_abstentions",
                    "source_title_review_flags",
                )
            },
            "provenance": {
                k: original[k]
                for k in (
                    "baseline_commit",
                    "taxonomy_sha256",
                    "decision_prompt_version",
                    "model",
                    "sdk_version",
                    "inventory_sha256",
                )
            },
            "comparisons": [],
            "clean_pilot": json.loads((REPO / "experiments/clean30/manifest.json").read_text()),
        }

    build = REPO / "frontend/dist"
    if build.exists():
        app.mount("/assets", StaticFiles(directory=build / "assets"), name="static-assets")

        @app.get("/{page:path}", include_in_schema=False)
        def frontend(page: str):
            if page.startswith("api/"):
                raise HTTPException(404, "Endpoint not found")
            return FileResponse(build / "index.html")

    return app


app = create_app()
