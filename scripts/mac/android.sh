#!/usr/bin/env bash
# Let Claude play an Android game on the emulator, record it, then tag the recording.
#
#   scripts/mac/android.sh com.dreamgames.royalmatch                # check setup (free)
#   scripts/mac/android.sh com.dreamgames.royalmatch --play          # play 12 min, then tag
#   scripts/mac/android.sh com.dreamgames.royalmatch --play --minutes 6
#
# Start the emulator in Android Studio first, signed in to a Google account with no payment
# method, with the game installed.
source "$(dirname "$0")/common.sh"
need adb
need ffmpeg

if [[ $# -lt 1 ]]; then
  sed -n '2,9p' "$0"
  exit 1
fi
PACKAGE="$1"
shift
if [[ "${1:-}" != "--play" ]]; then
  uv run gametagger-play "$PACKAGE" --check "$@"
  exit $?
fi
shift

uv run gametagger-play "$PACKAGE" --budget-usd "$BUDGET" "$@"
LATEST="$(ls -td gametagger-play/"$PACKAGE"/*/ 2>/dev/null | head -1)"
if [[ -z "$LATEST" || ! -f "$LATEST/dossier.json" ]]; then
  echo "No recording to tag."
  exit 1
fi
echo
echo "Tagging the recording together with the Google Play listing..."
uv run gametagger-genome "$LATEST/dossier.json" --google-play "$PACKAGE" \
  --burst-strategy auto --bursts 12 --max-observer-tokens 150000 \
  --live --budget-usd "$BUDGET" --observer-model "${OBSERVER_MODEL:-claude-sonnet-5}" \
  --output "$LATEST/result.json"
echo
echo "Saved: $LATEST (recording, steps, screenshots, dossier.json, result.json)."
