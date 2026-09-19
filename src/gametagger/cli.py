"""Single-case development CLI. Credentials are read from the process environment only."""

import argparse
import json
import os
from pathlib import Path

from gametagger.decisions.jev import JevDecisionEngine, TypeSafeGateway
from gametagger.decisions.mock import MockJevGateway
from gametagger.domain import EvidenceItem, EvidenceType
from gametagger.observers.anthropic import AnthropicObserver
from gametagger.observers.mock import MockObserver
from gametagger.pipeline import AnalysisPipeline
from gametagger.taxonomy import load_taxonomy


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze one image with GameTagger")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--game-id", default="local-case")
    parser.add_argument("--project-id", help="Associate uploads with this opaque project")
    parser.add_argument("--game-title")
    parser.add_argument("--metadata", type=Path, help="JSON object of textual source metadata")
    parser.add_argument("--source", default="local-upload")
    parser.add_argument("--blind-media", action="store_true")
    parser.add_argument(
        "--offline", action="store_true", help="Mock observer and mock Jev; no API calls"
    )
    parser.add_argument("--observer-model", default=os.environ.get("OBSERVER_MODEL"))
    parser.add_argument("--jev-model", default=os.environ.get("TYPESAFE_MODEL", "jev-latest"))
    args = parser.parse_args()
    if not args.offline:
        for key in ("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY"):
            if not os.environ.get(key):
                parser.error(f"Set {key} in the environment, or use --offline")
        if not args.observer_model:
            parser.error(
                "Supply --observer-model or set OBSERVER_MODEL to a vision-capable Claude model"
            )
    metadata = json.loads(args.metadata.read_text()) if args.metadata else {}
    if not isinstance(metadata, dict) or any(not isinstance(v, str) for v in metadata.values()):
        parser.error("Metadata must be a JSON object with string values")
    taxonomy = load_taxonomy()
    observer = (
        MockObserver()
        if args.offline
        else AnthropicObserver(
            taxonomy,
            model=args.observer_model,
            workspace_id=os.environ.get("ANTHROPIC_WORKSPACE_ID"),
        )
    )
    gateway = MockJevGateway() if args.offline else TypeSafeGateway(model=args.jev_model)
    result = AnalysisPipeline(observer, JevDecisionEngine(taxonomy, gateway)).analyze(
        game_id=args.game_id,
        game_title=args.game_title,
        blind_media=args.blind_media,
        offline=args.offline,
        project_id=args.project_id or args.game_id,
        evidence=[
            EvidenceItem(
                id="image-1",
                type=EvidenceType.GAMEPLAY_IMAGE,
                source=args.source,
                uri=str(args.image),
                metadata=metadata,
            )
        ],
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
