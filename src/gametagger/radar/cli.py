"""gametagger-radar: find test-market games worth tearing down, and propose a build.

    gametagger-radar scan --charts-file reading.json        # score a saved chart reading
    gametagger-radar scan --live --limit 100                # read CA/AU/NZ charts now (free)
    gametagger-radar approve gp-com.studio.game             # queue a game for a deep dive

``scan`` makes no paid model calls and downloads no games; it only reads public chart positions.
The output is a ranked shortlist and a one-line morning push. ``approve`` records the owner's go
for the Mac-side teardown; it does not run one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gametagger.radar.brief import (
    BriefedCandidate,
    build_proposal,
    render_push,
    render_shortlist_md,
)
from gametagger.radar.candidate import RegionChart, merge_candidates
from gametagger.radar.catalogue import load_catalogue
from gametagger.radar.signals import SignalWeights, score_candidate
from gametagger.radar.trends import load_hot_terms


def _chart_to_dict(c: RegionChart) -> dict:
    return {
        "region": c.region,
        "store": c.store,
        "kind": c.kind,
        "chart_date": c.chart_date,
        "rows": {k: list(v) for k, v in c.rows.items()},
    }


def _chart_from_dict(d: dict) -> RegionChart:
    return RegionChart(
        region=d["region"],
        store=d["store"],
        kind=d["kind"],
        chart_date=d.get("chart_date"),
        rows={k: (v[0], v[1], v[2] if len(v) > 2 else None) for k, v in d.get("rows", {}).items()},
    )


def _load_charts(args) -> list[RegionChart]:
    if args.charts_file:
        data = json.loads(Path(args.charts_file).read_text())
        return [_chart_from_dict(d) for d in data]
    if args.live:
        from gametagger.radar.charts_multi import read_test_market_charts

        errors: list[str] = []
        charts = read_test_market_charts(
            limit=args.limit, on_error=lambda where, exc: errors.append(f"{where}: {exc}")
        )
        for e in errors:
            print(f"  (skipped) {e}", file=sys.stderr)
        return charts
    raise SystemExit("scan needs --charts-file <saved reading> or --live")


def cmd_scan(args) -> int:
    charts = _load_charts(args)
    if not charts:
        print("No charts available.", file=sys.stderr)
        return 1
    catalogue = load_catalogue(Path(args.root)) if args.root else load_catalogue()
    us_ids = frozenset(catalogue)  # the catalogue is the US top-grosser set
    if args.digest:
        from gametagger.radar.digest import digest_terms_or_default

        hot = digest_terms_or_default(args.digest)
    else:
        hot = load_hot_terms(Path(args.trends) if args.trends else None)
    hints = json.loads(Path(args.hints).read_text()) if args.hints else {}
    weights = SignalWeights()

    candidates = merge_candidates(charts, known_genomes=catalogue)
    briefed: list[BriefedCandidate] = []
    for cand in candidates:
        # A one-line genre/mechanic read per game, gathered cheaply from the store page by the
        # scheduled run; here it sharpens the genre guess and the "what's working" line.
        hint = hints.get(cand.game_id, {})
        if isinstance(hint, list):
            hint = {"hints": hint}
        # Fold the standout mechanic into the hints so trend-fit and the genre guess both see it
        # (e.g. a "social-tournament ladder" standout should match a "social tournament" trend).
        base_hints = list(hint.get("hints") or [])
        if hint.get("standout"):
            base_hints.append(hint["standout"])
        if base_hints:
            cand.hints = tuple(base_hints)
        sig = score_candidate(cand, us_game_ids=us_ids, hot_terms=hot, weights=weights)
        if sig.priority < args.min_priority:
            continue
        proposal = build_proposal(
            sig,
            cand,
            hot_terms=hot,
            standout_mechanic=hint.get("standout"),
            what_it_is=hint.get("what_it_is"),
        )
        briefed.append(BriefedCandidate(candidate=cand, signals=sig, proposal=proposal))
    briefed.sort(key=lambda b: -b.signals.priority)
    briefed = briefed[: args.top]

    chart_date = next((c.chart_date for c in charts if c.chart_date), None)
    md = render_shortlist_md(briefed, chart_date=chart_date)
    if args.out:
        Path(args.out).write_text(md)
        print(f"Wrote shortlist: {args.out}")
    else:
        print(md)
    if briefed:
        push = render_push(briefed[0], n_more=len(briefed) - 1)
        print("\n--- morning push ---")
        print(push)
    if args.json:
        Path(args.json).write_text(
            json.dumps(
                [
                    {
                        "game_id": b.candidate.game_id,
                        "title": b.candidate.title,
                        **b.signals.as_dict(),
                        "proposal": {
                            "what_it_is": b.proposal.what_it_is,
                            "whats_working": b.proposal.whats_working,
                            "theme_to": b.proposal.differentiation.theme_to,
                            "add_mechanic": b.proposal.differentiation.add_mechanic,
                            "rationale": b.proposal.differentiation.rationale,
                            "question": b.proposal.question,
                        },
                    }
                    for b in briefed
                ],
                indent=2,
            )
        )
        print(f"Wrote JSON: {args.json}")
    return 0


def cmd_approve(args) -> int:
    queue = Path(args.queue)
    queue.parent.mkdir(parents=True, exist_ok=True)
    record = {"game_id": args.game_id, "note": args.note or "", "status": "approved"}
    with queue.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    print(f"Queued {args.game_id} for a deep dive -> {queue}")
    print("Next (on the Mac, owner-approved acquisition + emulator play):")
    print(f"  scripts/mac/deep-dive.sh {args.game_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gametagger-radar", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="score chart readings into a shortlist + push")
    scan.add_argument("--charts-file", help="a saved multi-region chart reading (JSON)")
    scan.add_argument("--live", action="store_true", help="read CA/AU/NZ charts now (free)")
    scan.add_argument("--limit", type=int, default=100, help="ranks to read per Apple chart")
    scan.add_argument("--trends", help="digest trends JSON ({term: weight}); default is built-in")
    scan.add_argument(
        "--digest",
        help="newest trend-digest-*.md folder, or one digest file; builds the trend map from it",
    )
    scan.add_argument(
        "--hints", help="per-game genre/standout hints JSON ({game_id: {hints, standout, ...}})"
    )
    scan.add_argument("--root", help="repo root for the tagged catalogue (default: cwd)")
    scan.add_argument("--min-priority", type=float, default=40.0, help="drop below this priority")
    scan.add_argument("--top", type=int, default=10, help="keep at most this many")
    scan.add_argument("--out", help="write the shortlist markdown here")
    scan.add_argument("--json", help="also write the shortlist as JSON here")
    scan.set_defaults(func=cmd_scan)

    appr = sub.add_parser("approve", help="queue a game for an owner-approved deep dive")
    appr.add_argument("game_id", help="e.g. gp-com.studio.game or ios-123456789")
    appr.add_argument("--note", help="why / any direction for the teardown")
    appr.add_argument("--queue", default="radar-approvals.jsonl", help="approval queue file")
    appr.set_defaults(func=cmd_approve)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
