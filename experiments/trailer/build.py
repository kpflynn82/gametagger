"""Render the GameTagger marketing trailer (silent, 1080 x 1080, 30 fps, about 49 seconds).

    uv run python experiments/trailer/build.py [--fonts fonts.css] [--still SECONDS]

The scenes live in ``scene.html``; ``render(t)`` draws the frame at time ``t``. Every number
comes from the repository:

* the tag and genre counts from ``taxonomy/``;
* the top-100 figures from the published dashboard data in ``web/index.html``.

Game screens are invented illustrations; no store screenshots, trailers or logos are used.
NitroGen figures are from NVIDIA's public release: 40,000 hours of gameplay video across more
than 1,000 games. GameTagger used its game list to seed the catalog, and no model was trained
on it.

Needs Node with the ``playwright`` package and ffmpeg. ``--fonts`` takes a CSS file with
embedded Chivo and Chivo Mono (@font-face); without it the system sans is used.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CHROME = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
FPS, SECONDS = 30, 49.0

RENDER_JS = """
const { chromium } = require('playwright');
const [page_url, out, fps, seconds, still] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1080 } });
  await page.goto(page_url);
  await page.evaluate(() => document.fonts.ready);
  const count = Math.round(fps * seconds);
  const times = still ? still.split(',').map(Number) : [...Array(count).keys()].map(i => i / fps);
  for (const [i, t] of times.entries()) {
    await page.evaluate(t => window.render(t), t);
    await page.screenshot({ path: `${out}/${String(i).padStart(5, '0')}.png` });
  }
  await browser.close();
})();
"""

# Tags shown in the vocabulary cloud (labels as defined), mixed with genres.
CLOUD_TAGS = [
    "Gacha or loot boxes",
    "Battle pass",
    "Energy or stamina timers",
    "Live events",
    "Daily rewards or quests",
    "Guilds or clans",
    "In-game purchases",
    "Ad-supported",
    "Auto-play or idle progress",
    "Skill tree",
    "Loot drops",
    "Upgrade system",
    "Base or settlement building",
    "Deck building",
    "Boss battles",
    "Permadeath",
    "Crafting",
    "Open world",
    "Hub world",
    "Branching narrative",
    "Moral choices",
    "Online multiplayer",
    "Player versus player",
    "Ranked or competitive play",
    "Leaderboards",
    "Cross-platform play",
    "Touch controls",
    "Controller support",
    "Offline play",
    "Free to play",
    "Cosmetic-only purchases",
    "Pay-to-progress or pay-to-win",
    "Fantasy setting",
    "Cyberpunk setting",
    "Post-apocalyptic setting",
    "Cozy and relaxing",
    "Horror tone",
    "Anime style",
    "Low-poly",
    "Pixel art",
    "Colourblind options",
    "Farming",
    "Fishing",
    "Collecting",
    "Character customization",
    "Companions or party members",
    "Physics-based interaction",
    "Drivable vehicles",
    "Resource management",
    "Quests and missions",
]
CLOUD_GENRES = [
    "Match-3",
    "Merge",
    "Roguelite",
    "Souls-like",
    "MOBA",
    "Battle Royale",
    "4X Strategy",
    "Idle / Incremental",
    "Auto Battler",
    "City Builder",
    "Metroidvania",
    "Tower Defense",
    "Deck Builder",
    "Survivor-like / Bullet Heaven",
    "Life Simulation",
    "Endless Runner",
    "Extraction Shooter",
    "Colony Sim",
    "Creature Collector / Monster Tamer",
    "Casino",
]


def data() -> dict:
    tags = yaml.safe_load((ROOT / "taxonomy/genome_tags_v1.yaml").read_text())
    genres = yaml.safe_load((ROOT / "taxonomy/vgms_v4.yaml").read_text())
    labels = {t["label"]: t for t in tags["tags"]} | {t["label"]: t for t in genres["tags"]}
    genre_names = {g["display_name"] for f in genres["genre_families"] for g in f["genres"]}
    attributes = len(tags["tags"]) + len(genres["tags"])
    genre_count = len(genre_names)
    assert (attributes, genre_count, len(genres["genre_families"])) == (189, 100, 14), (
        "The trailer's counters are drawn for 189 attributes and 100 genres in 14 families"
    )
    cloud = [[t, False] for t in CLOUD_TAGS if t in labels]
    cloud += [[g, True] for g in CLOUD_GENRES if g in genre_names]
    order = sorted(range(len(cloud)), key=lambda i: (i * 37) % len(cloud))
    energy = labels["Energy or stamina timers"]

    page = (ROOT / "web/index.html").read_text()
    site = json.loads(re.search(r"const DATA = (\{.*?\});\n", page, re.S).group(1))
    games = site["games"]
    mix = Counter(g["rich"]["genre"] for g in games if g["rich"].get("genre"))
    sample = site["figures"]["sample"]
    wanted = ["Counter-Strike 2", "Dota 2", "Candy Crush Saga", "MONOPOLY GO!"]
    rows = [
        [g["title"], g["rich"]["genre"], g["rich"]["present"]]
        for title in wanted
        for g in games
        if g["title"] == title
    ]
    return {
        "cloud": [cloud[i] for i in order],
        "def": [
            energy["label"],
            energy["definition"],
            "Evidence allowed: screenshots · gameplay video · store listing · developer docs",
        ],
        "obs": [
            "A banner reads LIMITED OFFER with a countdown of 02:14:59.",
            "Three items are listed with prices of $4.99, $1.99 and $9.99.",
            "The top bar shows 1,250 coins and 30 gems.",
        ],
        "decisions": [
            ["In-game purchases", "present", 0.97],
            ["Live events", "present", 0.91],
            ["Energy or stamina timers", "unknown", None],
            ["Guilds or clans", "unknown", None],
        ],
        "web": {
            "sub": f"{sample['steam_games']} Steam most-played + {sample['mobile_games']} "
            f"Google Play top-grossing · charts of Sept {sample['chart_dates']['steam'][-2:]} and "
            f"{sample['chart_dates']['mobile'][-2:]}, 2026",
            "genres": [list(x) for x in mix.most_common(7)],
            "median": statistics.median(g["rich"]["present"] for g in games),
            "games_total": len(games),
            "games": rows,
        },
        "endline": "Claude describes · Jev decides, tag by tag<br>"
        "Catalog seeded from the NitroGen game list · Jev by TypeSafe",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fonts", type=Path)
    parser.add_argument("--out", type=Path, default=HERE / "gametagger-trailer.mp4")
    parser.add_argument("--still", help="comma-separated times: render stills to PNGs instead")
    args = parser.parse_args()
    fonts = args.fonts.read_text() if args.fonts and args.fonts.exists() else ""
    page = (HERE / "scene.html").read_text()
    page = page.replace("/*FONTS*/", fonts).replace("/*DATA*/", json.dumps(data()))
    node_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "scene.html").write_text(page)
        (work / "render.js").write_text(RENDER_JS)
        frames = work / "frames"
        frames.mkdir()
        subprocess.run(
            ["node", str(work / "render.js"), (work / "scene.html").as_uri(), str(frames),
             str(FPS), str(SECONDS), args.still or ""],
            check=True,
            env={**os.environ, "NODE_PATH": node_root.strip(), "CHROME": CHROME},
        )  # fmt: skip
        if args.still:
            for i, t in enumerate(args.still.split(",")):
                target = args.out.with_name(f"still-{float(t):05.1f}.png")
                shutil.copy(frames / f"{i:05d}.png", target)
                print(target)
            return
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(frames / "%05d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow",
             "-movflags", "+faststart", str(args.out)],
            check=True,
        )  # fmt: skip
    print(args.out)


if __name__ == "__main__":
    main()
