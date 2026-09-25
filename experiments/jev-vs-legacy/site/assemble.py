"""Assemble the published benchmark pages from committed results.

    uv run python experiments/jev-vs-legacy/site/prep.py <out>/data.json
    uv run python experiments/jev-vs-legacy/site/assemble.py <out> [results-url] [requests-url]

Writes ``<out>/results/index.html`` (with its LinkedIn images and social card beside it) and
``<out>/requests/index.html``. Publish each folder as its own page; the requests page needs the
``db`` and ``user`` capabilities described in docs/JEV_VS_LEGACY_BENCHMARK.md.

With ``--standalone`` (after the positional arguments) the results page is wrapped in a full
HTML document for ordinary static hosting such as Vercel; Artifact publishing adds that wrapper
itself.

The page carries no store URLs: the Artifact publisher's link validation rejected a version that
embedded 100 store links, so game profiles link only within the page.
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


DESCRIPTION = (
    "Today's top 100 Steam and Google Play games tagged two ways on identical evidence: the "
    "original one-prompt tagger and the Jev pipeline. Accuracy, cost, time, a game library and "
    "a dictionary of every tag."
)


def standalone(page: str) -> str:
    """Wrap the page body in a complete document with the resets the Artifact host supplies."""
    head, marker, body = page.partition('<div class="wrap">')
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="description" content="{DESCRIPTION}">\n'
        '<meta property="og:title" content="Jev versus one big prompt: tagging 100 top games">\n'
        f'<meta property="og:description" content="{DESCRIPTION}">\n'
        '<meta property="og:type" content="website">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        "<style>[hidden]{display:none!important}img{max-width:100%}</style>\n"
        f"{head}</head>\n<body>\n{marker}{body}\n</body>\n</html>\n"
    )


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0])
    results_url = args[1] if len(args) > 1 else "#"
    requests_url = args[2] if len(args) > 2 else "#"
    post = (EXP / "linkedin/post.txt").read_text().strip().replace("[link]", results_url)
    page = (HERE / "results-template.html").read_text()
    page = page.replace("/*DATA*/", (out / "data.json").read_text())
    page = page.replace("/*POST*/", json.dumps(post)).replace("/*REQUEST_URL*/", requests_url)
    results = out / "results"
    (results / "linkedin").mkdir(parents=True, exist_ok=True)
    if "--standalone" in sys.argv:
        page = standalone(page)
    (results / "index.html").write_text(page)
    for png in sorted((EXP / "linkedin").glob("*.png")):
        shutil.copy(png, results / "linkedin" / png.name)
    shutil.copy(EXP / "report/social-card.png", results / "social-card.png")

    cohort = json.loads((EXP / "cohort.json").read_text())
    titles = json.dumps(sorted(g["title"] for g in cohort["games"]))
    board = (HERE / "requests-template.html").read_text()
    board = board.replace("/*TITLES*/", titles).replace("/*RESULTS_URL*/", results_url)
    (out / "requests").mkdir(parents=True, exist_ok=True)
    (out / "requests" / "index.html").write_text(board)
    print(f"wrote {results / 'index.html'} and {out / 'requests' / 'index.html'}")


if __name__ == "__main__":
    main()
