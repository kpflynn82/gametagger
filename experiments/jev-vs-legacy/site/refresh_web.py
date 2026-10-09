"""Rebuild ``web/index.html`` from ``dashboard-template.html``, keeping the published data.

    uv run python experiments/jev-vs-legacy/site/refresh_web.py [--check]

Use it after editing the template (layout, text, pages) when the data has not changed; a new
snapshot goes through ``prep.py`` and ``assemble.py`` instead. ``--check`` only reports whether
``web/index.html`` already matches the template.

The site is one page with six views (home, dashboard, games, tags, play-testing,
how-it-works). ``web/vercel.json`` serves the same file at each view's path.
"""

import re
import sys
from pathlib import Path

from assemble import DASHBOARD_DESCRIPTION, standalone

HERE = Path(__file__).resolve().parent
WEB = HERE.parents[2] / "web"
REQUEST_URL = "https://claude.ai/artifact/3MLmYUfDTkFgC9RFfkNiPU"


def main() -> None:
    published = (WEB / "index.html").read_text()
    data = re.search(r"const DATA = (\{.*?\});\n", published, re.S).group(1)
    home = (HERE / "dashboard-template.html").read_text()
    home = home.replace("/*DATA*/", data).replace("/*REQUEST_URL*/", REQUEST_URL)
    home = home.replace("/*BENCH_URL*/", "/benchmark")
    title = "GameTagger: what's inside today's top mobile games"
    page = standalone(home, title, DASHBOARD_DESCRIPTION, "social-card.png")
    if "--check" in sys.argv:
        same = page == published
        print("web/index.html matches the template" if same else "web/index.html differs")
        sys.exit(0 if same else 1)
    (WEB / "index.html").write_text(page)
    print(f"wrote {WEB / 'index.html'}")


if __name__ == "__main__":
    main()
