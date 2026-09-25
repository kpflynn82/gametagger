"""Steam user tags as an independent answer key.

Steam players vote tags onto a game ("Open World", "Pixel Graphics", ...). The store page embeds
every tag with its vote count. Neither method is shown these tags: rich mode and the old method
both read the Steam *store* genres and features, which the publisher chooses, never user tags.

What the key can and cannot say: a well-voted tag is evidence the attribute is present, so it
supports *recall* (did a method find it?). A missing tag is not evidence of absence, so it can
never mark a method's extra tag wrong; precision needs the owner's review.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from gametagger.genome.net import SourceError, fetch_text

STORE_PAGE = "https://store.steampowered.com/app/{}/?l=english&cc=us"
# Pass Steam's age gate (a public page setting, not a login) and ask for English text.
AGE_GATE_COOKIE = "birthtime=0; lastagecheckage=1-0-1900; wants_mature_content=1"
TAG_MODAL = re.compile(r"InitAppTagModal\(\s*\d+\s*,\s*(\[.*?\])\s*,", re.S)
DISPLAYED_TAGS = 20  # Steam shows a game's 20 most-voted tags on its page


def parse_user_tags(page: str) -> list[dict[str, Any]]:
    match = TAG_MODAL.search(page)
    if not match:
        return []
    try:
        raw = json.loads(match.group(1))
    except ValueError:
        return []
    tags = [
        {"name": str(t["name"]).strip(), "votes": int(t.get("count") or 0)}
        for t in raw
        if isinstance(t, dict) and t.get("name")
    ]
    tags.sort(key=lambda t: -t["votes"])
    return [{**t, "rank": n} for n, t in enumerate(tags, start=1)]


def steam_user_tags(appid: str, *, fetch_page: Callable[..., str] = fetch_text) -> list[dict]:
    if not str(appid).isdigit():
        raise SourceError("A Steam app ID must be numeric")
    page = fetch_page(STORE_PAGE.format(appid), headers={"Cookie": AGE_GATE_COOKIE})
    return parse_user_tags(page)


def build_answer_key(
    cohort: dict,
    *,
    fetch_page: Callable[..., str] = fetch_text,
    pause: float = 1.0,
    sleep=time.sleep,
    log=lambda m: print(m, file=sys.stderr),
) -> dict[str, Any]:
    games = {}
    for game in cohort["games"]:
        appid = game["ids"].get("steam_app")
        if not appid:
            continue
        sleep(pause)
        try:
            tags = steam_user_tags(appid, fetch_page=fetch_page)
            status = "ok" if tags else "no_tags_on_page"
        except SourceError as exc:
            tags, status = [], f"error: {exc}"
        games[game["game_id"]] = {"steam_app": appid, "status": status, "tags": tags}
        log(f"{game['game_id']}: {status}, {len(tags)} tags")
    return {
        "schema_version": "steam-user-tags-v1",
        "source": "Steam store pages: player-voted user tags with vote counts",
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "displayed_tags": DISPLAYED_TAGS,
        "method_note": (
            "A tag counts as present when it is among the game's most-voted tags "
            f"(top {DISPLAYED_TAGS}, as Steam displays). Absent tags are unknown, not negative."
        ),
        "games": games,
    }
