"""Render the GameTagger marketing trailer (silent, 1080 x 1080, 30 fps, about 82 seconds).

    uv run python experiments/trailer/build.py [--fonts fonts.css] [--still SECONDS]
    uv run python experiments/trailer/build.py --cut highlight [--fonts fonts.css]   # 30 s

The scenes live in ``scene.html``; ``render(t)`` draws the frame at time ``t``. Every number
comes from the repository:

* the tag and genre counts from ``taxonomy/``;
* Jev's figures from the benchmark in ``experiments/jev-vs-legacy/results/``;
* the top-100 figures from the published dashboard data in ``web/index.html``;
* the plane game's store-page tags from ``experiments/single-games/epic-plane-evolution/``;
* the AI player's measurements and the prototype's simulated figures from the teardown and
  Fold & Fly entries in ``docs/EXECUTION_STATUS.md`` (see ``PLAY`` and ``BUILD`` below);
* the prototype footage from ``footage/prototype.mp4``, recorded from the Fold & Fly
  prototype by its ``scripts/trailer-clips.mjs``.

The original game's screens are invented illustrations; no store screenshots, trailers or
logos are used, and the original game is not named. The prototype footage is real.
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
FPS, SECONDS = 30, 81.6

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


def jev() -> dict:
    """Jev's scene: illustrative decisions for the mock shop, then measured benchmark figures."""
    exp = ROOT / "experiments/jev-vs-legacy/results"
    summary = json.loads((exp / "summary.json").read_text())
    rich, old = summary["arms"]["rich"], summary["arms"]["legacy-deep"]
    per_game = [json.loads(x) for x in (exp / "per-game.jsonl").read_text().splitlines()]
    asked = statistics.median(g["questions_asked"] for g in per_game if g["arm"] == "rich")
    decide_s = rich["latency_ms"]["stages"]["decide"]["median"] / 1000
    jev_cents = 100 * rich["cost_usd"]["typesafe_total"] / rich["games"]
    said_no = 100 * rich["steam_tags"]["all_mapped"]["contradiction_rate"]
    old_no = 100 * old["steam_tags"]["all_mapped"]["contradiction_rate"]
    sample = summary["sample"]
    return {
        "questions": int(asked),
        # present, absent, not enough evidence, conflicting (illustrative, for the mock shop)
        "rows": [
            ["In-game purchases", [0.97, 0.01, 0.01, 0.01], "present"],
            ["Live events", [0.91, 0.02, 0.06, 0.01], "present"],
            ["Energy or stamina timers", [0.12, 0.03, 0.82, 0.03], "unknown"],
            ["Guilds or clans", [0.08, 0.05, 0.84, 0.03], "unknown"],
        ],
        "tiles": [
            [asked, 0, "", "", "questions per game", "median, every tag plus genre"],
            [decide_s, 1, "", " s", "to decide a game", "median"],
            [jev_cents, 1, "", "¢", "Jev's cost per game", "the Observer's image reading is extra"],
            [
                said_no,
                1,
                "",
                "%",
                "player tags wrongly called absent",
                f"one big Claude prompt: {old_no:.1f}%",
            ],
        ],
        "foot": f"Measured on the top 100 ({sample['steam_games']} Steam most-played + "
        f'{sample["mobile_games"]} Google Play top-grossing, Sept 2026). "Wrongly called absent" '
        "uses the 50 Steam games' top player tags; the big prompt is Claude Opus 4.8. "
        "The per-tag decisions shown before are illustrative.",
    }


