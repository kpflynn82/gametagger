#!/usr/bin/env bash
# Tag today's Google Play top 100 grossing games plus about 30 rising games (vocabulary v2,
# store pages only), for the mobile-first site. Screenshots and trailers are described on your
# Claude plan through Claude Code (no API charge); Jev runs on TypeSafe under a $1.00 cap in its
# own ledger (benchmark-runs/mobile-top100/ledger.jsonl).
#
# Games already tagged on October 5 or 8 (experiments/mobile-retag-v2/ and
# experiments/mobile-top100/new-run/ per-game.jsonl) are not tagged again; the site uses those
# results. Safe to run again: finished games are kept and skipped, and the chart is only read
# once. cohort.json can also come from the Play Store app (experiments/mobile-top100/play_cohort.py).
source "$(dirname "$0")/common.sh"

EXPERIMENT="experiments/mobile-top100"
WORKDIR="benchmark-runs/mobile-top100"
JEV_CAP="${GAMETAGGER_JEV_CAP_USD:-1.00}"
MODEL="${OBSERVER_MODEL:-claude-sonnet-5}"
mkdir -p "$WORKDIR" "$EXPERIMENT"
CLI=(uv run gametagger-compare --experiment "$EXPERIMENT" --workdir "$WORKDIR")

NO_VIDEO=()
if ! command -v ffmpeg >/dev/null; then
  echo "Note: ffmpeg is not installed, so store trailers are skipped (screenshots and text only)."
  NO_VIDEO=(--no-video)
fi
AWAKE=()
if command -v caffeinate >/dev/null; then
  AWAKE=(caffeinate -i)
fi

echo "1/5 Checking that Claude Code is logged in to your Claude plan..."
"${CLI[@]}" check-plan --model "$MODEL"

echo
if [[ -f "$EXPERIMENT/cohort.json" ]]; then
  echo "2/5 Using the chart already read: $EXPERIMENT/cohort.json"
else
  echo "2/5 Reading today's Google Play charts (free)..."
  "${CLI[@]}" mobile-cohort --grossing 100 --rising 30
fi

NEW_IDS="$(uv run python - "$EXPERIMENT/cohort.json" <<'PY'
import json, sys
cohort = json.load(open(sys.argv[1]))
done = {json.loads(line)["game_id"]
        for path in ("experiments/mobile-retag-v2/per-game.jsonl",
                     "experiments/mobile-top100/new-run/per-game.jsonl")
        for line in open(path) if line.strip()}
print(",".join(g["game_id"] for g in cohort["games"] if g["game_id"] not in done))
PY
)"
COUNT=$(echo "$NEW_IDS" | tr ',' '\n' | grep -c . || true)
echo "   $COUNT games to tag (the rest were tagged on October 5 or 8)."
if [[ "$COUNT" -eq 0 ]]; then
  echo "Nothing new to tag."
else
  echo
  echo "3/5 Gathering store pages and screenshots (free)..."
  "${CLI[@]}" dossiers --games "$NEW_IDS" ${NO_VIDEO[@]+"${NO_VIDEO[@]}"}

  echo
  echo "4/5 Tagging: images described on your plan, Jev capped at \$$JEV_CAP..."
  ${AWAKE[@]+"${AWAKE[@]}"} "${CLI[@]}" run --live --use-max-plan --vocabulary v2 --arms rich \
    --games "$NEW_IDS" --budget-usd "$JEV_CAP" --observer-model "$MODEL" --retry-failed \
    | tee "$WORKDIR/run-summary.json" \
    || echo "The run stopped early (see above). Finished games are kept; open it again to go on."
fi

echo
echo "5/5 Summarizing (tag states and counts only)..."
uv run python experiments/mobile-retag-v2/summarize.py --workdir "$WORKDIR" \
  --out "$EXPERIMENT/new-run"
echo
echo "Done. Results: $EXPERIMENT (cohort and summary) and $WORKDIR (kept on this Mac)."
