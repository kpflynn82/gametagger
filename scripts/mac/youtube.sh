#!/usr/bin/env bash
# Tag a game from its store page plus YouTube gameplay videos, sampled screen by screen.
#
#   scripts/mac/youtube.sh "Royal Match" --google-play com.dreamgames.royalmatch
#   scripts/mac/youtube.sh "Last War" --google-play com.fun.lastwar.gp --videos 2 --dry-run
#
# Anything after the title is passed to gametagger-genome (store IDs, --categories, ...).
source "$(dirname "$0")/common.sh"
need ffmpeg
need yt-dlp

if [[ $# -lt 1 ]]; then
  sed -n '2,8p' "$0"
  exit 1
fi
TITLE="$1"
shift
VIDEOS=2
MODE=(--live --budget-usd "$BUDGET" --observer-model "${OBSERVER_MODEL:-claude-sonnet-5}")
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --videos) VIDEOS="$2"; shift 2 ;;
    --dry-run) MODE=(); shift ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

SAFE="$(echo "$TITLE" | tr -cs 'A-Za-z0-9' '-' | sed 's/^-//; s/-$//' | tr 'A-Z' 'a-z')"
OUT="gametagger-media/$SAFE"
mkdir -p "$OUT"
uv run gametagger-genome --game-id "youtube:$SAFE" --title "$TITLE" \
  --youtube never --youtube-gameplay "$VIDEOS" --burst-strategy auto --bursts 10 \
  --max-observer-tokens 120000 --media-dir "$OUT" --save-dossier "$OUT/dossier.json" \
  --output "$OUT/result.json" ${ARGS[@]+"${ARGS[@]}"} ${MODE[@]+"${MODE[@]}"}
echo
echo "Saved: $OUT/result.json (tags) and $OUT/dossier.json (evidence)."
