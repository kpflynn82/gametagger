"""gametagger-clone: scaffold a web prototype + Codex art brief from a clone spec.

    gametagger-clone scaffold --spec spec.json --out builds/
    gametagger-clone scaffold --title "Wyrmwall" --family role_playing --theme dragons \\
        --keep "social tournament system" --add gacha --out builds/

``--spec`` is JSON with the CloneSpec fields (as the radar's approve step writes). The flag form is
a quick manual path. Nothing here calls a model or generates art; it writes the skeleton and the
handoff files for Codex to fill.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gametagger.clone.scaffold import scaffold_clone
from gametagger.clone.spec import CloneSpec


def _spec_from_args(args) -> CloneSpec:
    if args.spec:
        data = json.loads(Path(args.spec).read_text())
        return CloneSpec(
            title=data["title"],
            family=data.get("family", "unknown"),
            theme=data.get("theme", "dragons"),
            core_loop=data.get("core_loop", ""),
            keep=data.get("keep", []),
            add=data.get("add", []),
            directions=data.get("directions", []),
            screens=data.get("screens", ["Home", "Play", "Shop", "Progress"]),
            economy=data.get("economy", {}),
            source_note=data.get("source_note", ""),
        )
    if not args.title:
        raise SystemExit("scaffold needs --spec <file> or --title ...")
    return CloneSpec.from_proposal(
        title=args.title,
        family=args.family or "unknown",
        theme=args.theme or "dragons",
        keep=args.keep or [],
        add=args.add or [],
        directions=args.direction or [],
        source_note=args.source_note or "",
    )


def cmd_scaffold(args) -> int:
    spec = _spec_from_args(args)
    written = scaffold_clone(spec, Path(args.out))
    print(f"Scaffolded {spec.title} ({spec.engine}, {spec.theme}) in {Path(args.out) / spec.slug}")
    for label, path in written.items():
        print(f"  {label:10s} {path}")
    print("\nHand the folder to Codex for art (reads ART_BRIEF.md + assets/MANIFEST.json).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gametagger-clone", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scaffold", help="write the web skeleton + Codex art brief")
    s.add_argument("--spec", help="CloneSpec JSON")
    s.add_argument("--title")
    s.add_argument("--family", help="genre family, e.g. role_playing / puzzle / action")
    s.add_argument("--theme", help="the fresh theme to reskin to")
    s.add_argument("--keep", action="append", help="a system to clone faithfully (repeatable)")
    s.add_argument("--add", action="append", help="a mechanic to add (repeatable)")
    s.add_argument("--direction", action="append", help="a freeform direction (repeatable)")
    s.add_argument("--source-note", help="one line on the teardown this came from")
    s.add_argument("--out", default="builds", help="output directory (default: builds/)")
    s.set_defaults(func=cmd_scaffold)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
