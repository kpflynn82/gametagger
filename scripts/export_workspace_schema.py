"""Generate browser contracts without starting the server or opening a database."""

import json
from pathlib import Path

from gametagger.workspace.app import create_app

root = Path(__file__).resolve().parents[1]
(root / "frontend/openapi.json").write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
