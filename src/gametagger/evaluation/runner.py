from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="GameTagger v2 evaluation harness")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--pipelines",
        nargs="+",
        default=["legacy_v1", "observer_jev"],
        help="Pipelines to compare once adapters are configured.",
    )
    args = parser.parse_args()

    cases = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(cases)} benchmark cases")
    print(f"Requested pipelines: {', '.join(args.pipelines)}")
    print(
        "Scaffold only: pipeline execution is added in PR 3 after observer + legacy adapters exist."
    )


if __name__ == "__main__":
    main()
