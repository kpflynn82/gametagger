"""LinkedIn image set for the Jev versus previous-method benchmark.

Reads only the committed results (``results/summary.json``), renders six 1200 x 1500 slides as
HTML and screenshots them with a headless Chromium. Every slide carries its sample, dates and
answer-key method. Run from the repository root:

    uv run python experiments/jev-vs-legacy/linkedin/build.py [--fonts path/to/embedded.css]

``--fonts`` is an optional CSS file of @font-face rules (Chivo and Chivo Mono embedded as data
URIs); without it the slides fall back to the system sans.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results" / "summary.json"
PER_GAME = HERE.parent / "results" / "per-game.jsonl"
CHROME = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"

ARMS = ("rich", "legacy-deep", "legacy-standard")
NAME = {
    "rich": "Jev pipeline",
    "legacy-deep": "One prompt · Opus 4.8",
    "legacy-standard": "One prompt · Haiku 4.5",
}
COLOR = {"rich": "#2a78d6", "legacy-deep": "#1baf7a", "legacy-standard": "#eb6834"}
VISION = "#9ec5f4"  # lighter step of the Jev blue: the Claude vision share of the pipeline
JEV = "#184f95"  # darker step of the same blue: Jev's own judging step

CSS = """
*{box-sizing:border-box;margin:0}
body{width:1200px;height:1500px;overflow:hidden;background:#fbfbfa;color:#101418;
font-family:Chivo,"Liberation Sans",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.s{width:1200px;height:1500px;padding:76px 84px 64px;display:flex;flex-direction:column}
.top{display:flex;justify-content:space-between;font:500 20px/1 "Chivo Mono",monospace;
letter-spacing:.08em;text-transform:uppercase;color:#5a5f66}
.top b{color:#2a78d6;font-weight:700}
h1{font-weight:800;font-size:68px;line-height:1.04;letter-spacing:-.022em;margin-top:56px;
text-wrap:balance}
.sub{font-size:30px;line-height:1.38;color:#474c53;margin-top:26px;max-width:960px}
.chart{margin-top:84px;display:flex;flex-direction:column;gap:28px}
.ct{font-weight:600;font-size:25px;color:#101418}
.cn{font-size:21px;color:#5a5f66;margin-top:-18px}
.row{display:grid;grid-template-columns:300px 1fr;align-items:center;gap:20px}
.lab{font-size:24px;line-height:1.2;color:#101418}
.lab small{display:block;font-size:18px;color:#6c7178;margin-top:3px}
.track{display:flex;align-items:center;gap:14px;height:58px}
.bar{display:flex;height:58px;gap:3px}
.seg{height:100%}
.seg:last-child{border-radius:0 6px 6px 0}
.val{font-weight:800;font-size:34px;line-height:1;font-variant-numeric:tabular-nums;color:#101418;white-space:nowrap}
.key{display:flex;flex-wrap:wrap;gap:10px 30px;font-size:21px;color:#474c53}
.key i{display:inline-block;width:18px;height:18px;border-radius:4px;margin-right:9px;
vertical-align:-2px}
.hero{display:flex;gap:28px}
.hero .h{flex:1;border-top:6px solid;padding-top:22px}
.hero .n{font-weight:800;font-size:88px;line-height:1;letter-spacing:-.03em;
font-variant-numeric:tabular-nums}
.hero .t{font-size:23px;line-height:1.3;color:#474c53;margin-top:14px}
.foot{margin-top:auto;padding-top:22px;border-top:2px solid #e3e3df;font-size:18px;
line-height:1.45;color:#6c7178}
.steps{display:flex;flex-direction:column;gap:26px;margin-top:56px}
.lane{border:2px solid #e3e3df;border-radius:14px;padding:22px 24px;display:flex;
flex-direction:column;gap:14px;background:#fff}
.lane .lt{display:flex;align-items:baseline;gap:14px;font-weight:800;font-size:28px}
.lane .lt small{font:500 18px/1 "Chivo Mono",monospace;color:#5a5f66;letter-spacing:.04em}
.flow{display:flex;align-items:stretch;gap:10px}
.box{flex:1;border-radius:10px;padding:12px 14px;font-size:19px;line-height:1.3;color:#2a2f35;
background:#f2f4f7}
.box b{display:block;font-size:14px;letter-spacing:.07em;text-transform:uppercase;
font-family:"Chivo Mono",monospace;margin-bottom:5px}
.arrow{align-self:center;font-size:26px;color:#9aa0a8}
.diff{display:grid;grid-template-columns:230px 1fr 1fr;font-size:19px;line-height:1.3;
border-top:2px solid #e3e3df}
.diff div{padding:9px 12px 9px 0;border-bottom:1px solid #e3e3df}
.diff .h{font:500 15px/1.3 "Chivo Mono",monospace;text-transform:uppercase;letter-spacing:.06em;
color:#5a5f66}
.step{display:grid;grid-template-columns:64px 1fr;gap:22px;align-items:start}
.step .k{font:700 30px/1.2 "Chivo Mono",monospace;color:#2a78d6}
.step p{font-size:27px;line-height:1.4;color:#2a2f35}
.step p b{color:#101418}
"""


def esc(v) -> str:
    return html.escape(str(v))


def usd(v: float, digits: int = 3) -> str:
    return f"${v:.{digits}f}"


def pct(v: float) -> str:
    return f"{100 * v:.0f}%"


def secs(ms: float) -> str:
    s = ms / 1000
    return f"{s:.0f} s" if s >= 20 else f"{s:.1f} s"


def bars(rows, scale: float, width: int = 500) -> str:
    """rows: (arm, label, sublabel, [(value, color)], value_text). One shared linear scale."""
    out = []
    for _arm, label, sub, segs, text in rows:
        seg_html = "".join(
            f'<div class="seg" style="width:{max(4, width * v / scale):.0f}px;background:{c}">'
            "</div>"
            for v, c in segs
            if v > 0
        )
        small = f"<small>{esc(sub)}</small>" if sub else ""
        out.append(
            f'<div class="row"><div class="lab">{esc(label)}{small}</div>'
            f'<div class="track"><div class="bar">{seg_html}</div>'
            f'<div class="val">{text}</div></div></div>'
        )
    return "".join(out)


def slide(n: int, total: int, title: str, sub: str, body: str, foot: str, fonts: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset=utf-8><style>{fonts}{CSS}</style></head>"
        f'<body><div class="s"><div class="top"><span><b>GameTagger</b> benchmark · '
        f"100 top games</span><span>{n}/{total}</span></div><h1>{title}</h1>"
        f'<p class="sub">{sub}</p>{body}<div class="foot">{foot}</div></div></body></html>'
    )


def figures(s: dict) -> dict:
    A = s["arms"]
    f = {"sample": s["sample"], "run_date": s["run_date"]}
    for arm in ARMS:
        a = A[arm]
        n = a["completed"] or 1
        f[arm] = {
            "games": a["games"],
            "completed": a["completed"],
            "failure_rate": a["failure_rate"],
            "recall_all": a["steam_tags"]["all_mapped"]["recall_pooled"],
            "recall_shared": a["steam_tags"]["shared_vocabulary"]["recall_pooled"],
            "said_absent": a["steam_tags"]["all_mapped"]["contradiction_rate"],
            "tags": a["tags_per_game"]["positive_in_genome_vocabulary"]["median"],
            "time": a["latency_ms"]["method"]["median"],
            "stages": {k: v["median"] for k, v in a["latency_ms"]["stages"].items()},
            "cost": a["cost_usd"]["per_game"]["mean"],
            "cost_claude": a["cost_usd"].get("anthropic_total", 0) / n,
            "cost_jev": a["cost_usd"].get("typesafe_total", 0) / n,
            "tokens": {
                p: {k: a["tokens"][p][k]["mean"] for k in ("input_tokens", "output_tokens")}
                for p in a["tokens"]
                if a["tokens"][p]["input_tokens"]["n"]
            },
        }
    f["diff"] = s["recall_difference_vs_rich"]
    # Old-method answers the original site read as empty (no yes/no key it could unpack).
    f["unreadable"] = {a: 0 for a in ARMS[1:]}
    if PER_GAME.exists():
        for line in PER_GAME.read_text().splitlines():
            r = json.loads(line)
            if r["arm"] in f["unreadable"] and r["status"] == "valid" and not r.get("tags"):
                f["unreadable"][r["arm"]] += 1
    return f


def footer(f: dict, *, accuracy: bool = False) -> str:
    s = f["sample"]
    text = (
        f"{s['games_compared']} games: Steam most-played ({s['chart_dates']['steam']}) + Google "
        f"Play US top-grossing ({s['chart_dates']['mobile']}), run {f['run_date']}. Identical "
        "evidence for every method."
    )
    if accuracy:
        text += (
            f" Answer key: top 20 Steam player tags ({s['games_with_steam_answer_key']} Steam "
            "games), draft crosswalk; a missing tag never counts as a no."
        )
    else:
        text += " List prices, provider-reported tokens."
    return esc(text)


def build(f: dict, fonts: str) -> list[tuple[str, str]]:
    R, OP, H = f["rich"], f["legacy-deep"], f["legacy-standard"]
    total = 7
    slides = []

    # 1 accuracy
    rows = [
        (a, NAME[a], None, [(f[a]["recall_all"], COLOR[a])], pct(f[a]["recall_all"])) for a in ARMS
    ]
    shared = [
        (a, NAME[a], None, [(f[a]["recall_shared"], COLOR[a])], pct(f[a]["recall_shared"]))
        for a in ARMS
    ]
    d = f["diff"]["legacy-deep"]["shared_vocabulary"]
    close = d["ci95_points"]["low"] <= 0 <= d["ci95_points"]["high"]
    body = (
        '<div class="chart"><div class="ct">Share of what players tagged that each method found'
        '</div><div class="cn">Every attribute the Steam tags point to</div>'
        + bars(rows, 1.0)
        + '<div class="ct" style="margin-top:14px">Only attributes both vocabularies can name'
        '</div><div class="cn">The fair head-to-head'
        + (
            f": Jev vs Opus is within noise ({d['rich_minus_old_points']:+.0f} points, 95% "
            f"interval {d['ci95_points']['low']:+.0f} to {d['ci95_points']['high']:+.0f})"
            if close
            else f": Jev {d['rich_minus_old_points']:+.0f} points vs Opus (95% interval "
            f"{d['ci95_points']['low']:+.0f} to {d['ci95_points']['high']:+.0f})"
        )
        + "</div>"
        + bars(shared, 1.0)
        + "</div>"
    )
    slides.append(
        (
            "1-accuracy",
            slide(
                1,
                total,
                f"Jev found {pct(R['recall_all'])} of what players tag. "
                f"One big prompt found {pct(OP['recall_all'])}.",
                "Today's top 100 games, tagged two ways on identical evidence and checked against "
                "Steam players' tags. "
                + (
                    f"On attributes both methods can name, they are level: "
                    f"{pct(R['recall_shared'])} vs {pct(OP['recall_shared'])}."
                    if close
                    else f"On attributes both methods can name: {pct(R['recall_shared'])} vs "
                    f"{pct(OP['recall_shared'])}."
                ),
                body,
                footer(f, accuracy=True)
                + esc(
                    f" Haiku: the old site could not read {f['unreadable']['legacy-standard']}"
                    f" of {H['completed']} answers, counted as given."
                ),
                fonts,
            ),
        )
    )

    # 2 how each method works
    old_c, jev_c = COLOR["legacy-deep"], COLOR["rich"]
    diff_rows = [
        ("Knows the game's name", "Yes, can lean on memory", "No: title withheld from Jev"),
        ("Images", "2 per store, 600 px wide", "Every screenshot + 6 trailer clips"),
        ("Model calls", "1", "One per image, then Jev in batches"),
        ("Answers", "Yes / no per tag", "Present, absent, unknown, conflicting"),
        ("Genre", "Must pick 1 of 59", "v4.1 hierarchy; may decline"),
        ("Evidence trail", "None", "Every tag cites its sources"),
    ]
    diff = (
        '<div class="diff"><div class="h"></div><div class="h" style="color:'
        + old_c
        + '">One prompt</div><div class="h" style="color:'
        + jev_c
        + '">Jev pipeline</div>'
        + "".join(
            f"<div><b>{esc(a)}</b></div><div>{esc(b)}</div><div>{esc(c)}</div>"
            for a, b, c in diff_rows
        )
        + "</div>"
    )

    def lane(color, title, tag, steps):
        boxes = '<div class="arrow">→</div>'.join(
            f'<div class="box"><b style="color:{color}">{esc(h)}</b>{esc(t)}</div>'
            for h, t in steps
        )
        return (
            f'<div class="lane" style="border-color:{color}"><div class="lt">{esc(title)}'
            f'<small>{esc(tag)}</small></div><div class="flow">{boxes}</div></div>'
        )

    body = (
        '<div class="chart" style="margin-top:56px;gap:18px">'
        + lane(
            old_c,
            "One prompt",
            "Haiku 4.5 or Opus 4.8",
            [
                ("Reads", "Game name, text cut to 1,000 characters, 2 screenshots per store"),
                ("Asks", "One Claude call for the whole game"),
                ("Returns", "About 91 yes/no tags and 1 of 59 genres"),
            ],
        )
        + lane(
            jev_c,
            "Jev pipeline",
            "Claude Sonnet 5 + Jev",
            [
                ("Looks", "Claude describes each image and trailer clip, never naming genres"),
                ("Splits", "All text and descriptions become numbered claims"),
                ("Judges", "Jev answers 189 attributes and the genre, one question each"),
            ],
        )
        + diff
        + "</div>"
    )
    slides.append(
        (
            "2-how",
            slide(
                2,
                total,
                "Same evidence, two very different ways to use it.",
                "The old site asks one model one big question. The new pipeline separates "
                "looking from judging, so every answer can be traced to what was seen.",
                body,
                footer(f),
                fonts,
            ),
        )
    )

    # 3 cost: where the money goes
    scale = max(f[a]["cost"] for a in ARMS)
    rows = [
        (
            "rich",
            NAME["rich"],
            "Claude vision + Jev",
            [(R["cost_claude"], VISION), (R["cost_jev"], JEV)],
            usd(R["cost"]),
        ),
        (
            "legacy-deep",
            NAME["legacy-deep"],
            None,
            [(OP["cost"], COLOR["legacy-deep"])],
            usd(OP["cost"]),
        ),
        (
            "legacy-standard",
            NAME["legacy-standard"],
            None,
            [(H["cost"], COLOR["legacy-standard"])],
            usd(H["cost"]),
        ),
    ]
    jev_share = R["cost_jev"] / R["cost"] if R["cost"] else 0
    body = (
        '<div class="chart"><div class="ct">Cost per game (mean)</div>'
        + bars(rows, scale)
        + f'<div class="key"><span><i style="background:{VISION}"></i>Claude describing '
        f'screenshots and trailer</span><span><i style="background:{JEV}"></i>Jev judging '
        "every attribute</span></div></div>"
        f'<div class="hero" style="margin-top:56px"><div class="h" style="border-color:{JEV}">'
        f'<div class="n">{usd(R["cost_jev"], 4)}</div><div class="t">Jev\'s own judging step, '
        f"per game ({189} attributes plus the genre)</div></div>"
        f'<div class="h" style="border-color:{COLOR["legacy-deep"]}"><div class="n">'
        f'{usd(OP["cost"])}</div><div class="t">The old one-prompt method on Opus, per game</div>'
        "</div></div>"
    )
    slides.append(
        (
            "3-cost",
            slide(
                3,
                total,
                f"Jev's judging costs {usd(R['cost_jev'], 4)} a game. The pictures cost the rest.",
                f"The full pipeline costs more than one prompt, but {100 * (1 - jev_share):.0f}% "
                f"of its bill is Claude describing images. Jev's part is {100 * jev_share:.0f}%.",
                body,
                footer(f),
                fonts,
            ),
        )
    )

    # 4 time per stage
    obs, dec = R["stages"].get("observe", 0), R["stages"].get("decide", 0)
    scale = max(obs + dec, OP["time"], H["time"])
    rows = [
        (
            "rich",
            NAME["rich"],
            "describe, then judge",
            [(obs, VISION), (dec, JEV)],
            secs(obs + dec),
        ),
        (
            "legacy-deep",
            NAME["legacy-deep"],
            None,
            [(OP["time"], COLOR["legacy-deep"])],
            secs(OP["time"]),
        ),
        (
            "legacy-standard",
            NAME["legacy-standard"],
            None,
            [(H["time"], COLOR["legacy-standard"])],
            secs(H["time"]),
        ),
    ]
    body = (
        '<div class="chart"><div class="ct">Wall-clock time per game (median of each stage)'
        "</div>"
        + bars(rows, scale)
        + f'<div class="key"><span><i style="background:{VISION}"></i>Claude describing '
        'each image and trailer clip, one request each</span><span><i style="background:'
        f'{JEV}"></i>Jev: {189}+ questions in batches</span></div></div>'
    )
    slides.append(
        (
            "4-time",
            slide(
                4,
                total,
                f"Jev decides in {secs(dec)}. Looking at the pictures takes {secs(obs)}.",
                "The old method answers in one call. The new pipeline first has Claude describe "
                "every screenshot and trailer clip, then Jev judges. That first step is the slow "
                "one, and it is the one to optimize next.",
                body,
                footer(f)
                + esc(" Shared evidence gathering is excluded; three games ran in parallel."),
                fonts,
            ),
        )
    )

    # 5 tokens
    def tk(arm, provider, key):
        return f[arm]["tokens"].get(provider, {}).get(key, 0)

    rin, rout = tk("rich", "anthropic", "input_tokens"), tk("rich", "anthropic", "output_tokens")
    jin = tk("rich", "typesafe", "input_tokens")
    scale = max(
        rin + rout,
        jin,
        *(
            tk(a, "anthropic", "input_tokens") + tk(a, "anthropic", "output_tokens")
            for a in ARMS[1:]
        ),
    )

    def k(v):
        return f"{v / 1000:.1f}k"

    rows = [
        (
            "rich",
            "Claude vision",
            "in the Jev pipeline",
            [(rin, "#5598e7"), (rout, VISION)],
            k(rin + rout),
        ),
        ("rich", "Jev", "input; output is free", [(jin, JEV)], k(jin)),
        *[
            (
                a,
                NAME[a],
                None,
                [
                    (tk(a, "anthropic", "input_tokens"), COLOR[a]),
                    (tk(a, "anthropic", "output_tokens"), COLOR[a] + "66"),
                ],
                k(tk(a, "anthropic", "input_tokens") + tk(a, "anthropic", "output_tokens")),
            )
            for a in ARMS[1:]
        ],
    ]
    body = (
        '<div class="chart"><div class="ct">Tokens per game (mean): input, then output</div>'
        + bars(rows, scale)
        + '<div class="key"><span>Solid: input tokens. Lighter end: output tokens.'
        "</span></div></div>"
    )
    slides.append(
        (
            "5-tokens",
            slide(
                5,
                total,
                f"Jev reads {k(jin)} tokens a game, at $0.042 per million.",
                "That is more text than the old prompt "
                f"({k(tk('legacy-deep', 'anthropic', 'input_tokens'))} in) because Jev is "
                "asked every attribute separately, with only the evidence that "
                "may answer it. Its price per token is about 1/120th of Opus.",
                body,
                footer(f),
                fonts,
            ),
        )
    )

    # 6 depth
    rows = [(a, NAME[a], None, [(f[a]["tags"], COLOR[a])], f"{f[a]['tags']:.0f}") for a in ARMS]
    scale = max(f[a]["tags"] for a in ARMS)
    body = (
        '<div class="chart"><div class="ct">Attributes reported present per game (median)</div>'
        '<div class="cn">Old keys translated into the same vocabulary</div>'
        + bars(rows, scale)
        + "</div>"
        f'<div class="hero" style="margin-top:56px"><div class="h" style="border-color:'
        f'{COLOR["rich"]}"><div class="n">{pct(R["said_absent"])}</div><div class="t">of '
        "player-tagged attributes Jev called absent</div></div>"
        f'<div class="h" style="border-color:{COLOR["legacy-deep"]}"><div class="n">'
        f'{pct(OP["said_absent"])}</div><div class="t">the same for one prompt on Opus</div>'
        "</div></div>"
    )
    slides.append(
        (
            "6-depth",
            slide(
                6,
                total,
                f"{R['tags']:.0f} attributes per game, each with its evidence.",
                "Jev answers present, absent, unknown or conflicting for every attribute, and "
                "never guesses a genre to fill a gap. The old prompt has to say yes or no.",
                body,
                footer(f, accuracy=True),
                fonts,
            ),
        )
    )

    # 7 method and caveats
    s = f["sample"]
    steps = [
        (
            "01",
            f"<b>{s['games_compared']} games</b>: the top 50 on Steam's most-played chart "
            f"({s['chart_dates']['steam']}) and the top 50 on Google Play US top-grossing "
            f"({s['chart_dates']['mobile']}).",
        ),
        (
            "02",
            "<b>Same evidence for every method</b>: store listing, Wikipedia, up to 4 "
            "screenshots per store and the store trailer, gathered once.",
        ),
        (
            "03",
            "<b>Old method</b>: the original site's single Claude prompt, copied verbatim, "
            "on Haiku 4.5 and on Opus 4.8. <b>New</b>: Claude Sonnet 5 describes the images "
            "without naming genres, then Jev judges each attribute.",
        ),
        (
            "04",
            f"<b>Answer key</b>: Steam players' top 20 tags ({s['games_with_steam_answer_key']}"
            " Steam games), through a draft crosswalk. Mobile games have no public equivalent; a "
            "blinded human review is pending.",
        ),
        (
            "05",
            f"<b>Old site's parser</b>: in {f['unreadable']['legacy-standard']} of "
            f"{H['completed']} games Haiku nested its answers where the original code does not "
            "look, so the old site would have recorded no tags. Kept as is; Opus had "
            f"{f['unreadable']['legacy-deep']}.",
        ),
        (
            "06",
            "<b>Limits</b>: one run, list prices, wall-clock times with 3 games in parallel. "
            "Steam tags reward saying yes, so precision is not measured here.",
        ),
    ]
    body = (
        '<div class="steps">'
        + "".join(f'<div class="step"><div class="k">{k_}</div><p>{t}</p></div>' for k_, t in steps)
        + "</div>"
    )
    slides.append(
        (
            "7-method",
            slide(
                7,
                total,
                "How we measured it",
                "Built to be checked. The code, crosswalks and per-game results are in the repo.",
                body,
                esc(
                    f"Failure rate: Jev pipeline {pct(R['failure_rate'])}, Opus "
                    f"{pct(OP['failure_rate'])}, Haiku {pct(H['failure_rate'])}. "
                    "Crosswalks are drafts pending review."
                ),
                fonts,
            ),
        )
    )
    return slides


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fonts", type=Path)
    parser.add_argument("--out", type=Path, default=HERE)
    args = parser.parse_args()
    fonts = args.fonts.read_text() if args.fonts and args.fonts.exists() else ""
    f = figures(json.loads(RESULTS.read_text()))
    args.out.mkdir(parents=True, exist_ok=True)
    for name, page in build(f, fonts):
        src = args.out / f"{name}.html"
        src.write_text(page)
        subprocess.run(
            [
                CHROME,
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                "--window-size=1200,1500",
                "--virtual-time-budget=3000",
                f"--screenshot={(args.out / f'{name}.png')}",
                src.resolve().as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        if args.fonts:
            src.unlink()  # the HTML embeds the font files; keep only the PNG
        print(args.out / f"{name}.png")


if __name__ == "__main__":
    main()
