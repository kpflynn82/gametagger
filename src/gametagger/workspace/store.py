"""Schema-v1 migration and scoped local storage. No connection to legacy databases."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES (1);
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assets (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), owner TEXT NOT NULL,
 idempotency_key TEXT NOT NULL, input_hash TEXT NOT NULL, status TEXT NOT NULL,
 body TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(owner,idempotency_key));
CREATE TABLE IF NOT EXISTS reviews (
 id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
 owner TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id);
CREATE INDEX IF NOT EXISTS idx_reviews_project ON reviews(project_id);
"""


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.assets = self.root / "assets"
        self.assets.mkdir(exist_ok=True, mode=0o700)
        self.path = self.root / "workspace.sqlite3"
        with self.connect() as db:
            db.executescript(SCHEMA)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def project(self, project_id, owner):
        with self.connect() as db:
            row = db.execute(
                "SELECT body FROM projects WHERE id=? AND owner=?", (project_id, owner)
            ).fetchone()
        if not row:
            return None
        return json.loads(row["body"])

    def list_projects(self, owner):
        with self.connect() as db:
            return [
                json.loads(r["body"])
                for r in db.execute(
                    "SELECT body FROM projects WHERE owner=? ORDER BY created_at DESC", (owner,)
                )
            ]

    def asset_list(self, pid):
        with self.connect() as db:
            return [
                json.loads(r["body"])
                for r in db.execute("SELECT body FROM assets WHERE project_id=?", (pid,))
            ]

    def run(self, rid, owner):
        with self.connect() as db:
            row = db.execute(
                "SELECT body FROM runs WHERE id=? AND owner=?", (rid, owner)
            ).fetchone()
        return json.loads(row["body"]) if row else None

    def runs(self, owner):
        with self.connect() as db:
            return [
                json.loads(r["body"])
                for r in db.execute(
                    "SELECT body FROM runs WHERE owner=? ORDER BY created_at DESC", (owner,)
                )
            ]

    def save_run(self, r):
        with self.connect() as db:
            db.execute(
                "UPDATE runs SET status=?,body=? WHERE id=? "
                "AND (status!='cancelled' OR ?='cancelled')",
                (r["status"], json.dumps(r), r["id"], r["status"]),
            )

    def recover(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT body FROM runs WHERE status NOT IN "
                "('completed','partial','failed','cancelled','interrupted')"
            ).fetchall()
            for row in rows:
                r = json.loads(row["body"])
                r["status"] = "interrupted"
                r["error"] = "Process stopped before completion; create a new offline run to retry."
                r["events"].append({"stage": "interrupted", "at": now()})
                db.execute(
                    "UPDATE runs SET status=?,body=? WHERE id=?",
                    ("interrupted", json.dumps(r), r["id"]),
                )
