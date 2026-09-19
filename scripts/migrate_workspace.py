"""Initialize/migrate a private workspace only; never connects to any legacy database."""

import argparse
from pathlib import Path

from gametagger.workspace.store import Store

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--data-dir", type=Path, required=True)
args = parser.parse_args()
store = Store(args.data_dir)
with store.connect() as db:
    print("Workspace schema", db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0])
