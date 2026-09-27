"""Render the ~53-second square explainer video (silent, 1080 x 1080, 30 fps).

    uv run python experiments/jev-vs-legacy/video/build.py [--fonts embedded.css] [--still SECONDS]

The scenes live in ``scene.html``; ``render(t)`` draws the frame at time ``t``. Numbers come from
the committed results (``results/summary.json``, ``results/per-game.jsonl``,
``cost-test/summary.json``) and the worked example in ``example.json``. No store screenshots or
trailers are used. Needs Node with the ``playwright`` package and ffmpeg.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
CHROME = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
FPS, SECONDS = 30, 52.6

RENDER_JS = """
const { chromium } = require('playwright');
const [page_url, out, fps, seconds, still] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  const page = await browser.newPage({ viewport: { width: 1080, height: 1080 } });
  await page.goto(page_url);
  await page.evaluate(() => document.fonts.ready);
  const count = Math.round(fps * seconds);
  const times = still ? [Number(still)] : [...Array(count).keys()].map(i => i / fps);
  for (const [i, t] of times.entries()) {
    await page.evaluate(t => window.render(t), t);
    await page.screenshot({ path: `${out}/${String(i).padStart(5, '0')}.png` });
  }
  await browser.close();
})();
"""


def data() -> dict:
    s = json.loads((EXP / "results/summary.json").read_text())
    c = json.loads((EXP / "cost-test/summary.json").read_text())
    ex = json.loads((HERE / "example.json").read_text())
    rich, old = s["arms"]["rich"], s["arms"]["legacy-deep"]
    games = [json.loads(line) for line in (EXP / "results/per-game.jsonl").read_text().splitlines()]
    legacy = next(g for g in games if g["game_id"] == "steam-730" and g["arm"] == "legacy-deep")
    mapped = "all_mapped"
    stats = [
        {
            "label": "Tags found",
            "note": "median per game",
            "kind": "n",
            "old": old["tags_per_game"]["positive_in_genome_vocabulary"]["median"],
            "jev": rich["tags_per_game"]["positive_in_genome_vocabulary"]["median"],
        },
        {
            "label": "Player tags matched",
            "note": "Steam players' top 20",
            "kind": "pct",
            "old": old["steam_tags"][mapped]["recall_pooled"],
            "jev": rich["steam_tags"][mapped]["recall_pooled"],
        },
        {
            "label": 'Wrongly said "no"',
            "note": "to a tag players gave it",
            "kind": "pct",
            "old": old["steam_tags"][mapped]["contradiction_rate"],
            "jev": rich["steam_tags"][mapped]["contradiction_rate"],
        },
        {
            "label": "Cost",
            "note": "per game, all in",
            "kind": "cents",
            "old": old["cost_usd"]["per_game"]["mean"],
            "jev": c["arms"]["rich-haiku"]["total_cost_per_game"],
            "star": True,
        },
    ]
    for row in stats:  # Jev's figure animates from the old one
        row["jev_from"] = row["old"]
    sample = s["sample"]
    shared = (
        rich["steam_tags"]["shared_vocabulary"]["recall_pooled"],
        old["steam_tags"]["shared_vocabulary"]["recall_pooled"],
    )
    foot = (
        f"{sample['steam_games']} Steam most-played + {sample['mobile_games']} Google Play "
        f"top-grossing, Sept 2026. Old prompt = one call to Claude Opus 4.8. Player tags via a "
        f"draft crosswalk; on tags both can name they tie ({100 * shared[0]:.0f}% vs "
        f"{100 * shared[1]:.0f}%). *Jev cost from a {c['games']}-game test with Claude Haiku "
        "describing images in half-price batches."
    )
    return {
        "old": [[k, v] for k, v in legacy["tags"].items()],
        "ex": ex,
        "stats": stats,
        "foot": foot,
        "end": "Claude describes. Jev decides, tag by tag.<br>GameTagger · Jev by TypeSafe",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fonts", type=Path)
    parser.add_argument("--out", type=Path, default=HERE / "gametagger-jev.mp4")
    parser.add_argument("--still", type=float, help="render one frame at this time to a PNG")
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
             str(FPS), str(SECONDS), "" if args.still is None else str(args.still)],
            check=True,
            env={**os.environ, "NODE_PATH": node_root.strip(), "CHROME": CHROME},
        )  # fmt: skip
        if args.still is not None:
            target = args.out.with_name(f"still-{args.still:05.1f}.png")
            shutil.copy(frames / "00000.png", target)
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
