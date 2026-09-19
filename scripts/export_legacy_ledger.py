"""Export only allowlisted numeric/decision fields after immutable snapshot verification.

Titles, URLs, text, observations, credentials, media and raw error messages are excluded.
"""

import argparse
import hashlib
import json
from pathlib import Path

from gametagger.evaluation.replay import verify_snapshot


def build(snapshot: Path, manifest: Path):
    verify_snapshot(snapshot, json.loads(manifest.read_text()))
    rows = []
    for row in json.loads((snapshot / "comparison.json").read_text()):
        rid = str(int(row["analysis_id"]))
        path = snapshot / "results" / (rid + ".json")
        raw = path.read_bytes() if path.exists() else None
        saved = json.loads(raw) if raw else {}
        result = saved.get("result") or {}
        genre = result.get("genre") or {}
        rows.append(
            {
                "id": rid,
                "status": row["status"],
                "comparison": row["comparison"],
                "old_primary_id": row.get("old_canonical_id"),
                "new_primary_id": row.get("new_genre"),
                "source_relationship": "unverified",
                "source_title_flag": bool(row.get("source_title_review")),
                "evidence_available": bool(row.get("evidence_available")),
                "mode": "historical metadata-only replay",
                "human_truth": None,
                "failure_cause": "provider_execution" if row["status"] == "error" else "unreviewed",
                "cause_status": "observed execution error"
                if row["status"] == "error"
                else "proposed; not adjudicated",
                "genre_distributions": genre.get("global_genre_probabilities"),
                "tags": [
                    {k: t[k] for k in ("tag_id", "state", "probabilities", "action")}
                    for t in result.get("tags", [])
                ],
                "result_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.snapshot, args.manifest)
    with args.output.open("x") as handle:
        handle.write(json.dumps(result, separators=(",", ":")) + "\n")
    print(f"Exported {len(result)} redacted records; no source contents.")


if __name__ == "__main__":
    main()
