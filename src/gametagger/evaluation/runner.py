"""Replay hash-bound saved results without making model calls."""

import argparse
import json
from pathlib import Path

from gametagger.evaluation.benchmark import replay_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = replay_manifest(args.manifest, args.output)
    print(json.dumps(result["availability"], indent=2))


if __name__ == "__main__":
    main()
