"""The write-up: a self-contained HTML report with inline SVG charts, a 1200 x 675 social card
(HTML, and PNG when a headless Chromium is available) and a short post text.

Every figure states its sample, dates and answer-key method. Numbers come only from ``score``;
the narrative uses guarded wording (a difference whose 95% interval spans zero is reported as no
clear difference). Charts built from test fixtures carry an "Illustrative / UI test data"
watermark and are never presented as measured results.
"""

from __future__ import annotations

import html
import shutil
import subprocess
from pathlib import Path
from typing import Any

ARMS = ("rich", "legacy-standard", "legacy-deep")
SHORT = {"rich": "Jev rich mode", "legacy-standard": "Old · Haiku", "legacy-deep": "Old · Opus"}
LONG = {
    "rich": "Jev rich mode (Claude vision Observer + Jev)",
    "legacy-standard": "Old method, standard (Claude Haiku 4.5, one call)",
    "legacy-deep": "Old method, deep (Claude Opus 4.8, one call)",
}
CSS_VAR = {"rich": "--s-rich", "legacy-standard": "--s-haiku", "legacy-deep": "--s-opus"}

CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;
--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);--shared:#c3c2b7;
--s-rich:#2a78d6;--s-haiku:#eb6834;--s-opus:#1baf7a;--good:#006300}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;
--axis:#383835;--ring:rgba(255,255,255,.10);--shared:#52514e;--s-rich:#3987e5;
--s-haiku:#d95926;--s-opus:#199e70;--good:#0ca30c}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;
--ink-2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
--shared:#52514e;--s-rich:#3987e5;--s-haiku:#d95926;--s-opus:#199e70;--good:#0ca30c}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:40px 16px 64px}
h1{font-size:34px;line-height:1.15;margin:0 0 10px;letter-spacing:-.01em}
h2{font-size:22px;margin:44px 0 6px}
h3{font-size:16px;margin:0 0 2px}
p{margin:8px 0;color:var(--ink-2)} p.lead{font-size:18px;color:var(--ink)}
.meta{color:var(--muted);font-size:14px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;
padding:20px 20px 14px;margin:16px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:24px 0}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:14px 16px}
.tile .label{font-size:13px;color:var(--ink-2);margin-bottom:6px}
.tile .row{display:flex;align-items:baseline;gap:8px;margin:2px 0}
.tile .v{font-weight:600;font-size:20px;white-space:nowrap}
.tile .n{font-size:13px;color:var(--ink-2)}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;flex:none}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:14px;color:var(--ink-2);margin:10px 0 0}
.legend span{display:inline-flex;align-items:center;gap:6px}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{fill:var(--ink-2);font:13px system-ui,-apple-system,"Segoe UI",sans-serif}
svg text.value{fill:var(--ink);font-weight:600}
svg .grid{stroke:var(--grid);stroke-width:1} svg .axis{stroke:var(--axis);stroke-width:1}
figcaption{font-size:13px;color:var(--muted);margin-top:8px}
details{margin-top:10px;font-size:14px} summary{cursor:pointer;color:var(--ink-2)}
table{border-collapse:collapse;width:100%;margin-top:8px;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid)}
th{color:var(--ink-2);font-weight:600}
.watermark{position:fixed;inset:0;pointer-events:none;display:flex;align-items:center;
justify-content:center;font-size:64px;font-weight:700;color:rgba(227,73,72,.24);transform:rotate(-18deg);z-index:9}
.banner{background:#fde8e8;color:#7a1414;border-radius:8px;padding:10px 14px;font-weight:600}
ul{color:var(--ink-2);padding-left:20px} li{margin:4px 0}
@media (max-width:560px){h1{font-size:26px}.card{padding:14px}}
"""


def esc(value: Any) -> str:
    return html.escape(str(value))


def fmt_s(ms: float | None) -> str:
    return "–" if ms is None else f"{ms / 1000:.1f} s"


def fmt_usd(v: float | None, digits: int = 3) -> str:
    return "–" if v is None else f"${v:,.{digits}f}"


def fmt_pct(v: float | None) -> str:
    return "–" if v is None else f"{v * 100:.0f}%"


def fmt_n(v: float | None) -> str:
    return "–" if v is None else (f"{v:,.0f}" if v >= 100 else f"{v:,.1f}".rstrip("0").rstrip("."))


def _get(d: dict, *path, default=None):
    for key in path:
        if not isinstance(d, dict) or key not in d:
            return default
        d = d[key]
    return d


def legend(arms: list[str]) -> str:
    items = "".join(
        f'<span><i class="dot" style="background:var({CSS_VAR[a]})"></i>{esc(LONG[a])}</span>'
        for a in arms
    )
    return f'<div class="legend">{items}</div>'


def _bar_path(x0: float, y: float, width: float, height: float, r: float = 4) -> str:
    """A bar grown from x0, square at the baseline, 4px-rounded at its data end."""
    r = min(r, width / 2, height / 2) if width > 0 else 0
    x1 = x0 + width
    return (
        f"M{x0:.1f},{y:.1f}H{x1 - r:.1f}Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f}"
        f"V{y + height - r:.1f}Q{x1:.1f},{y + height:.1f} {x1 - r:.1f},{y + height:.1f}"
        f"H{x0:.1f}Z"
    )


def hbar(
    rows: list[tuple[str, float | None, str]],
    *,
    max_value: float | None = None,
    segments: dict[str, list[tuple[str, float, str]]] | None = None,
) -> str:
    """Horizontal bars, one per method. ``segments`` stacks (label, value, css color) pieces."""
    # Reserve room for the longest value label so no label is clipped (about 7.5px a character).
    longest = max((len(label) for _, _, label in rows), default=4)
    width, left, bar, gap = 720, 150, 22, 16
    right = max(60, int(longest * 7.5) + 20)
    values = [v for _, v, _ in rows if v is not None]
    top = max_value or (max(values) if values else 1) or 1
    plot = width - left - right
    height = len(rows) * (bar + gap) + 8
    out = [f'<svg viewBox="0 0 {width} {height}" role="img">']
    for tick in range(5):
        x = left + plot * tick / 4
        out.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="0" y2="{height - 4}"/>')
    out.append(f'<line class="axis" x1="{left}" x2="{left}" y1="0" y2="{height - 4}"/>')
    for i, (arm, value, label) in enumerate(rows):
        y = 4 + i * (bar + gap)
        out.append(
            f'<text x="{left - 10}" y="{y + bar / 2 + 4:.1f}" text-anchor="end">'
            f"{esc(SHORT[arm])}</text>"
        )
        if value is None:
            out.append(f'<text x="{left + 8}" y="{y + bar / 2 + 4:.1f}">no data</text>')
            continue
        pieces = (segments or {}).get(arm) or [("", value, f"var({CSS_VAR[arm]})")]
        x = float(left)
        for n, (name, part, color) in enumerate(pieces):
            w = max(0.0, plot * part / top)
            last = n == len(pieces) - 1
            path = _bar_path(x, y, w - (0 if last else 2), bar, 4 if last else 0)
            tip = f"{SHORT[arm]}{' · ' + name if name else ''}: {label if last else fmt_s(part)}"
            out.append(f'<path d="{path}" fill="{color}"><title>{esc(tip)}</title></path>')
            x += w
        out.append(
            f'<text class="value" x="{x + 8:.1f}" y="{y + bar / 2 + 4:.1f}">{esc(label)}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def table(headers: list[str], body: list[list[str]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    rows = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in body)
    return f"<details><summary>Table view</summary><table><tr>{head}</tr>{rows}</table></details>"


def figure(title: str, subtitle: str, svg: str, caption: str, tbl: str, arms: list[str]) -> str:
    return (
        f'<figure class="card"><h3>{esc(title)}</h3><p>{esc(subtitle)}</p>{svg}'
        f"{legend(arms)}<figcaption>{esc(caption)}</figcaption>{tbl}</figure>"
    )


def sample_line(scores: dict) -> str:
    s = scores["sample"]
    dates = s["chart_dates"]
    return (
        f"Sample: {s['games_compared']} games ({s['steam_games']} from the Steam most-played "
        f"chart of {dates.get('steam')}, {s['mobile_games']} from the Google Play US "
        f"top-grossing chart of {dates.get('mobile')}), run {scores.get('run_date', '')}."
    )


def key_line(scores: dict) -> str:
    return (
        f"Answer key: Steam players' top-20 user tags on the "
        f"{scores['sample'].get('games_with_steam_answer_key', 0)} games with a Steam listing, "
        "through the draft crosswalk (pending owner approval). A missing Steam tag is not "
        "counted against any method."
    )


def headline(scores: dict) -> dict[str, str]:
    """Guarded, number-driven sentences for the lead and the social post."""
    arms = scores["arms"]
    rec = _get(arms, "rich", "steam_tags", "shared_vocabulary", "recall_pooled")
    diffs = scores.get("recall_difference_vs_rich", {})
    parts = []
    for other in ("legacy-deep", "legacy-standard"):
        d = _get(diffs, other, "shared_vocabulary")
        old = _get(arms, other, "steam_tags", "shared_vocabulary", "recall_pooled")
        if not d or d.get("rich_minus_old_points") is None or rec is None:
            continue
        ci = d.get("ci95_points") or {}
        if ci and ci["low"] <= 0 <= ci["high"]:
            verdict = "no clear difference"
        else:
            verdict = "higher for Jev" if d["rich_minus_old_points"] > 0 else "lower for Jev"
        parts.append(
            f"{fmt_pct(old)} for the {SHORT[other]} setting ({d['rich_minus_old_points']:+.0f} "
            f"points, 95% interval {ci.get('low', 0):+.0f} to {ci.get('high', 0):+.0f}: {verdict})"
        )
    if not parts:
        return {}
    return {
        "recall": (
            f"On attributes both methods can name, Jev found {fmt_pct(rec)} of what Steam "
            f"players tagged, versus {' and '.join(parts)}."
        )
    }


def render_report(scores: dict, *, illustrative: bool = False) -> str:
    arms = [a for a in ARMS if a in scores["arms"]]
    A = scores["arms"]
    sample, key = sample_line(scores), key_line(scores)
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        '<meta name=viewport content="width=device-width,initial-scale=1">',
        "<title>Jev vs Old Tagger</title>",
        f"<style>{CSS}</style></head><body>",
    ]
    if illustrative:
        parts.append('<div class="watermark">Illustrative / UI test data</div>')
    parts.append("<main>")
    if illustrative:
        parts.append(
            '<p class="banner">Illustrative / UI test data. These numbers are fixtures for '
            "checking the layout, not measurements.</p>"
        )
    parts.append("<h1>Jev rich mode versus the original one-call tagger</h1>")
    parts.append(f'<p class="meta">{esc(sample)}</p>')
    parts.append(
        '<p class="lead">The same shared evidence for every game (store text, Wikipedia, '
        "screenshots and the store trailer) was given to three methods: the new pipeline, "
        "where Claude describes the images and Jev judges 189 attributes and the genre one "
        "question at a time, and the original site's single Claude request on its two model "
        "settings.</p>"
    )
    for sentence in headline(scores).values():
        parts.append(f"<p>{esc(sentence)}</p>")

    # ---- stat tiles
    def tile(label: str, getter, fmt) -> str:
        rows = "".join(
            f'<div class="row"><i class="dot" style="background:var({CSS_VAR[a]})"></i>'
            f'<span class="v">{esc(fmt(getter(A[a])))}</span><span class="n">'
            f"{esc(SHORT[a])}</span></div>"
            for a in arms
        )
        return f'<div class="tile"><div class="label">{esc(label)}</div>{rows}</div>'

    parts.append('<div class="tiles">')
    parts.append(
        tile(
            "Player-tagged attributes found",
            lambda x: _get(x, "steam_tags", "all_mapped", "recall_pooled"),
            fmt_pct,
        )
    )
    parts.append(
        tile(
            "Attributes reported per game (median)",
            lambda x: _get(x, "tags_per_game", "positive_in_genome_vocabulary", "median"),
            fmt_n,
        )
    )
    parts.append(
        tile("Time per game (median)", lambda x: _get(x, "latency_ms", "method", "median"), fmt_s)
    )
    parts.append(
        tile("Cost per game (mean)", lambda x: _get(x, "cost_usd", "per_game", "mean"), fmt_usd)
    )
    parts.append("</div>")

    # ---- accuracy
    parts.append("<h2>Accuracy against Steam players' tags</h2>")
    parts.append(f"<p>{esc(key)}</p>")
    for scope, title, sub in (
        (
            "all_mapped",
            "Share of player-tagged attributes each method reported present",
            "All Genome attributes the Steam tags map to. The old method has no words for some "
            "of them, so this shows what each method can tell you.",
        ),
        (
            "shared_vocabulary",
            "The same, limited to attributes both vocabularies can name",
            "The fair head-to-head: only attributes the old tag list can also express.",
        ),
    ):
        rows = [
            (
                a,
                _get(A[a], "steam_tags", scope, "recall_pooled"),
                fmt_pct(_get(A[a], "steam_tags", scope, "recall_pooled")),
            )
            for a in arms
        ]
        tbl = table(
            ["Method", "Recall (pooled)", "Mean per game", "Said absent", "Games", "Attributes"],
            [
                [
                    LONG[a],
                    fmt_pct(_get(A[a], "steam_tags", scope, "recall_pooled")),
                    fmt_pct(_get(A[a], "steam_tags", scope, "recall_mean_per_game")),
                    fmt_pct(_get(A[a], "steam_tags", scope, "contradiction_rate")),
                    str(_get(A[a], "steam_tags", scope, "games", default="–")),
                    str(_get(A[a], "steam_tags", scope, "attributes", default="–")),
                ]
                for a in arms
            ],
        )
        parts.append(figure(title, sub, hbar(rows, max_value=1.0), f"{sample} {key}", tbl, arms))
    rows = [
        (
            a,
            _get(A[a], "steam_tags", "all_mapped", "contradiction_rate"),
            fmt_pct(_get(A[a], "steam_tags", "all_mapped", "contradiction_rate")),
        )
        for a in arms
    ]
    top = max([v for _, v, _ in rows if v is not None] or [0.05]) * 1.25
    parts.append(
        figure(
            "Said “no” to something players tagged",
            "Share of player-tagged attributes a method explicitly marked absent. Lower is "
            "better; not answering is not counted here.",
            hbar(rows, max_value=top or 0.05),
            f"{sample} {key}",
            table(
                ["Method", "Contradiction rate"],
                [[LONG[a], r[2]] for a, r in zip(arms, rows, strict=True)],
            ),
            arms,
        )
    )
    # ---- output volume
    parts.append("<h2>How much each method says</h2>")
    rows = [
        (
            a,
            _get(A[a], "tags_per_game", "positive_in_genome_vocabulary", "median"),
            fmt_n(_get(A[a], "tags_per_game", "positive_in_genome_vocabulary", "median")),
        )
        for a in arms
    ]
    parts.append(
        figure(
            "Attributes reported present per game (median)",
            "Old-method tags are translated into the Genome vocabulary through the draft "
            "crosswalk. Jev also marks each remaining attribute absent, unknown or conflicting.",
            hbar(rows),
            sample,
            table(
                ["Method", "Median (Genome)", "Median (own words)", "Mean (Genome)"],
                [
                    [
                        LONG[a],
                        fmt_n(
                            _get(A[a], "tags_per_game", "positive_in_genome_vocabulary", "median")
                        ),
                        fmt_n(_get(A[a], "tags_per_game", "positive_raw", "median")),
                        fmt_n(_get(A[a], "tags_per_game", "positive_in_genome_vocabulary", "mean")),
                    ]
                    for a in arms
                ],
            ),
            arms,
        )
    )
    # ---- speed
    parts.append("<h2>Speed</h2>")
    segments, rows = {}, []
    for a in arms:
        gather = _get(A[a], "latency_ms", "with_evidence_gathering", "median")
        method = _get(A[a], "latency_ms", "method", "median")
        if gather is None or method is None:
            rows.append((a, None, ""))
            continue
        shared = max(0.0, gather - method)
        segments[a] = [
            ("shared evidence gathering", shared, "var(--shared)"),
            ("method", method, f"var({CSS_VAR[a]})"),
        ]
        rows.append((a, gather, f"{fmt_s(method)} (+{fmt_s(shared)})"))
    stage_rows = [
        [LONG[a], stage, fmt_s(_get(d, "median")), fmt_s(_get(d, "p95"))]
        for a in arms
        for stage, d in (_get(A[a], "latency_ms", "stages", default={}) or {}).items()
    ]
    parts.append(
        figure(
            "Median time per game",
            "Colored: the method itself (first number). Gray: fetching store pages, Wikipedia "
            "and media (in brackets), shared and identical for every method.",
            hbar(rows, segments=segments),
            f"{sample} Wall-clock time with three games in parallel; retries included.",
            table(["Method", "Stage", "Median", "95th percentile"], stage_rows),
            arms,
        )
    )
    # ---- tokens and cost
    parts.append("<h2>Tokens and cost</h2>")
    rows = [
        (
            a,
            _get(A[a], "cost_usd", "per_game", "mean"),
            fmt_usd(_get(A[a], "cost_usd", "per_game", "mean")),
        )
        for a in arms
    ]
    token_rows = [
        [
            LONG[a],
            fmt_n(_get(A[a], "tokens", "anthropic", "input_tokens", "median")),
            fmt_n(_get(A[a], "tokens", "anthropic", "output_tokens", "median")),
            fmt_n(_get(A[a], "tokens", "typesafe", "input_tokens", "median")),
            fmt_usd(_get(A[a], "cost_usd", "total"), 2),
        ]
        for a in arms
    ]
    parts.append(
        figure(
            "Cost per game (mean)",
            "Computed from list prices and reported token counts: Claude Haiku 4.5 $1/$5, "
            "Opus 4.8 $5/$25, Sonnet 5 $2/$10 per million input/output tokens; Jev $0.042 per "
            "million input tokens, output free.",
            hbar(rows),
            sample,
            table(
                [
                    "Method",
                    "Claude input (median)",
                    "Claude output (median)",
                    "Jev input (median)",
                    "Total spent",
                ],
                token_rows,
            ),
            arms,
        )
    )
    # ---- genre
    parts.append("<h2>Primary genre</h2>")
    genre_rows = [
        [
            LONG[a],
            str(_get(A[a], "genre", "with_primary_genre", default="–")),
            str(_get(A[a], "genre", "forced_fallback", default="–")),
            fmt_pct(_get(A[a], "genre_vs_steam_tags", "consistent_genre")),
            fmt_pct(_get(A[a], "genre_vs_steam_tags", "consistent_family")),
        ]
        for a in arms
    ]
    parts.append(
        '<div class="card"><p>The old method must always name a genre and silently substitutes '
        "one when its answer is not on its list; Jev may decline when the evidence does not "
        "support one. Agreement with Steam tags is a weak signal, because Steam tags list every "
        "genre a game touches, not its main one.</p>"
        + table(
            [
                "Method",
                "Games with a primary genre",
                "Forced fallback",
                "Consistent with Steam tags",
                "Same family as a Steam tag",
            ],
            genre_rows,
        ).replace("<details>", "<details open>")
        + "</div>"
    )
    if scores.get("owner_review"):
        review_rows = [
            [LONG.get(a, a), kind, str(v["yes"]), str(v["no"]), fmt_pct(v["precision"])]
            for a, kinds in scores["owner_review"].items()
            for kind, v in kinds.items()
        ]
        parts.append("<h2>Owner review (blinded)</h2>")
        parts.append(
            '<div class="card"><p>The owner judged a random sample of proposed attributes and '
            "genres without knowing which method proposed them.</p>"
            + table(["Method", "Kind", "Correct", "Wrong", "Precision"], review_rows).replace(
                "<details>", "<details open>"
            )
            + "</div>"
        )
    # ---- method notes
    parts.append("<h2>How to read this</h2><ul>")
    for note in (
        "Same inputs: every method read the same dossier per game, gathered once from exact "
        "store IDs. The old method is also told the game's name, as the original site was, so it "
        "can draw on what Claude already knows; Jev is shown only the evidence.",
        "The old method is a faithful adaptation of the original site's prompt and rules "
        "(gametagger-web commit 4b710fd), not the live site: its evidence came from the shared "
        "dossier, there is no Xbox store section, and trailer frames stayed off as in the "
        "original default.",
        "Recall uses Steam players' tags, which exist only for games sold on Steam; most mobile "
        "games are therefore judged by the owner review instead.",
        "The crosswalks between vocabularies are drafts pending owner approval.",
        "Costs are computed from list prices, not invoices. Times include provider retries.",
    ):
        parts.append(f"<li>{esc(note)}</li>")
    parts.append("</ul></main></body></html>")
    return "".join(parts)


# --------------------------------------------------------------------------- social card


def render_social_card(scores: dict, *, illustrative: bool = False) -> str:
    arms = [a for a in ARMS if a in scores["arms"]]
    A = scores["arms"]
    kpis = [
        (
            "Player-tagged attributes found",
            lambda x: _get(x, "steam_tags", "all_mapped", "recall_pooled"),
            fmt_pct,
            1.0,
        ),
        (
            "Attributes per game",
            lambda x: _get(x, "tags_per_game", "positive_in_genome_vocabulary", "median"),
            fmt_n,
            None,
        ),
        ("Seconds per game", lambda x: _get(x, "latency_ms", "method", "median"), fmt_s, None),
        ("Cost per game", lambda x: _get(x, "cost_usd", "per_game", "mean"), fmt_usd, None),
    ]
    blocks = []
    for label, getter, fmt, fixed_max in kpis:
        values = [getter(A[a]) for a in arms]
        top = fixed_max or max([v for v in values if v is not None] or [1]) or 1
        bars = "".join(
            f'<div class="b"><span class="k">{esc(SHORT[a])}</span><span class="track">'
            f'<i style="width:{0 if not v else max(1.5, 100 * v / top):.1f}%;'
            f'background:var({CSS_VAR[a]})"></i></span>'
            f'<span class="val">{esc(fmt(v))}</span></div>'
            for a, v in zip(arms, values, strict=True)
        )
        blocks.append(f'<div class="kpi"><div class="kl">{esc(label)}</div>{bars}</div>')
    s = scores["sample"]
    footer = (
        f"{s['games_compared']} games: Steam most-played ({s['chart_dates'].get('steam')}) + "
        f"Google Play US top-grossing ({s['chart_dates'].get('mobile')}). Accuracy = share of "
        f"Steam players' top-20 tags found, {s.get('games_with_steam_answer_key', 0)} games on "
        "Steam, draft crosswalk. Costs from list prices."
    )
    mark = '<div class="wm">Illustrative / UI test data</div>' if illustrative else ""
    head = "<!doctype html><html><head><meta charset=utf-8><title>Jev Benchmark Card</title>"
    return f"""{head}<style>
{CSS}
body{{margin:0;width:1200px;height:675px;overflow:hidden;background:var(--surface)}}
.c{{width:1200px;height:675px;padding:48px 56px 36px;display:flex;flex-direction:column}}
.t{{font-size:44px;font-weight:700;line-height:1.1;letter-spacing:-.01em;color:var(--ink)}}
.st{{font-size:22px;color:var(--ink-2);margin-top:10px}}
.g{{display:grid;grid-template-columns:1fr 1fr;gap:26px 48px;margin-top:34px;flex:1}}
.kl{{font-size:20px;font-weight:600;margin-bottom:10px;color:var(--ink)}}
.b{{display:grid;grid-template-columns:150px 1fr 96px;align-items:center;gap:12px;margin:7px 0}}
.k{{font-size:17px;color:var(--ink-2)}} .val{{font-size:18px;font-weight:600;text-align:right}}
.track{{height:20px;display:block}} .track i{{display:block;height:20px;border-radius:0 4px 4px 0}}
.f{{font-size:15px;color:var(--muted);line-height:1.4}}
.wm{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:72px;
font-weight:800;color:rgba(227,73,72,.22);transform:rotate(-14deg)}}
</style></head><body><div class="c">{mark}
<div class="t">One LLM call vs. Jev: tagging {s["games_compared"]} top games</div>
<div class="st">Same evidence per game. Old tagger (Claude Haiku or Opus, one prompt) vs.
Claude vision + Jev judging 189 attributes one by one.</div>
<div class="g">{"".join(blocks)}</div><div class="f">{esc(footer)}</div></div></body></html>"""


def social_post(scores: dict) -> str:
    A, s = scores["arms"], scores["sample"]
    rich = A.get("rich", {})
    parts = [
        f"We re-tagged {s['games_compared']} of today's top games (Steam most-played + Google "
        "Play top-grossing) two ways on identical evidence: our original one-prompt tagger "
        "(Claude Haiku / Opus) and a new pipeline where Claude only describes what it sees and "
        "Jev judges each attribute.",
    ]
    for sentence in headline(scores).values():
        parts.append(sentence)
    rec = _get(rich, "tags_per_game", "positive_in_genome_vocabulary", "median")
    if rec is not None:
        parts.append(
            f"Jev reported a median of {fmt_n(rec)} attributes per game at "
            f"{fmt_usd(_get(rich, 'cost_usd', 'per_game', 'mean'))} and "
            f"{fmt_s(_get(rich, 'latency_ms', 'method', 'median'))} per game."
        )
    parts.append(
        f"Answer key: Steam players' top tags ({s.get('games_with_steam_answer_key', 0)} games); "
        f"charts dated {s['chart_dates'].get('steam')} / {s['chart_dates'].get('mobile')}; costs "
        "from list prices."
    )
    return "\n\n".join(parts) + "\n"


def render_png(html_path: Path, png_path: Path) -> bool:
    """Screenshot the card with a headless Chromium when one is installed."""
    candidates = [
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell",
        "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    ]
    binary = next((c for c in candidates if c and Path(c).exists()), None)
    if binary is None:
        return False
    result = subprocess.run(
        [
            binary,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--window-size=1200,675",
            f"--screenshot={png_path.resolve()}",
            html_path.resolve().as_uri(),
        ],
        capture_output=True,
        timeout=120,
    )
    return result.returncode == 0 and png_path.exists()
