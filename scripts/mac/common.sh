# Shared by the Mac scripts: find the repo, load keys, check tools. Sourced, not run.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

# Keys live outside the repo so they can never be committed.
KEYS="${GAMETAGGER_KEYS:-$HOME/Claude Workspace/gametagger/gametagger.env}"
if [[ ! -f "$KEYS" ]]; then
  echo "Keys file not found: $KEYS"
  echo "Create it (see docs/MAC_TOOLS.md) or set GAMETAGGER_KEYS to its path."
  exit 1
fi
set -a
# shellcheck disable=SC1090
. "$KEYS"
set +a

# Android Studio installs adb here when it is not on PATH.
if ! command -v adb >/dev/null && [[ -x "$HOME/Library/Android/sdk/platform-tools/adb" ]]; then
  export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
fi

need() {
  if ! command -v "$1" >/dev/null; then
    echo "Missing: $1. Run scripts/mac/setup.sh first."
    exit 1
  fi
}

# Total spend allowed in this copy's ledger (benchmark-runs/ledger.jsonl), across all runs.
BUDGET="${GAMETAGGER_BUDGET_USD:-2.00}"
