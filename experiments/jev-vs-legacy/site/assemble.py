"""Assemble the published benchmark pages from committed results.

    uv run python experiments/jev-vs-legacy/site/prep.py <out>/data.json
    uv run python experiments/jev-vs-legacy/site/assemble.py <out> [results-url] [requests-url]

Writes ``<out>/results/index.html`` (with its LinkedIn images and social card beside it) and
``<out>/requests/index.html``. Publish each folder as its own page; the requests page needs the
``db`` and ``user`` capabilities described in docs/JEV_VS_LEGACY_BENCHMARK.md.
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent


def main() -> None:
    out = Path(sys.argv[1])
    results_url = sys.argv[2] if len(sys.argv) > 2 else "#"
    requests_url = sys.argv[3] if len(sys.argv) > 3 else "#"
    post = (EXP / "linkedin/post.txt").read_text().strip().replace("[link]", results_url)
    page = (HERE / "results-template.html").read_text()
    page = page.replace("/*DATA*/", (out / "data.json").read_text())
    page = page.replace("/*POST*/", json.dumps(post)).replace("/*REQUEST_URL*/", requests_url)
    results = out / "results"
    (results / "linkedin").mkdir(parents=True, exist_ok=True)
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
