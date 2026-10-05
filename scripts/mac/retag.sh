#!/usr/bin/env bash
# Retag the Google Play top 50 (the site's list) with vocabulary v2, from store pages only.
# Screenshots and trailers are described on your Claude plan through Claude Code (no API
# charge); Jev runs on TypeSafe under a $1.00 cap for this run.
#
#   scripts/mac/retag.sh              # check the plan, gather store pages, tag, summarize
#   scripts/mac/retag.sh --limit 2    # try the first two games only
#
# Safe to run again: finished games are kept and skipped. Keep the Mac awake while it runs.
source "$(dirname "$0")/common.sh"

WORKDIR="benchmark-runs/mobile-retag-v2"
JEV_CAP="${GAMETAGGER_JEV_CAP_USD:-1.00}"
mkdir -p "$WORKDIR"

NO_VIDEO=()
if ! command -v ffmpeg >/dev/null; then
  echo "Note: ffmpeg is not installed, so store trailers are skipped (screenshots and text only)."
  echo "      scripts/mac/setup.sh installs it."
  NO_VIDEO=(--no-video)
fi
AWAKE=()
if command -v caffeinate >/dev/null; then
  AWAKE=(caffeinate -i)
fi

echo "1/4 Checking that Claude Code is logged in to your Claude plan..."
uv run gametagger-compare --workdir "$WORKDIR" check-plan

echo
echo "2/4 Gathering store pages, screenshots and trailers (free)..."
uv run gametagger-compare --workdir "$WORKDIR" dossiers --list mobile \
  ${NO_VIDEO[@]+"${NO_VIDEO[@]}"} "$@"

echo
echo "3/4 Tagging: images described on your plan, Jev capped at \$$JEV_CAP..."
${AWAKE[@]+"${AWAKE[@]}"} uv run gametagger-compare --workdir "$WORKDIR" run --live \
  --use-max-plan --vocabulary v2 --arms rich --list mobile --budget-usd "$JEV_CAP" \
  --retry-failed "$@" | tee "$WORKDIR/run-summary.json" \
  || echo "The run stopped early (see above). Finished games are kept; run this again to go on."

echo
echo "4/4 Summarizing..."
uv run python experiments/mobile-retag-v2/summarize.py --workdir "$WORKDIR"
echo
echo "Done. Results: $WORKDIR (kept on this Mac) and experiments/mobile-retag-v2/summary.json."
