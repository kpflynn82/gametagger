"""Rich Genome CLI. Default is a dry run; live inference needs --live and keys in the env.

Store pages are read first (text, screenshots, trailer). When no store page offers a trailer,
YouTube is searched through the official Data API as a backup: that finds a video and YouTube's
published still images, never the video file itself.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from gametagger.decisions.jev import TypeSafeGateway
from gametagger.decisions.mock import MockJevGateway
from gametagger.genome.dossier import Dossier, ImageSource, VideoSource
from gametagger.genome.engine import GenomeEngine, GenomePipeline
from gametagger.genome.media import download_media
from gametagger.genome.report import render_plan, render_profile
from gametagger.genome.sources import (
    SourceError,
    app_store_source,
    google_play_reference,
    steam_source,
    wikipedia_source,
    youtube_search,
)
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
    parser.add_argument("--title", help="Display title; also used for YouTube search")

    sources = parser.add_argument_group("store pages and sources (exact IDs, never a search)")
    sources.add_argument("--steam-app", help="Numeric Steam app ID")
    sources.add_argument("--app-store", help="Numeric Apple App Store ID (digits after 'id')")
    sources.add_argument("--app-store-country", default="us", help="App Store country code")
    sources.add_argument("--google-play", help="Google Play package, e.g. com.studio.game")
    sources.add_argument("--wikipedia", help="Exact English Wikipedia article title")
    sources.add_argument(
        "--youtube",
        choices=["auto", "always", "never"],
        default="auto",
        help="auto: search only when no store page has a trailer (needs YOUTUBE_API_KEY)",
    )

    media = parser.add_argument_group("screenshots and video")
    media.add_argument("--image", action="append", default=[], type=Path, help="Screenshot")
    media.add_argument("--video", action="append", default=[], type=Path, help="Video file")
    media.add_argument("--max-screenshots", type=int, default=4, help="Per store (default 4)")
    media.add_argument("--no-video", action="store_true", help="Skip trailers and videos")
    media.add_argument("--no-media", action="store_true", help="Text only: no images or video")
    media.add_argument("--media-dir", type=Path, help="Where downloads are kept")
    media.add_argument("--bursts", type=int, default=6, help="Frame bursts per video")
    media.add_argument("--frames-per-burst", type=int, default=6)

    parser.add_argument("--categories", help="Comma-separated Genome categories to ask")
    parser.add_argument("--max-questions-per-request", type=int, default=60)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Mocks only; no inference")
    mode.add_argument("--live", action="store_true", help="Call Jev and the vision Observer")
    parser.add_argument(
        "--max-estimated-tokens",
        type=int,
        default=50_000,
        help="Refuse a live run whose rough Jev input estimate exceeds this",
    )
    parser.add_argument(
        "--max-observer-tokens",
        type=int,
        default=80_000,
        help="Refuse a live run whose rough vision-Observer input estimate exceeds this",
    )
    parser.add_argument("--observer-model", default=os.environ.get("OBSERVER_MODEL"))
    parser.add_argument("--jev-model", default=os.environ.get("TYPESAFE_MODEL", "jev-latest"))
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    parser.add_argument("--output", type=Path, help="Write the result to this file")
    parser.add_argument("--save-dossier", type=Path, help="Write the assembled dossier here")
    return parser


def assemble_dossier(args, parser) -> Dossier:
    try:
        return _assemble(args, parser)
    except (OSError, ValueError) as exc:  # pydantic ValidationError is a ValueError
        parser.error(f"Could not build the dossier: {exc}")


def _note(notes: list[str], message: str) -> None:
    notes.append(message)
    print(f"note: {message}", file=sys.stderr)


def _assemble(args, parser) -> Dossier:
    if args.dossier:
        base = Dossier.model_validate_json(args.dossier.read_text())
        root = args.dossier.resolve().parent
        base = base.model_copy(
            update={
                "images": [
                    i.model_copy(update={"path": str((root / i.path).resolve())})
                    for i in base.images
                ],
                "videos": [
                    v.model_copy(update={"path": str((root / v.path).resolve())})
                    for v in base.videos
                ],
            }
        )
    elif args.game_id:
        base = None
    else:
        parser.error("Give a dossier file, or --game-id with store IDs, --image or --video")
    game_id = base.game_id if base else args.game_id
    notes = list(base.notes) if base else []
    sources = list(base.sources) if base else []
    images = list(base.images) if base else []
    videos = list(base.videos) if base else []
    references = list(base.references) if base else []

    requested = [
        ("Steam", args.steam_app, steam_source),
        (
            "App Store",
            args.app_store,
            lambda x: app_store_source(x, country=args.app_store_country),
        ),
        ("Google Play", args.google_play, google_play_reference),
        ("Wikipedia", args.wikipedia, wikipedia_source),
    ]
    fetched = []
    for name, identifier, fetch in requested:
        if identifier:
            try:
                fetched.append(fetch(identifier))
            except SourceError as exc:
                _note(notes, f"{name}: {exc}")
    sources += [f.text for f in fetched if f.text]
    references += [r for f in fetched for r in f.references]
    refs = [m for f in fetched for m in f.media]
    if args.google_play:
        _note(notes, "Google Play is recorded as a link only until a data service is connected.")

    has_trailer = bool(videos or args.video or any(m.kind != "image" for m in refs))
    wants_youtube = args.youtube == "always" or (
        args.youtube == "auto" and fetched and not has_trailer
    )
    if wants_youtube and not args.no_media:
        key = os.environ.get("YOUTUBE_API_KEY")
        title = args.title or (base.title if base else None)
        title = title or next((s.reported_title for s in sources if s.reported_title), None)
        if not key or not title:
            _note(
                notes,
                "No store trailer found. Set YOUTUBE_API_KEY (and give --title) to search "
                "YouTube as a backup.",
            )
        else:
            official = tuple(
                n
                for s in sources
                for k in ("developers", "publishers")
                for n in s.fields.get(k, [])
            )
            try:
                found = youtube_search(title, key, official_names=official)
                refs += found.media
                references += found.references
            except SourceError as exc:
                _note(notes, f"YouTube: {exc}")

    if refs and not args.no_media:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", game_id).strip("-")[:64] or "game"
        directory = args.media_dir or Path("gametagger-media") / safe_id
        new_images, new_videos, download_notes = download_media(
            refs, directory, max_screenshots=args.max_screenshots, video=not args.no_video
        )
        images += new_images
        videos += new_videos
        for message in download_notes:
            _note(notes, message)
    taken = {x.id for x in [*sources, *images, *videos, *references]}

    def fresh(prefix: str) -> str:
        n = 1
        while f"{prefix}{n}" in taken:
            n += 1
        taken.add(f"{prefix}{n}")
        return f"{prefix}{n}"

    images += [ImageSource(id=fresh("image"), path=str(p.resolve())) for p in args.image]
    videos += [VideoSource(id=fresh("video"), path=str(p.resolve())) for p in args.video]
    if args.no_media:
        images, videos = [], []
    elif args.no_video:
        videos = []
    title = args.title or (base.title if base else None)
    return Dossier(
        game_id=game_id,
        title=title or next((s.reported_title for s in sources if s.reported_title), None),
        sources=sources,
        images=images,
        videos=videos,
        references=references,
        notes=notes,
    )


def save_dossier(dossier: Dossier, path: Path) -> None:
    """Write paths relative to the saved file so the dossier folder can be moved."""
    root = path.resolve().parent

    def rel(p: str) -> str:
        return os.path.relpath(p, root)

    portable = dossier.model_copy(
        update={
            "images": [i.model_copy(update={"path": rel(i.path)}) for i in dossier.images],
            "videos": [v.model_copy(update={"path": rel(v.path)}) for v in dossier.videos],
        }
    )
    path.write_text(portable.model_dump_json(indent=2) + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    dossier = assemble_dossier(args, parser)
    if args.save_dossier:
        save_dossier(dossier, args.save_dossier)
    taxonomy = load_taxonomy()
    vocabulary = load_vocabulary(taxonomy)
    categories = [c.strip() for c in args.categories.split(",")] if args.categories else None
    has_media = bool(dossier.images or dossier.videos)

    if args.live:
        if not os.environ.get("TYPESAFE_API_KEY"):
            parser.error("Set TYPESAFE_API_KEY in the environment for a live run")
        if has_media and not (os.environ.get("ANTHROPIC_API_KEY") and args.observer_model):
            parser.error(
                "Screenshots and trailers need ANTHROPIC_API_KEY and --observer-model "
                "(a vision-capable Claude model), or use --no-media for a text-only run"
            )
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

    observer = ordered = None
    if args.live and has_media:
        from gametagger.observers.anthropic import AnthropicObserver
        from gametagger.observers.anthropic_ordered import AnthropicOrderedObserver

        workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        observer = AnthropicObserver(
            taxonomy, model=args.observer_model, workspace_id=workspace, enforce_boundary=False
        )
        ordered = AnthropicOrderedObserver(
            taxonomy,
            model=args.observer_model,
            workspace_id=workspace,
            allow_live=True,
            enforce_boundary=False,
        )
    elif args.offline:
        observer = MockObserver()
    try:
        pipeline = GenomePipeline(
            engine,
            observer,
            ordered,
            bursts=args.bursts,
            frames_per_burst=args.frames_per_burst,
        )
        prepared = pipeline.prepare(dossier, observe=False)
    except ValueError as exc:
        parser.error(str(exc))
    plan = engine.plan(prepared.claims, prepared.evidence)
    estimate = plan.estimate(engine.genre_branch_chars())
    vision = prepared.observer_estimate()
    if not (args.offline or args.live):
        if args.format == "json":
            requests = [
                {
                    "state": json.loads(plan.states[b[0]]),
                    "questions": {k: vars(plan.specs[k]) for k in b},
                }
                for b in plan.batches
            ]
            result = {
                "dry_run": True,
                "jev_estimate": estimate,
                "observer_estimate": vision,
                "media": prepared.media,
                "references": [r.model_dump(mode="json") for r in dossier.references],
                "notes": dossier.notes,
                "skipped": plan.skipped,
                "requests": requests,
            }
            text = json.dumps(result, indent=2, ensure_ascii=False)
        else:
            text = render_plan(
                plan,
                estimate,
                dossier=dossier,
                prepared=prepared,
                vocabulary=vocabulary,
                tags=engine.tags,
            )
        print(text)
        if args.output:
            args.output.write_text(text + "\n")
        return
    if args.live:
        if estimate["approx_input_tokens_total"] > args.max_estimated_tokens:
            parser.error(
                f"Estimated {estimate['approx_input_tokens_total']:,} Jev input tokens exceeds "
                f"--max-estimated-tokens {args.max_estimated_tokens:,}. Narrow --categories or "
                "raise the cap deliberately."
            )
        if vision["approx_input_tokens_total"] > args.max_observer_tokens:
            parser.error(
                f"Estimated {vision['approx_input_tokens_total']:,} vision input tokens exceeds "
                f"--max-observer-tokens {args.max_observer_tokens:,}. Lower --max-screenshots, "
                "--bursts or --frames-per-burst, or raise the cap deliberately."
            )
        print(
            f"Live run: about {estimate['approx_input_tokens_total']:,} Jev input tokens and "
            f"{vision['approx_input_tokens_total']:,} vision input tokens (rough estimates).",
            file=sys.stderr,
        )
    profile = pipeline.analyze(dossier, offline=args.offline)
    payload = profile.model_dump_json(indent=2)
    if args.output:
        args.output.write_text(payload + "\n")
    print(payload if args.format == "json" else render_profile(profile, vocabulary))


if __name__ == "__main__":
    main()
