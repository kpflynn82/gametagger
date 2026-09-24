"""Build one shared dossier per cohort game, so every method reads identical evidence.

Sources come only from the cohort's exact IDs: Steam games use their Steam listing; mobile games
use their Google Play listing and, when linked, their App Store listing; both use the linked
English Wikipedia article. Screenshots and the store trailer are downloaded once. When no store
offered a trailer, the YouTube Data API backup can add a reference and YouTube's still images.
Evidence gathering is timed here, once, and reported as a shared stage.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from gametagger.comparison.identity import polite
from gametagger.genome.cli import save_dossier
from gametagger.genome.dossier import Dossier
from gametagger.genome.media import download_media
from gametagger.genome.net import fetch_json
from gametagger.genome.sources import (
    SourceError,
    app_store_source,
    google_play_reference,
    google_play_source,
    steam_source,
    wikipedia_source,
    youtube_search,
)


def safe_id(game_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", game_id).strip("-")[:80] or "game"


def dossier_path(workdir: Path, game_id: str) -> Path:
    return workdir / "dossiers" / safe_id(game_id) / "dossier.json"


def build_dossier(
    game: dict[str, Any],
    workdir: Path,
    *,
    max_screenshots: int = 4,
    video: bool = True,
    youtube_key: str | None = None,
) -> tuple[Dossier, dict[str, Any]]:
    ids, notes, fetched, timings = game["ids"], [], [], {}
    plan = []
    if game["list"] == "steam":
        plan.append(("steam", ids.get("steam_app"), steam_source))
    else:
        plan.append(("google_play", ids.get("google_play"), google_play_source))
        plan.append(("app_store", ids.get("app_store"), app_store_source))
    # Wikimedia rate-limits shared addresses; wait and retry instead of losing the article.
    polite_json = polite(fetch_json)
    plan.append(
        ("wikipedia", ids.get("wikipedia"), lambda t: wikipedia_source(t, fetch=polite_json))
    )
    start = perf_counter()
    for name, identifier, fetch in plan:
        if not identifier:
            continue
        t0 = perf_counter()
        try:
            fetched.append(fetch(identifier))
        except SourceError as exc:
            notes.append(f"{name}: {exc}")
            if fetch is google_play_source:
                fetched.append(google_play_reference(identifier))
        timings[f"source_{name}_ms"] = (perf_counter() - t0) * 1000
    sources = [f.text for f in fetched if f.text]
    references = [r for f in fetched for r in f.references]
    refs = [m for f in fetched for m in f.media]
    if youtube_key and not any(m.kind != "image" for m in refs):
        t0 = perf_counter()
        official = tuple(n for s in sources for n in s.fields.get("developers", []))
        try:
            found = youtube_search(game["title"], youtube_key, official_names=official)
            refs += found.media
            references += found.references
        except SourceError as exc:
            notes.append(f"YouTube: {exc}")
        timings["youtube_search_ms"] = (perf_counter() - t0) * 1000
    t0 = perf_counter()
    media_dir = dossier_path(workdir, game["game_id"]).parent / "media"
    images, videos, media_notes = download_media(
        refs, media_dir, max_screenshots=max_screenshots, video=video
    )
    # Trailers are large and CDN hiccups happen; only rich mode uses them, so a transient failure
    # would bias the comparison. Retry the trailer alone before giving up.
    trailer_refs = [m for m in refs if m.kind != "image"]
    retries = 0
    while video and trailer_refs and not videos and retries < 2:
        retries += 1
        _, videos, retry_notes = download_media(
            trailer_refs, media_dir, max_screenshots=0, video=True
        )
        media_notes += retry_notes
    if retries:
        outcome = "succeeded" if videos else "failed"
        media_notes.append(f"Trailer download retried {retries} time(s); {outcome}.")
    notes += media_notes
    timings["media_download_ms"] = (perf_counter() - t0) * 1000
    timings["total_ms"] = (perf_counter() - start) * 1000
    if not (sources or images or videos):
        raise SourceError(f"No evidence could be gathered for {game['game_id']}")
    dossier = Dossier(
        game_id=game["game_id"],
        title=game["title"],
        sources=sources,
        images=images,
        videos=videos,
        references=references,
        notes=notes,
    )
    summary = {
        "game_id": game["game_id"],
        "sources": [s.id for s in sources],
        "text_chars": sum(len(s.text) for s in sources),
        "images": len(images),
        "videos": len(videos),
        "references": [r.id for r in references],
        "notes": notes,
        "gather_timings": timings,
    }
    return dossier, summary


def build_all(
    cohort: dict,
    workdir: Path,
    *,
    games: list[str] | None = None,
    force: bool = False,
    max_screenshots: int = 4,
    video: bool = True,
    log=lambda m: print(m, file=sys.stderr),
) -> list[dict[str, Any]]:
    youtube_key = os.environ.get("YOUTUBE_API_KEY")
    summaries = []
    for game in cohort["games"]:
        if games and game["game_id"] not in games:
            continue
        path = dossier_path(workdir, game["game_id"])
        summary_path = path.with_name("gather.json")
        if path.exists() and summary_path.exists() and not force:
            summaries.append(json.loads(summary_path.read_text()))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            dossier, summary = build_dossier(
                game,
                workdir,
                max_screenshots=max_screenshots,
                video=video,
                youtube_key=youtube_key,
            )
        except (SourceError, ValueError, OSError) as exc:
            summary = {"game_id": game["game_id"], "error": str(exc)}
            log(f"{game['game_id']}: FAILED ({exc})")
        else:
            save_dossier(dossier, path)
            log(
                f"{game['game_id']}: {', '.join(summary['sources']) or 'no text'}; "
                f"{summary['images']} images, {summary['videos']} video; "
                f"{summary['gather_timings']['total_ms'] / 1000:.1f}s"
            )
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        summaries.append(summary)
    return summaries
