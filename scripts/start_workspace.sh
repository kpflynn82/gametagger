#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/uvicorn || ! -f frontend/dist/index.html ]]; then
  echo "First run: uv sync --frozen --extra dev && npm --prefix frontend ci && npm --prefix frontend run build"
  exit 1
fi
# Explicit localhost-only mode. No .env/key loading, network fetching, or inference.
export GAMETAGGER_BUILD_SHA="$(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain)" ]]; then
  export GAMETAGGER_BUILD_SHA="${GAMETAGGER_BUILD_SHA}+working-tree"
fi
export GAMETAGGER_LOCAL_DEV=1
export GAMETAGGER_LOCAL_ROLE="${GAMETAGGER_LOCAL_ROLE:-viewer}"
exec .venv/bin/uvicorn gametagger.workspace.app:app --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
