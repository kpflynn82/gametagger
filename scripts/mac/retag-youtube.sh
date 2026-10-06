#!/usr/bin/env bash
# Pilot: do YouTube gameplay videos decide more of the v2 mobile tags than store pages alone?
# Five games from the Google Play top 50, with two of each game's most-watched YouTube gameplay
# videos added to the store page. Images and frames are described on your Claude plan; Jev is
# capped at $0.25 in this pilot's own ledger. Compare with experiments/mobile-retag-v2.
#
#   scripts/mac/retag-youtube.sh
#
# Downloading from YouTube is against YouTube's terms; the owner approved it as a proof of
# concept on September 27, 2026. Downloads stay in the git-ignored benchmark-runs/ folder.
source "$(dirname "$0")/common.sh"
need ffmpeg

WORKDIR="benchmark-runs/mobile-retag-v2-youtube"
STORE_ONLY="benchmark-runs/mobile-retag-v2"
JEV_CAP="${GAMETAGGER_JEV_CAP_USD:-0.25}"
MODEL="${OBSERVER_MODEL:-claude-sonnet-5}"
GAMES="${PILOT_GAMES:-gp-com.dreamgames.royalmatch,gp-com.scopely.monopolygo,gp-com.fun.lastwar.gp,gp-com.moonactive.coinmaster,gp-com.king.candycrushsaga}"
mkdir -p "$WORKDIR"
AWAKE=()
if command -v caffeinate >/dev/null; then
  AWAKE=(caffeinate -i)
fi

# Screenshots already described in the store-only run are reused, not described again.
if [[ -d "$STORE_ONLY/descriptions" && ! -d "$WORKDIR/descriptions" ]]; then
  cp -R "$STORE_ONLY/descriptions" "$WORKDIR/descriptions"
fi

echo "1/4 Checking that Claude Code is logged in to your Claude plan..."
uv run gametagger-compare --workdir "$WORKDIR" check-plan --model "$MODEL"

echo
echo "2/4 Gathering store pages plus 2 YouTube gameplay videos per game (free)..."
uv run --with yt-dlp gametagger-compare --workdir "$WORKDIR" dossiers --list mobile \
  --games "$GAMES" --youtube-gameplay 2

echo
echo "3/4 Tagging: frames described on your plan (scene-change sampling), Jev capped at \$$JEV_CAP..."
${AWAKE[@]+"${AWAKE[@]}"} uv run gametagger-compare --workdir "$WORKDIR" run --live \
  --use-max-plan --vocabulary v2 --arms rich --list mobile --games "$GAMES" \
  --budget-usd "$JEV_CAP" --observer-model "$MODEL" --bursts 12 --burst-strategy auto \
  --retry-failed | tee "$WORKDIR/run-summary.json" \
  || echo "The run stopped early (see above). Finished games are kept; run this again to go on."

echo
echo "4/4 Summarizing..."
uv run python experiments/mobile-retag-v2/summarize.py --workdir "$WORKDIR" \
  --out experiments/mobile-retag-v2/youtube-pilot
echo
echo "Done. Results: experiments/mobile-retag-v2/youtube-pilot/summary.json."
