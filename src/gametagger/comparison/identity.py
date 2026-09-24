"""Exact-ID identity: link each chart entry to its Wikipedia article and other store listings.

Primary route: Wikidata records store IDs as properties (Steam application ID P1733, Google Play
package P3418, App Store ID P3861). Looking an entry up by its chart's exact store ID returns
the same game, not a namesake, and yields its English Wikipedia article and its other store IDs.

Fallback (mobile only, when Wikidata has no match): an App Store search accepted only when both
the normalized title and the developer match exactly. Such links are marked for owner review.
Anything ambiguous is left unlinked and recorded, never guessed.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote, urlencode

from gametagger.genome.net import SourceError, fetch_json
from gametagger.genome.sources import normal_title

WIKIDATA_API = "https://www.wikidata.org/w/api.php?"
# Cached entity documents; the API itself is rate limited much more tightly.
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{}.json"
ITUNES_SEARCH = "https://itunes.apple.com/search?"
PROPERTIES = {"steam_app": "P1733", "google_play": "P3418", "app_store": "P3861"}
Fetch = Callable[[str], Any]


def polite(fetch: Fetch, *, tries: int = 6, wait: float = 10.0, sleep=time.sleep) -> Fetch:
    """Retry HTTP 429 (Wikimedia rate limits) with growing pauses; other errors pass through."""

    def call(url: str) -> Any:
        for attempt in range(tries):
            try:
                return fetch(url)
            except SourceError as exc:
                if "HTTP 429" not in str(exc) or attempt == tries - 1:
                    raise
                sleep(wait * (attempt + 1))
        raise AssertionError("unreachable")

    return call


def wikidata_items(prop: str, value: str, *, fetch: Fetch = fetch_json) -> list[str]:
    url = WIKIDATA_API + urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": f'haswbstatement:"{prop}={value}"',
            "srlimit": "5",
            "format": "json",
        }
    )
    hits = ((fetch(url) or {}).get("query") or {}).get("search") or []
    return [h["title"] for h in hits if str(h.get("title", "")).startswith("Q")]


def wikidata_entities(qids: list[str], *, fetch: Fetch = fetch_json) -> dict[str, dict]:
    entities = {}
    for qid in qids:
        payload = fetch(WIKIDATA_ENTITY.format(quote(qid))) or {}
        entity = (payload.get("entities") or {}).get(qid)
        if isinstance(entity, dict):
            entities[qid] = entity
    return entities


def claim_values(entity: dict, prop: str) -> list[str]:
    values = []
    for statement in (entity.get("claims") or {}).get(prop) or []:
        if statement.get("rank") == "deprecated":
            continue
        value = ((statement.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, str) and value not in values:
            values.append(value)
    return values


def _label(entity: dict) -> str:
    return str(((entity.get("labels") or {}).get("en") or {}).get("value") or "")


def _enwiki(entity: dict) -> str | None:
    return ((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title")


def resolve_wikidata(game: dict, *, fetch: Fetch = fetch_json) -> dict[str, Any]:
    key = "steam_app" if "steam_app" in game["ids"] else "google_play"
    value = game["ids"][key]
    qids = wikidata_items(PROPERTIES[key], value, fetch=fetch)
    record: dict[str, Any] = {"method": "wikidata-exact-store-id", "lookup": f"{key}={value}"}
    if not qids:
        return {**record, "status": "no_match"}
    entities = wikidata_entities(qids, fetch=fetch)
    candidates = [{"qid": q, "label": _label(e), "enwiki": _enwiki(e)} for q, e in entities.items()]
    record["candidates"] = candidates
    if len(entities) == 1:
        qid = next(iter(entities))
    else:
        wanted = normal_title(game["title"])
        named = [q for q, e in entities.items() if normal_title(_label(e)) == wanted]
        if len(named) != 1:
            return {**record, "status": "ambiguous"}
        qid = named[0]
    entity = entities[qid]
    return {
        **record,
        "status": "matched",
        "qid": qid,
        "label": _label(entity),
        "wikipedia": _enwiki(entity),
        "steam_app": claim_values(entity, PROPERTIES["steam_app"]),
        "google_play": claim_values(entity, PROPERTIES["google_play"]),
        "app_store": claim_values(entity, PROPERTIES["app_store"]),
    }


def resolve_app_store_by_search(game: dict, *, fetch: Fetch = fetch_json) -> dict[str, Any]:
    """Accept a single App Store result whose title and developer both match exactly."""
    url = ITUNES_SEARCH + urlencode(
        {"term": game["title"], "entity": "software", "country": "us", "limit": "10"}
    )
    wanted_title = normal_title(game["title"])
    developers = {normal_title(d) for d in game.get("developers") or [] if normal_title(d)}
    matches = [
        r
        for r in (fetch(url) or {}).get("results") or []
        if normal_title(str(r.get("trackName", ""))) == wanted_title
        and normal_title(str(r.get("artistName", ""))) in developers
    ]
    record = {"method": "app-store-search-title-and-developer", "needs_owner_review": True}
    if len(matches) != 1:
        return {**record, "status": "no_match" if not matches else "ambiguous"}
    return {**record, "status": "matched", "app_store": str(matches[0]["trackId"])}


SETTLED = {"matched", "no_match", "ambiguous"}


def resolve_cohort(
    cohort: dict,
    *,
    fetch: Fetch = fetch_json,
    log=print,
    pause: float = 3.0,
    sleep=time.sleep,
    force: bool = False,
) -> dict:
    """Fill ``ids`` (wikipedia, app_store, steam_app) and an ``identity`` record per game.

    Resumable: games whose Wikidata lookup already settled are skipped unless ``force``.
    """
    fetch = polite(fetch, sleep=sleep)
    for game in cohort["games"]:
        previous = (game.get("identity") or {}).get("wikidata") or {}
        if previous.get("status") in SETTLED and not force:
            continue
        sleep(pause)
        ids = game["ids"]
        try:
            found = resolve_wikidata(game, fetch=fetch)
        except SourceError as exc:
            found = {"method": "wikidata-exact-store-id", "status": "error", "error": str(exc)}
        identity = {"wikidata": found}
        if found["status"] == "matched":
            if found.get("wikipedia"):
                ids["wikipedia"] = found["wikipedia"]
            if game["list"] == "mobile":
                if found["app_store"]:
                    ids["app_store"] = found["app_store"][0]
                if len(found["steam_app"]) == 1:
                    ids["steam_app"] = found["steam_app"][0]
        if game["list"] == "mobile" and "app_store" not in ids:
            try:
                search = resolve_app_store_by_search(game, fetch=fetch)
            except SourceError as exc:
                search = {"status": "error", "error": str(exc)}
            identity["app_store_search"] = search
            if search["status"] == "matched":
                ids["app_store"] = search["app_store"]
        game["identity"] = identity
        linked = ", ".join(k for k in ("wikipedia", "app_store", "steam_app") if k in ids)
        log(f"{game['game_id']}: wikidata {found['status']}; linked {linked or 'nothing extra'}")
    return cohort