# Measured by the teardown player (an AI player on an Android emulator, a separate project) on
# Sept 28-29, 2026: 13.2 hours of play; in the first 8 hours (159 flights) 154 forced ads, a
# median 27 s each; an energy limit (5 flights, then a wait of about 42 minutes) from about
# hour 11; still on the first plane after 13 hours. Model calls for the whole run: $6.95 paid
# plus $76.69 of subscription calls priced at API rates. See docs/EXECUTION_STATUS.md.
PLAY = {
    "hours": 13.2,
    "counters": [
        [13.2, "hours of play", False],
        [159, "flights in the first 8 hours", False],
        [154, "forced ads in those 8 hours", True],
    ],
    # The player's own notes, trimmed (steps.jsonl of the run), with the play time.
    "notes": [
        ["0:00:36", "Trying a drag from the plane's nose further down to launch it."],
        ["0:04:48", "Tapping NEXT, avoiding the ad-based multiply option."],
        ["1:55:48", "Ad showing. Waiting for the close button to appear."],
        ["11:06:00", "Energy still regenerating (10:18 timer). Waiting."],
    ],
    "foot": "An AI player on an Android emulator, Sept 28-29, 2026. Model calls for the whole "
    "run: about $84 at API prices. The phone screens are invented; the numbers and notes are "
    "the AI player's.",
}

# The prototype, Fold & Fly (a separate repository): bot players simulate the economy and the
# ad policy (sim/sim.mjs, 6 players each): a good player sees 0.107 forced ads per flight (11%
# of the original's 0.97) and reaches the second plane in about 25 minutes. The first playable
# build was made overnight, Sept 28-29; six planes and six courses by Sept 30.
BUILD = {
    "stats": [
        ["Overnight", "to a first playable build: three.js, in a web browser."],
        ["1 in 9 flights", "ends in a forced ad, in bot-player tests. The original: about 1 in 1."],
        [
            "25 minutes",
            "to the first new plane, simulated. Our AI player didn't reach one in 13 "
            "hours of the original.",
        ],
        ["6 planes, 6 courses", "including a harbour town, built from free CC0 models."],
    ],
    "foot": "Footage: the Fold & Fly prototype, recorded frame by frame. Bot-player figures are "
    "simulated.",
    # The edit: [clip, seconds in, seconds out] from footage/prototype.json.
    "edit": [
        ["hangar", 0.2, 2.9],
        ["launch", 0.5, 2.3],
        ["valley", 0.2, 2.4],
        ["finish", 0.5, 3.1],
        ["town", 0.3, 4.2],
    ]
    + [[f"plane{i}", 0.1, 0.55] for i in range(1, 7)],
}


def learn() -> dict:
    """The store page's tags for the plane game, next to what playing it measured."""
    profile = json.loads(
        (ROOT / "experiments/single-games/epic-plane-evolution/tags.json").read_text()
    )
    tags = {t["id"]: t for t in profile["tags"]}
    measured = [
        ("mechanic_upgrades", "CONFIRMED", "three tracks: slingshot, plane, income"),
        ("mechanic_physics", "CONFIRMED", "slingshot launch, glide, skim the ground"),
        ("monetization_ads", "MEASURED", "0.97 forced ads per flight, 27 s each"),
        ("engagement_energy_system", "MEASURED", "5 flights, then a 42-minute wait"),
        ("monetization_pay_to_progress", "MEASURED", "a gem every 5 levels: ad, wait or pay"),
    ]
    rows = []
    for tag_id, kind, text in measured:
        tag = tags[tag_id]
        state = tag["state"]
        prob = tag["probabilities"][state]
        chip = {"present": "PRESENT", "insufficient_evidence": "NOT ENOUGH EVIDENCE"}[state]
        rows.append([tag["label"], state, f"{chip} {prob:.2f}", kind, text])
    return {
        "rows": rows,
        "next": "Next plane: <em>not reached in 13 hours.</em>",
        "loop": ["Slingshot", "Glide and skim", "Coins", "Upgrade"],
        "loopNote": "every flight, the plane goes a little further",
        "kdr": [
            [
                "KEEP",
                "var(--green)",
                [
                    ["Slingshot timing", ""],
                    ["Skimming the ground", ""],
                    ["Three upgrade tracks", ""],
                    ["A new plane at each finish line", ""],
                ],
            ],
            [
                "DROP",
                "var(--red)",
                [["A forced ad after almost every flight", ""], ["The energy limit", ""]],
            ],
            [
                "REPLACE",
                "var(--blue)",
                [
                    ["A gem every 5 levels", "paid in coins"],
                    ["A booster upgraded by ads", "rocket jets you earn"],
                    ["A ×2 needle gamble for an ad", "an optional ×2"],
                ],
            ],
        ],
    }


