"""Rich Genome CLI. Default is a dry run; live inference needs --live and keys in the env."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from gametagger.decisions.jev import TypeSafeGateway
from gametagger.decisions.mock import MockJevGateway
from gametagger.genome.dossier import Dossier, ImageSource
from gametagger.genome.engine import GenomeEngine, GenomePipeline
from gametagger.genome.report import render_plan, render_profile
from gametagger.genome.sources import SourceError, steam_source, wikipedia_source
from gametagger.genome.vocabulary import load_vocabulary
from gametagger.observers.mock import MockObserver
from gametagger.taxonomy import load_taxonomy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gametagger-genome",
        description=(
            "Rich Genome tagging with Jev. Without --offline or --live this is a dry run that "
            "shows what would be sent and makes no model calls."
        ),
    )
    parser.add_argument("dossier", nargs="?", type=Path, help="dossier-v1 JSON file")
    parser.add_argument("--game-id", help="Game ID when no dossier file is given")
    parser.add_argument("--title", help="Display title (never sent to Jev)")
    parser.add_argument("--steam-app", help="Fetch this exact numeric Steam app ID")
    parser.add_argument("--wikipedia", help="Fetch this exact English Wikipedia article title")
    parser.add_argument("--image", action="append", default=[], type=Path, help="Screenshot")
    parser.add_argument("--categories", help="Comma-separated Genome categories to ask")
    parser.add_argument("--max-questions-per-request", type=int, default=60)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Mocks only; no inference")
    mode.add_argument("--live", action="store_true", help="Call Jev (and the Observer)")
    parser.add_argument(
        "--max-estimated-tokens",
        type=int,
        default=50_000,
        help="Refuse a live run whose rough Jev input estimate exceeds this",
    )
    parser.add_argument("--observer-model", default=os.environ.get("OBSERVER_MODEL"))
    parser.add_argument("--jev-model", default=os.environ.get("TYPESAFE_MODEL", "jev-latest"))
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    parser.add_argument("--output", type=Path, help="Write the JSON result to this file")
    parser.add_argument("--save-dossier", type=Path, help="Write the assembled dossier here")
    return parser


def assemble_dossier(args, parser) -> Dossier:
    try:
        return _assemble(args, parser)
    except (OSError, ValueError) as exc:  # pydantic ValidationError is a ValueError
        parser.error(f"Could not build the dossier: {exc}")


def _assemble(args, parser) -> Dossier:
    if args.dossier:
        dossier = Dossier.model_validate_json(args.dossier.read_text())
        base = args.dossier.resolve().parent
        images = [
            i.model_copy(update={"path": str((base / i.path).resolve())}) for i in dossier.images
        ]
        dossier = dossier.model_copy(update={"images": images})
    elif args.game_id:
        dossier = None
    else:
        parser.error("Give a dossier file, or --game-id with --steam-app/--wikipedia/--image")
    sources = list(dossier.sources) if dossier else []
    images = list(dossier.images) if dossier else []
    try:
        if args.steam_app:
            sources.append(steam_source(args.steam_app))
        if args.wikipedia:
            sources.append(wikipedia_source(args.wikipedia))
    except SourceError as exc:
        parser.error(str(exc))
    taken = {s.id for s in sources} | {i.id for i in images}
    for path in args.image:
        n = len(images) + 1
        while f"image{n}" in taken:
            n += 1
        taken.add(f"image{n}")
        images.append(ImageSource(id=f"image{n}", path=str(path.resolve())))
    return Dossier(
        game_id=dossier.game_id if dossier else args.game_id,
        title=args.title or (dossier.title if dossier else None),
        sources=sources,
        images=images,
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    dossier = assemble_dossier(args, parser)
    if args.save_dossier:
        args.save_dossier.write_text(dossier.model_dump_json(indent=2) + "\n")
    taxonomy = load_taxonomy()
    vocabulary = load_vocabulary(taxonomy)
    categories = [c.strip() for c in args.categories.split(",")] if args.categories else None

    if args.live:
        if not os.environ.get("TYPESAFE_API_KEY"):
            parser.error("Set TYPESAFE_API_KEY in the environment for a live run")
        if dossier.images and not (os.environ.get("ANTHROPIC_API_KEY") and args.observer_model):
            parser.error("Screenshots need ANTHROPIC_API_KEY and --observer-model (or omit them)")
        gateway = TypeSafeGateway(model=args.jev_model)
    else:
        gateway = MockJevGateway()
    try:
        engine = GenomeEngine(
            taxonomy,
            vocabulary,
            gateway,
            categories=categories,
            max_questions_per_request=args.max_questions_per_request,
        )
    except ValueError as exc:
        parser.error(str(exc))

    observer = None
    if args.live and dossier.images:
        from gametagger.observers.anthropic import AnthropicObserver

        observer = AnthropicObserver(
            taxonomy,
            model=args.observer_model,
            workspace_id=os.environ.get("ANTHROPIC_WORKSPACE_ID"),
            enforce_boundary=False,
        )
    elif args.offline:
        observer = MockObserver()
    pipeline = GenomePipeline(engine, observer)

    evidence, claims, *_ = pipeline.prepare(dossier, observe=False)
    plan = engine.plan(claims, evidence)
    estimate = plan.estimate(engine.genre_branch_chars())
    if not (args.offline or args.live):
        if args.format == "json":
            batches = [
                {
                    "state": json.loads(plan.states[b[0]]),
                    "questions": {k: vars(plan.specs[k]) for k in b},
                }
                for b in plan.batches
            ]
            result = {
                "dry_run": True,
                "estimate": estimate,
                "skipped": plan.skipped,
                "requests": batches,
            }
            text = json.dumps(result, indent=2, ensure_ascii=False)
        else:
            text = render_plan(
                plan,
                estimate,
                dossier=dossier,
                claims=claims,
                vocabulary=vocabulary,
                tags=engine.tags,
            )
        print(text)
        if args.output:
            args.output.write_text(text + "\n")
        return
    if args.live and estimate["approx_input_tokens_total"] > args.max_estimated_tokens:
        parser.error(
            f"Estimated {estimate['approx_input_tokens_total']:,} Jev input tokens exceeds "
            f"--max-estimated-tokens {args.max_estimated_tokens:,}. Narrow --categories or "
            "raise the cap deliberately."
        )
    if args.live:
        print(
            f"Live run: about {estimate['approx_input_tokens_total']:,} Jev input tokens "
            "(rough estimate).",
            file=sys.stderr,
        )
    profile = pipeline.analyze(dossier, offline=args.offline)
    payload = profile.model_dump_json(indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload if args.format == "json" else render_profile(profile, vocabulary))


if __name__ == "__main__":
    main()
