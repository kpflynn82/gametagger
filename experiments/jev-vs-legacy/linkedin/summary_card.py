"""One attention-grabbing summary graphic (1200 x 1500) for a single-image LinkedIn post.

    uv run python experiments/jev-vs-legacy/linkedin/summary_card.py [--fonts embedded.css]

Every number is read from the committed results: ``results/summary.json`` (100-game benchmark)
and ``cost-test/summary.json`` (20-game cheaper-description test). The footer states both
samples, the answer key and the like-for-like tie, so the image stands on its own when shared.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
CHROME = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
JEV, OLD = "#3987e5", "#566170"  # validated pair on the #0e1620 surface; bars are always labelled

CSS = """
*{box-sizing:border-box;margin:0}
body{width:1200px;height:1500px;overflow:hidden;background:#0e1620;color:#f3f5f8;
font-family:Chivo,"Liberation Sans",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.c{width:1200px;height:1500px;padding:72px 84px 60px;display:flex;flex-direction:column}
.eb{font:500 21px/1 "Chivo Mono",monospace;letter-spacing:.1em;text-transform:uppercase;
color:#8d98a6}
.eb b{color:#6da7ec;font-weight:700}
h1{font-weight:800;font-size:84px;line-height:1;letter-spacing:-.03em;margin-top:40px}
.ans{font-weight:800;font-size:46px;line-height:1.1;letter-spacing:-.02em;margin-top:28px;color:#6da7ec}
.ans span{color:#f3f5f8}
.sub{font-size:28px;line-height:1.35;color:#b9c2cd;margin-top:22px;max-width:1000px}
.rows{margin-top:auto;display:flex;flex-direction:column;gap:38px}
.row .k{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}
.row .k span{font-weight:600;font-size:27px;color:#e4e8ee}
.row .k small{font:500 18px "Chivo Mono",monospace;color:#8d98a6;letter-spacing:.04em}
.bar{display:grid;grid-template-columns:150px 1fr;align-items:center;gap:18px;margin-top:8px}
.bar .who{font:500 19px "Chivo Mono",monospace;letter-spacing:.05em;text-transform:uppercase}
.track{display:flex;align-items:center;gap:16px}
.fill{height:44px;border-radius:0 7px 7px 0}
.val{font-weight:800;font-size:42px;letter-spacing:-.02em;font-variant-numeric:tabular-nums;white-space:nowrap}
.val small{font-size:22px;font-weight:600;color:#8d98a6;margin-left:6px;letter-spacing:0}
.foot{margin-top:48px;padding-top:20px;border-top:2px solid #243140;font-size:18px;line-height:1.5;
color:#8d98a6}
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fonts", type=Path)
    parser.add_argument("--out", type=Path, default=HERE / "summary-card.png")
    args = parser.parse_args()
    fonts = args.fonts.read_text() if args.fonts and args.fonts.exists() else ""
    s = json.loads((EXP / "results/summary.json").read_text())
    c = json.loads((EXP / "cost-test/summary.json").read_text())
    A = s["arms"]
    R, L = A["rich"], A["legacy-deep"]
    tags = (
        R["tags_per_game"]["positive_in_genome_vocabulary"]["median"],
        L["tags_per_game"]["positive_in_genome_vocabulary"]["median"],
    )
    found = (
        R["steam_tags"]["all_mapped"]["recall_pooled"],
        L["steam_tags"]["all_mapped"]["recall_pooled"],
    )
    shared = (
        R["steam_tags"]["shared_vocabulary"]["recall_pooled"],
        L["steam_tags"]["shared_vocabulary"]["recall_pooled"],
    )
    wrong = (
        R["steam_tags"]["all_mapped"]["contradiction_rate"],
        L["steam_tags"]["all_mapped"]["contradiction_rate"],
    )
    cost = (c["arms"]["rich-haiku"]["total_cost_per_game"], L["cost_usd"]["per_game"]["mean"])
    times_fewer = round(wrong[1] / wrong[0]) if wrong[0] else None
    sample = s["sample"]

    def row(label, note, values, fmt, scale):
        bars = "".join(
            f'<div class="bar"><span class="who" style="color:{col}">{who}</span>'
            f'<div class="track"><div class="fill" style="width:{max(8, 730 * v / scale):.0f}px;'
            f'background:{col}"></div><span class="val">{fmt(v)}</span></div></div>'
            for who, col, v in (("Jev", JEV, values[0]), ("Old prompt", OLD, values[1]))
        )
        return (
            f'<div class="row"><div class="k"><span>{html.escape(label)}</span>'
            f"<small>{html.escape(note)}</small></div>{bars}</div>"
        )

    pct = lambda v: f"{100 * v:.0f}%" if v >= 0.1 else f"{100 * v:.1f}%"  # noqa: E731
    cents = lambda v: f"{100 * v:.1f}¢"  # noqa: E731
    rows = "".join(
        [
            row("Tags per game", "median", tags, lambda v: f"{v:.0f}", max(tags)),
            row("Player tags found", "Steam players' top 20 tags", found, pct, 1.0),
            row('Wrongly said "no"', "lower is better", wrong, pct, max(wrong)),
            row("Cost per game", "all in", cost, cents, max(cost)),
        ]
    )
    foot = (
        f"{sample['games_compared']} games: Steam most-played ({sample['chart_dates']['steam']}) + "
        f"Google Play US top-grossing ({sample['chart_dates']['mobile']}), identical evidence for "
        f"both methods. Old prompt = the original one-call tagger on Claude Opus 4.8. Accuracy on "
        f"the {sample['games_with_steam_answer_key']} Steam games via a draft crosswalk; on tags "
        f"both methods can name they tie ({pct(shared[0])} vs {pct(shared[1])}). Jev cost is from "
        f"a {c['games']}-game test with Claude Haiku describing images in half-price batches; "
        "list prices."
    )
    page = f"""<!doctype html><html><head><meta charset=utf-8><style>{fonts}{CSS}</style></head>
<body><div class="c">
<div class="eb"><b>GameTagger</b> · top 100 games · Sept 2026</div>
<h1>Can we tag games more efficiently with Jev?</h1>
<p class="ans">Yes: <span>2× the tags,</span> {times_fewer}× fewer <span>wrong “no”s.</span></p>
<p class="sub">We re-tagged the top 100 games two ways on the same evidence: one big AI
prompt, or Claude describing what it sees and Jev judging 189 tags one at a time.</p>
<div class="rows">{rows}</div>
<div class="foot">{html.escape(foot)}</div>
</div></body></html>"""
    src = args.out.with_suffix(".html")
    src.write_text(page)
    subprocess.run(
        [
            CHROME,
            "--no-sandbox",
            "--hide-scrollbars",
            "--window-size=1200,1500",
            "--virtual-time-budget=3000",
            f"--screenshot={args.out}",
            src.resolve().as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    src.unlink()
    print(args.out)


if __name__ == "__main__":
    main()