def build() -> dict:
    manifest = json.loads((HERE / "footage/prototype.json").read_text())
    clips = {c["name"]: c for c in manifest["clips"]}
    edl = []
    for name, a, b in BUILD["edit"]:
        clip = clips[name]
        assert b <= clip["seconds"] + 1e-6, f"{name} is only {clip['seconds']} s long"
        taps = [t for t in clip["taps"] if a <= t["t"] <= b]
        edl.append([clip["start"], a, b, taps])
    return {
        "fps": manifest["fps"],
        "width": manifest["width"],
        "height": manifest["height"],
        "edl": edl,
        "stats": BUILD["stats"],
        "statAt": [1.0, 3.4, 7.4, 9.9],
        "foot": BUILD["foot"],
    }


def store_gaps() -> dict:
    """How many Google Play top-50 grossing games store evidence could not settle."""
    page = (ROOT / "web/index.html").read_text()
    site = json.loads(re.search(r"const DATA = (\{.*?\});\n", page, re.S).group(1))
    mobile = [g for g in site["games"] if g["list"] == "mobile"]

    def unknown(tag: str) -> int:
        return sum(1 for g in mobile if not (g.get("detail") or {}).get("jev", {}).get(tag))

    return {
        "games": len(mobile),
        "ads": unknown("monetization_ads"),
        "energy": unknown("engagement_energy_system"),
    }


