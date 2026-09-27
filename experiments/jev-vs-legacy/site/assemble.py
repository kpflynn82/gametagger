"""Assemble the published benchmark pages from committed results.

    uv run python experiments/jev-vs-legacy/site/prep.py <out>/data.json
    uv run python experiments/jev-vs-legacy/site/assemble.py <out> [results-url] [requests-url] \
        [benchmark-url]

Writes ``<out>/dashboard/index.html`` (the home page: what is in the top 100, the game library
and tag dictionary, a short method and comparison), ``<out>/results/index.html`` (the full
benchmark write-up, with its LinkedIn images and social card beside it) and
``<out>/requests/index.html``. Publish each folder as its own page; the requests page needs the
``db`` and ``user`` capabilities described in docs/JEV_VS_LEGACY_BENCHMARK.md.

With ``--standalone`` (after the positional arguments) the results page is wrapped in a full
HTML document for ordinary static hosting such as Vercel; Artifact publishing adds that wrapper
itself. ``--site-url=https://...`` makes the social card link absolute, which LinkedIn needs.

The page carries no store URLs: the Artifact publisher's link validation rejected a version that
embedded 100 store links, so game profiles link only within the page.
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


DASHBOARD_DESCRIPTION = (
    "What is inside the top 100 Steam and Google Play games: genres, the most common tags, PC "
    "versus mobile, what the biggest hits share, and every game's tags with their evidence."
)
DESCRIPTION = (
    "Today's top 100 Steam and Google Play games tagged two ways on identical evidence: the "
    "original one-prompt tagger and the Jev pipeline. Accuracy, cost, time, a game library and "
    "a dictionary of every tag."
)


def standalone(page: str, title: str, description: str, image: str = "social-card.png") -> str:
    """Wrap the page body in a complete document with the resets the Artifact host supplies.

    Also links the site's icons (favicon.ico, favicon.svg, apple-touch-icon.png in ``web/``) and
    the social card. Pass an absolute ``image`` URL (``--site-url``) for LinkedIn previews.
    """
    head, marker, body = page.partition('<div class="wrap">')
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="description" content="{description}">\n'
        f'<meta property="og:title" content="{title}">\n'
        f'<meta property="og:description" content="{description}">\n'
        '<meta property="og:type" content="website">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta property="og:image" content="{image}">\n'
        f'<meta name="twitter:image" content="{image}">\n'
        '<link rel="icon" href="/favicon.ico" sizes="any">\n'
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n'
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n'
        "<style>[hidden]{display:none!important}img{max-width:100%}</style>\n"
        f"{head}</head>\n<body>\n{marker}{body}\n</body>\n</html>\n"
    )


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    site = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--site-url=")), "")
    image = f"{site.rstrip('/')}/social-card.png" if site else "social-card.png"
    out = Path(args[0])
    results_url = args[1] if len(args) > 1 else "#"
    requests_url = args[2] if len(args) > 2 else "#"
    benchmark_url = args[3] if len(args) > 3 else results_url
    post = (EXP / "linkedin/post.txt").read_text().strip().replace("[link]", results_url)
    page = (HERE / "results-template.html").read_text()
    page = page.replace("/*DATA*/", (out / "data.json").read_text())
    page = page.replace("/*POST*/", json.dumps(post)).replace("/*REQUEST_URL*/", requests_url)
    results = out / "results"
    (results / "linkedin").mkdir(parents=True, exist_ok=True)
    if "--standalone" in sys.argv:
        page = standalone(
            page, "Jev versus one big prompt: tagging 100 top games", DESCRIPTION, image
        )
    (results / "index.html").write_text(page)
    for png in sorted((EXP / "linkedin").glob("*.png")):
        shutil.copy(png, results / "linkedin" / png.name)
    shutil.copy(EXP / "report/social-card.png", results / "social-card.png")

    # The dashboard home page. Jev's comparison cost is the cheaper-describing test's figure,
    # labelled as such on the page.
    data = json.loads((out / "data.json").read_text())
    test = json.loads((EXP / "cost-test/summary.json").read_text())
    data["cheap"] = {
        "games": test["games"],
        "cost": test["arms"]["rich-haiku"]["total_cost_per_game"],
    }
    home = (HERE / "dashboard-template.html").read_text()
    home = home.replace("/*DATA*/", json.dumps(data, separators=(",", ":")))
    home = home.replace("/*REQUEST_URL*/", requests_url).replace("/*BENCH_URL*/", benchmark_url)
    if "--standalone" in sys.argv:
        title = "GameTagger: what's inside the top 100 games"
        home = standalone(home, title, DASHBOARD_DESCRIPTION, image)
    (out / "dashboard").mkdir(parents=True, exist_ok=True)
    (out / "dashboard" / "index.html").write_text(home)
    # The home page plays the trailer (experiments/trailer) from files beside it.
    web = EXP.parents[1] / "web"
    for name in ("trailer.mp4", "trailer-poster.jpg"):
        if (web / name).exists():
            shutil.copy(web / name, out / "dashboard" / name)

    cohort = json.loads((EXP / "cohort.json").read_text())
    titles = json.dumps(sorted(g["title"] for g in cohort["games"]))
    board = (HERE / "requests-template.html").read_text()
    board = board.replace("/*TITLES*/", titles).replace("/*RESULTS_URL*/", results_url)
    (out / "requests").mkdir(parents=True, exist_ok=True)
    (out / "requests" / "index.html").write_text(board)
    print(f"wrote {out / 'dashboard'}, {results} and {out / 'requests'}")


if __name__ == "__main__":
    main()
