import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from gametagger.domain import EvidenceItem, EvidenceType, Observation
from gametagger.identity import project_upload_manifest
from gametagger.taxonomy import default_taxonomy_path, load_taxonomy
from gametagger.workspace.contracts import AssetView, ProjectView, RunView, TagView
from gametagger.workspace.media import extract_windows
from gametagger.workspace.store import now


class SpendDisabled(ValueError):
    pass


class ProviderRouter:
    """The real integration is retained, but no local website request can authorize spending."""

    def live(self):
        raise SpendDisabled(
            "Live providers require a separately authorized numeric budget and ledger."
        )

    @staticmethod
    def configured_engine(taxonomy, settings):
        # Integration seam for a future authorized budget executor; never reached by this server.
        from gametagger.decisions.jev import JevDecisionEngine, TypeSafeGateway

        return JevDecisionEngine(taxonomy, TypeSafeGateway(model=settings.typesafe_model))


class Workspace:
    def __init__(self, store):
        self.store = store
        self.taxonomy = load_taxonomy()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-analysis")
        self.lock = threading.Lock()
        self.providers = ProviderRouter()
        self.store.recover()

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=False)

    def asset_view(self, a, run_id=None):
        frames = [
            {k: v for k, v in f.items() if k != "file"}
            | {
                "url": (
                    f"/api/runs/{run_id}/assets/{a['id']}/frames/{i}"
                    if run_id
                    else f"/api/assets/{a['id']}/frames/{i}"
                )
            }
            for i, f in enumerate(a.get("video", {}).get("frames", []))
        ]
        return AssetView(
            id=a["id"],
            name=a["name"],
            kind=a["kind"],
            sha256=a["sha256"],
            bytes=a["bytes"],
            width=a.get("width"),
            height=a.get("height"),
            duration=a.get("duration"),
            url=f"/api/assets/{a['id']}/content",
            frames=frames,
        )

    def project_view(self, p, owner):
        primary = p.get("approved_primary")
        return ProjectView(
            **{
                k: p[k]
                for k in (
                    "id",
                    "title",
                    "release",
                    "platform",
                    "entry",
                    "identity_status",
                    "created_at",
                )
            },
            approved_primary=primary,
            approved_primary_label=self.taxonomy.genres_by_id[primary].display_name
            if primary
            else None,
            review_version=p.get("review_version", 0),
            run_count=sum(r["project_id"] == p["id"] for r in self.store.runs(owner)),
            assets=[self.asset_view(a) for a in self.store.asset_list(p["id"])],
        )

    def run_view(self, r, owner):
        p = self.store.project(r["project_id"], owner)
        with self.store.connect() as db:
            reviews = [
                json.loads(x["body"])
                for x in db.execute(
                    "SELECT body FROM reviews WHERE project_id=? ORDER BY id DESC", (p["id"],)
                )
            ]
        primary = p.get("approved_primary")
        result = r.get("result", {})
        return RunView(
            id=r["id"],
            project_id=p["id"],
            title=p["title"],
            release=p["release"],
            platform=p["platform"],
            mode=r["mode"],
            dataset="demo" if p["entry"] == "demo" else "workspace",
            status=r["status"],
            identity_status=r["snapshot"]["identity_status"],
            created_at=r["created_at"],
            primary_genre=primary,
            primary_label=self.taxonomy.genres_by_id[primary].display_name if primary else None,
            primary_status="Human-approved catalog primary" if primary else "No primary assigned",
            blocker=r.get("error") or result.get("blocker"),
            events=r["events"],
            tags=[
                TagView(
                    id=t.id,
                    label=t.label,
                    category=t.category,
                    execution="not_evaluated",
                    support_status="Not evaluated; no specific support assessed.",
                    human_state=p.get("approved_attributes", {}).get(t.id),
                )
                for t in self.taxonomy.tags
            ],
            observations=result.get("observations", []),
            assets=[self.asset_view(a, r["id"]) for a in r["assets"]],
            provenance=result.get("provenance", {}),
            reviews=reviews,
        )

    def enqueue(self, p, owner, key, mode):
        if mode == "live":
            self.providers.live()
        assets = self.store.asset_list(p["id"])
        snapshot = {k: v for k, v in p.items() if k not in {"approved_primary", "review_version"}}
        digest = hashlib.sha256(
            json.dumps(
                {
                    "project": snapshot,
                    "assets": [
                        {k: v for k, v in a.items() if k not in {"video", "frame_directory"}}
                        for a in assets
                    ],
                    "mode": mode,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with self.lock, self.store.connect() as db:
            existing = db.execute(
                "SELECT input_hash,body FROM runs WHERE owner=? AND idempotency_key=?", (owner, key)
            ).fetchone()
            if existing:
                if existing["input_hash"] != digest:
                    raise ValueError("Idempotency key already used for different inputs")
                return json.loads(existing["body"])
            active = db.execute(
                "SELECT count(*) FROM runs WHERE status NOT IN "
                "('completed','partial','failed','cancelled','interrupted')"
            ).fetchone()[0]
            if active >= 10:
                raise ValueError("Local queue is full (10 jobs)")
            # ISO timestamps use T; parse with SQLite datetime rather than lexical comparison.
            count = db.execute(
                "SELECT count(*) FROM runs WHERE owner=? "
                "AND datetime(created_at)>datetime('now','-1 minute')",
                (owner,),
            ).fetchone()[0]
            if count >= 30:
                raise ValueError("Rate limit: 30 runs per minute")
            r = {
                "id": uuid4().hex,
                "owner": owner,
                "project_id": p["id"],
                "mode": mode,
                "status": "queued",
                "input_hash": digest,
                "created_at": now(),
                "snapshot": snapshot,
                "assets": assets,
                "events": [{"stage": "queued", "at": now()}],
            }
            db.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
                (r["id"], p["id"], owner, key, digest, "queued", json.dumps(r), r["created_at"]),
            )
        self.pool.submit(self.execute, r)
        return r

    def execute(self, r):
        start = perf_counter()
        queue_ms = (
            datetime.now(timezone.utc) - datetime.fromisoformat(r["created_at"])
        ).total_seconds() * 1000

        def stage(name, execution="completed", reason=None):
            current = self.store.run(r["id"], r["owner"])
            if current["status"] == "cancelled":
                raise InterruptedError("Cancelled before next local stage")
            r["status"] = name
            r["events"].append(
                {
                    "stage": name,
                    "at": now(),
                    "elapsed_ms": (perf_counter() - start) * 1000,
                    "execution": execution,
                    "reason": reason,
                }
            )
            self.store.save_run(r)

        try:
            stage("validating_sources")
            p = r["snapshot"]
            stage("preparing_media")
            for a in r["assets"]:
                path = self.store.assets / a["file"]
                if hashlib.sha256(path.read_bytes()).hexdigest() != a["sha256"]:
                    raise ValueError("Saved asset hash mismatch")
                if a["kind"] == "video":
                    used = sum(
                        f.stat().st_size for f in self.store.assets.rglob("*") if f.is_file()
                    )
                    if used + 64 * 1024 * 1024 > 1024 * 1024 * 1024:
                        raise ValueError("Insufficient local media quota for bounded frame output")
                    a["frame_directory"] = a["id"] + "-" + r["id"]
                    a["video"] = extract_windows(path, self.store.assets / a["frame_directory"])
                    with self.store.connect() as db:
                        db.execute("UPDATE assets SET body=? WHERE id=?", (json.dumps(a), a["id"]))
            stage("observing", "documentary_quotes_only", "No visual recognition in offline mode")
            observations = []
            evidence = []
            if p["description"] and p["identity_status"] == "associated_project":
                e = EvidenceItem(
                    id="metadata:" + p["id"],
                    type=EvidenceType.OTHER,
                    source=p["source_label"],
                    metadata={"description": p["description"]},
                    sha256=hashlib.sha256(p["description"].encode()).hexdigest(),
                )
                evidence.append(e)
                observations.append(
                    Observation(
                        id=e.id + ":quote",
                        evidence_id=e.id,
                        text=p["description"],
                        kind="metadata_quote",
                        metadata_key="description",
                        observer_model="exact-source-quote-v1",
                    ).model_dump(mode="json")
                )
            for a in r["assets"]:
                evidence.append(
                    EvidenceItem(
                        id=a["id"],
                        type=EvidenceType.GAMEPLAY_CLIP
                        if a["kind"] == "video"
                        else EvidenceType.GAMEPLAY_IMAGE,
                        source="publisher-upload",
                        sha256=a["sha256"],
                    )
                )
            identity = (
                project_upload_manifest(evidence, p["id"])
                if evidence and p["identity_status"] == "associated_project"
                else None
            )
            stage("classifying", "not_evaluated", "live_budget_disabled")
            # Offline processing never manufactures semantic answers for arbitrary uploads.
            stage("applying_policy")
            r["result"] = {
                "observations": observations,
                "identity": identity.model_dump(mode="json") if identity else None,
                "blocker": "Identity needs review; reference sources were excluded."
                if p["identity_status"] == "unresolved"
                else (
                    "Offline preparation complete. Live analysis is budget-disabled; "
                    "no model genre or attributes were inferred."
                ),
                "provenance": {
                    "execution_mode": "offline-preparation",
                    "input_sha256": r["input_hash"],
                    "code_version": os.getenv("GAMETAGGER_BUILD_SHA", "unrecorded"),
                    "preparation_version": "local-preparation-v1",
                    "decision_prompt_version": None,
                    "taxonomy_version": self.taxonomy.version,
                    "taxonomy_sha256": hashlib.sha256(
                        default_taxonomy_path().read_bytes()
                    ).hexdigest(),
                    "observer": "exact-source-quote-v1; no visual recognition",
                    "decision_model": None,
                    "provider_calls": 0,
                    "usage": None,
                    "end_to_end_latency_ms": (perf_counter() - start) * 1000 + queue_ms,
                    "queue_latency_ms": queue_ms,
                    "latency_scope": "local queued preparation job; excludes upload; no inference",
                    "concurrency": 1,
                    "cache_condition": "uncached media preparation",
                    "evidence_hashes": {e.id: e.sha256 for e in evidence},
                    "context_evidence_ids": [],
                    "prepared_evidence_ids": [e.id for e in evidence],
                    "eligible_evidence_ids": [e.id for e in evidence] if identity else [],
                    "excluded_evidence_ids": [] if identity else [e.id for e in evidence],
                    "support_evidence_ids": [],
                    "video_strategy": "uniform-three-ordered-windows-v1"
                    if any(a["kind"] == "video" for a in r["assets"])
                    else None,
                },
            }
            stage("partial")
        except InterruptedError:
            r["status"] = "cancelled"
            r["events"].append({"stage": "cancelled", "at": now()})
            self.store.save_run(r)
        except Exception as exc:
            r["status"] = "failed"
            r["error"] = "Local processing failed: " + type(exc).__name__
            r["events"].append({"stage": "failed", "at": now()})
            self.store.save_run(r)
