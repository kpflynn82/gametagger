"""gametagger-compare: Jev rich mode versus the previous single-call method.

Every step except ``run --live`` is free (public pages and APIs, no model calls). Small,
shareable outputs (cohort, answer key, crosswalk-based scores, charts) live in
``experiments/jev-vs-legacy``; dossiers, downloaded media and raw model responses stay in the
git-ignored work directory because they contain third-party store text and images.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXPERIMENT_DIR = Path("experiments/jev-vs-legacy")
WORK_DIR = Path("benchmark-runs/jev-vs-legacy")


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {path}", file=sys.stderr)


def cmd_cohort(args) -> None:
    from gametagger.comparison.charts import build_cohort

    cohort = build_cohort(steam_count=args.steam, mobile_count=args.mobile)
    _write(args.experiment / "cohort.json", cohort)
    steam = sum(g["list"] == "steam" for g in cohort["games"])
    print(
        f"{steam} Steam and {len(cohort['games']) - steam} mobile games; "
        f"{len(cohort['skipped'])} chart entries skipped (see 'skipped')."
    )


def cmd_identity(args) -> None:
    from gametagger.comparison.identity import resolve_cohort

    path = args.experiment / "cohort.json"
    cohort = resolve_cohort(_read(path), log=lambda m: print(m, file=sys.stderr))
    _write(path, cohort)


def _selected(args, cohort: dict) -> list[dict]:
    from gametagger.comparison.runner import interleaved

    games = interleaved(cohort)
    if args.games:
        wanted = set(args.games.split(","))
        games = [g for g in games if g["game_id"] in wanted]
    return games[: args.limit] if args.limit else games


def cmd_dossiers(args) -> None:
    from gametagger.comparison.dossiers import build_all

    cohort = _read(args.experiment / "cohort.json")
    ids = [g["game_id"] for g in _selected(args, cohort)]
    summaries = build_all(
        cohort,
        args.workdir,
        games=ids,
        force=args.force,
        max_screenshots=args.max_screenshots,
        video=not args.no_video,
    )
    failed = [s["game_id"] for s in summaries if "error" in s]
    print(f"{len(summaries) - len(failed)} dossiers ready; {len(failed)} failed {failed or ''}")


def cmd_answer_key(args) -> None:
    from gametagger.comparison.answer_key import build_answer_key

    key = build_answer_key(_read(args.experiment / "cohort.json"))
    _write(args.experiment / "answer-key-steam-tags.json", key)


def cmd_run(args) -> None:
    from gametagger.comparison.runner import ARMS, make_runner

    if not args.live:
        raise SystemExit("Paid run: add --live (and --budget-usd) to call Claude and Jev.")
    if args.budget_usd is None:
        raise SystemExit("Set --budget-usd; the owner's approved cap is required for a live run.")
    arms = args.arms.split(",") if args.arms else list(ARMS)
    if unknown := set(arms) - set(ARMS):
        raise SystemExit(f"Unknown arms: {sorted(unknown)}")
    runner = make_runner(
        args.workdir,
        args.budget_usd,
        observer_model=args.observer_model,
        jev_model=args.jev_model,
    )
    games = _selected(args, _read(args.experiment / "cohort.json"))
    print(
        f"Running {len(arms)} arm(s) on {len(games)} game(s); ledger so far "
        f"${runner.ledger.spent:.2f} of ${runner.ledger.cap:.2f}",
        file=sys.stderr,
    )
    summary = runner.run(
        games, arms, workers=args.workers, force=args.force, retry_failed=args.retry_failed
    )
    print(json.dumps(summary, indent=2))
    if summary["stopped_by_budget"]:
        raise SystemExit(1)


def _scoring_inputs(args):
    from gametagger.comparison.crosswalk import load_crosswalks
    from gametagger.comparison.runner import ARMS
    from gametagger.comparison.scoring import load_results
    from gametagger.genome.vocabulary import load_vocabulary
    from gametagger.taxonomy import load_taxonomy

    taxonomy = load_taxonomy()
    vocabulary = load_vocabulary(taxonomy)
    crosswalks = load_crosswalks(taxonomy, vocabulary)
    cohort = _read(args.experiment / "cohort.json")
    results = load_results(args.workdir, cohort, list(ARMS))
    return taxonomy, vocabulary, crosswalks, cohort, results


def _measured(workdir: Path) -> bool:
    """True only when the ledger shows real, successful provider calls."""
    ledger = workdir / "ledger.jsonl"
    if not ledger.exists():
        return False
    return any('"status": "ok"' in line for line in ledger.read_text().splitlines())


def cmd_review_sheet(args) -> None:
    from gametagger.comparison.review import build_review, write_sheet

    taxonomy, vocabulary, crosswalks, cohort, results = _scoring_inputs(args)
    rows, key = build_review(
        cohort,
        results,
        crosswalks,
        vocabulary,
        taxonomy,
        games=args.review_games,
        tags_per_game=args.tags_per_game,
    )
    write_sheet(rows, args.experiment / "review" / "owner-review.csv")
    _write(args.experiment / "review" / "key-do-not-open.json", key)
    print(f"{len(rows)} rows to review. Fill 'your_verdict' with yes, no or unsure.")


def cmd_report(args) -> None:
    from datetime import date

    from gametagger.comparison.report import (
        render_png,
        render_report,
        render_social_card,
        social_post,
    )
    from gametagger.comparison.scoring import read_review, score

    taxonomy, _, crosswalks, cohort, results = _scoring_inputs(args)
    key_path = args.experiment / "answer-key-steam-tags.json"
    review_csv = args.experiment / "review" / "owner-review.csv"
    review_key = args.experiment / "review" / "key-do-not-open.json"
    review = (
        read_review(review_csv, review_key) if review_csv.exists() and review_key.exists() else None
    )
    names = {g.id: g.display_name for g in taxonomy.genres_by_id.values()}
    scores = score(
        cohort,
        _read(key_path) if key_path.exists() else None,
        results,
        crosswalks,
        names,
        review=review,
    )
    illustrative = args.illustrative or not _measured(args.workdir)
    scores["run_date"] = date.today().isoformat()
    scores["measured"] = not illustrative
    out = args.experiment / "report"
    _write(args.experiment / "results" / "summary.json", scores)
    compact = [
        {k: v for k, v in r.items() if k not in ("warnings",)}
        for arm in results.values()
        for r in arm.values()
    ]
    (args.experiment / "results" / "per-game.jsonl").write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in compact)
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(render_report(scores, illustrative=illustrative))
    card = out / "social-card.html"
    card.write_text(render_social_card(scores, illustrative=illustrative))
    (out / "social-post.txt").write_text(social_post(scores))
    png = render_png(card, out / "social-card.png")
    label = "ILLUSTRATIVE (no measured run found)" if illustrative else "measured"
    print(f"Report written to {out} ({label}); social card PNG: {'yes' if png else 'no'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gametagger-compare", description=__doc__)
    parser.add_argument("--experiment", type=Path, default=EXPERIMENT_DIR)
    parser.add_argument("--workdir", type=Path, default=WORK_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("cohort", help="Freeze today's Steam and Google Play charts (free)")
    p.add_argument("--steam", type=int, default=50)
    p.add_argument("--mobile", type=int, default=50)
    p.set_defaults(func=cmd_cohort)

    p = sub.add_parser("identity", help="Link exact store IDs to Wikipedia and stores (free)")
    p.set_defaults(func=cmd_identity)

    def selection(p):
        p.add_argument("--limit", type=int, help="First N games, alternating Steam and mobile")
        p.add_argument("--games", help="Comma-separated game IDs")
        p.add_argument("--force", action="store_true", help="Redo finished items")

    p = sub.add_parser("dossiers", help="Gather shared evidence and media per game (free)")
    selection(p)
    p.add_argument("--max-screenshots", type=int, default=4)
    p.add_argument("--no-video", action="store_true")
    p.set_defaults(func=cmd_dossiers)

    p = sub.add_parser("answer-key", help="Collect Steam user tags with vote counts (free)")
    p.set_defaults(func=cmd_answer_key)

    p = sub.add_parser("run", help="PAID: run the methods on the dossiers under a hard cap")
    selection(p)
    p.add_argument("--live", action="store_true", help="Required: call Claude and Jev")
    p.add_argument("--budget-usd", type=float, help="Hard spending cap across all runs")
    p.add_argument("--arms", help="Comma-separated: rich,legacy-standard,legacy-deep")
    p.add_argument("--workers", type=int, default=3, help="Games processed in parallel")
    p.add_argument(
        "--retry-failed",
        action="store_true",
        help="Re-run results degraded by provider or network errors (rate limits, timeouts)",
    )
    p.add_argument("--observer-model", default="claude-sonnet-5")
    p.add_argument("--jev-model", default="jev-latest")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("review-sheet", help="Blinded spreadsheet for the owner's check (free)")
    p.add_argument("--review-games", type=int, default=30)
    p.add_argument("--tags-per-game", type=int, default=15)
    p.set_defaults(func=cmd_review_sheet)

    p = sub.add_parser("report", help="Score, chart and write up the results (free)")
    p.add_argument("--illustrative", action="store_true", help="Force the test-data watermark")
    p.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