def highlight() -> dict:
    """The 30-second cut for LinkedIn: the discovery problem, then play and build.

    Sources: Dream Games' 2023 UK accounts as reported by the Financial Times (via MenaBytes,
    May 2025: $1.5bn revenue, $1bn on marketing and other distribution costs, $130m pre-tax
    loss); Moloco's 2026 report via PocketGamer.biz (190,000 mobile games released in 2025,
    2,500 passed 500,000 downloads in their first year); Google Play Console Help (one category
    of 17 for games, up to five tags, chosen by the developer); GameTagger's own top-100 data.
    """
    gaps = store_gaps()
    n = gaps["games"]
    return {
        "name": "highlight",
        "money": {
            "kicker": "ONE OF MOBILE'S BIGGEST HITS, IN 2023",
            "rows": [
                ["$1.5B", "earned by Dream Games, maker of Royal Match", False],
                ["$1.0B", "spent on marketing and distribution", True],
            ],
            "punch": "Even the hits <em>pay to be found.</em>",
            "source": "Dream Games' 2023 UK accounts, as reported by the Financial Times.",
        },
        "flood": {
            "kicker": "NEW MOBILE GAMES IN 2025",
            "rows": [
                ["190,000", "new mobile games released", False],
                ["2,500", "passed 500,000 downloads in their first year", True],
            ],
            "punch": f"That's about <em>1 in {round(190000 / 2500)}.</em>",
            "source": "Moloco, via PocketGamer.biz, August 2026.",
        },
        "cats": {
            "title": "Recommendations are only as good as what the store knows.",
            "cols": [
                [
                    "A GOOGLE PLAY LISTING",
                    "1 + 5",
                    "one category and up to five tags, picked by the developer",
                    False,
                ],
                [
                    "GAMETAGGER",
                    "189",
                    "gameplay questions answered for every game, each from evidence",
                    True,
                ],
            ],
            "source": "Google Play Console Help (categories and tags). GameTagger: 189 tags, "
            "100 genres.",
        },
        "gaps": {
            "title": "But a store page can't show how a game plays.",
            "cols": [
                [
                    "SHOWS ADS?",
                    f"{gaps['ads']} of {n}",
                    "top-grossing mobile games couldn't be settled from store pages",
                    True,
                ],
                ["ENERGY TIMERS?", f"{gaps['energy']} of {n}", "couldn't be settled either", True],
            ],
            "source": f"Google Play top {n} grossing (US), September 2026, tagged by GameTagger "
            "from store pages, screenshots and trailers.",
        },
        "build": "A playable prototype in days, <em>ready to test with real players</em> before "
        "you staff a team.",
        "end": "Better categories.<br>Better recommendations.",
        "url": "gametagger.vercel.app",
    }


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
            "A banner reads STARTER BUNDLE with a countdown of 02:14:59.",
            "Four items are listed, priced from $1.99 to $9.99.",
            "The top bar shows 1,250 coins and 30 gems.",
        ],
        "jev": jev(),
        "web": {
            "sub": f"{sample['steam_games']} Steam most-played + {sample['mobile_games']} "
            f"Google Play top-grossing · charts of Sept {sample['chart_dates']['steam'][-2:]} and "
            f"{sample['chart_dates']['mobile'][-2:]}, 2026",
            "genres": [list(x) for x in mix.most_common(7)],
            "median": statistics.median(g["rich"]["present"] for g in games),
            "games_total": len(games),
            "games": rows,
        },
        "play": PLAY,
        "learn": learn(),
        "build": build(),
        "pitch": [
            ["01", "Spot", "a game climbing the charts"],
            ["02", "Play", "an AI player plays it for hours"],
            ["03", "Learn", "what makes it work, tag by tag"],
            ["04", "Build", "a playable prototype, tuned by bot players"],
        ],
        "endtitle": "Learn why hit games work.<br>Prototype the next one in days.",
        "endline": "Claude describes · Jev decides, tag by tag · an AI player plays<br>"
        "Catalog seeded from the NitroGen game list · Jev by TypeSafe",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fonts", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--cut", choices=["full", "highlight"], default="full")
    parser.add_argument("--still", help="comma-separated times: render stills to PNGs instead")
    args = parser.parse_args()
    fonts = args.fonts.read_text() if args.fonts and args.fonts.exists() else ""
    page = (HERE / "scene.html").read_text()
    payload = data()
    seconds = SECONDS
    if args.cut == "highlight":
        payload["cut"] = highlight()
        seconds = 30
    args.out = args.out or ROOT / "web" / (
        "trailer.mp4" if args.cut == "full" else "linkedin/trailer-30s.mp4"
    )
    page = page.replace("/*FONTS*/", fonts).replace("/*DATA*/", json.dumps(payload))
    page = page.replace("/*GAMES*/", (HERE / "games.js").read_text())
    node_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "scene.html").write_text(page)
        (work / "footage").mkdir()
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(HERE / "footage/prototype.mp4"),
                "-q:v",
                "2",
                "-start_number",
                "0",
                str(work / "footage/%05d.jpg"),
            ],
            check=True,
        )
        (work / "render.js").write_text(RENDER_JS)
        frames = work / "frames"
        frames.mkdir()
        subprocess.run(
            [
                "node",
                str(work / "render.js"),
                (work / "scene.html").as_uri(),
                str(frames),
                str(FPS),
                str(seconds),
                args.still or "",
            ],
            check=True,
            env={**os.environ, "NODE_PATH": node_root.strip(), "CHROME": CHROME},
        )
        if args.still:
            for i, t in enumerate(args.still.split(",")):
                target = args.out.with_name(f"still-{float(t):05.1f}.png")
                shutil.copy(frames / f"{i:05d}.png", target)
                print(target)
            return
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                str(frames / "%05d.png"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-crf",
                "21",
                "-preset",
                "slow",
                "-movflags",
                "+faststart",
                str(args.out),
            ],
            check=True,
        )
    print(args.out)


if __name__ == "__main__":
    main()
