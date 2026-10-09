#!/usr/bin/env bash
# Read Google Play's Top grossing chart from the Android emulator. Free; no keys needed.
#
#   scripts/mac/play-chart.sh                 # read the chart that is on screen
#   scripts/mac/play-chart.sh --check PKG...  # open these games' store pages and save what they say
#
# Open the Play Store in the emulator on Games > Top charts > Top grossing first. The script only
# scrolls the list (and, with --check, opens store pages and goes back). It never taps Install or
# anything else. Screenshots and screen text go to benchmark-runs/play-chart/ (never committed);
# experiments/play-chart/parse_dump.py turns them into a chart file.
#
# The Play Store hides games that cannot run on the emulator's system image. A 16 KB page-size
# image (sdk_gphone16k) hid 5 of September's top 50, Township among them. Use a standard 4 KB
# Google Play image for chart reading. See experiments/play-chart/README.md.
set -euo pipefail
cd "$(dirname "$0")/../.."
if ! command -v adb >/dev/null && [[ -x "$HOME/Library/Android/sdk/platform-tools/adb" ]]; then
  export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
fi
command -v adb >/dev/null || { echo "Missing: adb. Install Android Studio first."; exit 1; }

OUT="benchmark-runs/play-chart/$(date +%Y%m%d-%H%M)"
mkdir -p "$OUT"
exec > >(tee "$OUT/log.txt") 2>&1

echo "=== $(date) ==="
adb devices
prop() { adb shell getprop "$1" | tr -d '\r'; }
echo "model: $(prop ro.product.model)  android: $(prop ro.build.version.release)"
echo "page size: $(adb shell getconf PAGE_SIZE | tr -d '\r')  locale: $(prop persist.sys.locale)$(prop ro.product.locale)"
echo "play store: $(adb shell dumpsys package com.android.vending | grep -m1 versionName | tr -d '\r ')"

save() {  # save a screenshot and the screen's text as $OUT/$1.png and $OUT/$1.xml
  adb exec-out screencap -p >"$OUT/$1.png"
  adb shell uiautomator dump /sdcard/gt-window.xml >/dev/null 2>&1
  adb pull /sdcard/gt-window.xml "$OUT/$1.xml" >/dev/null 2>&1
}

if [[ "${1:-}" == "--check" ]]; then
  shift
  for pkg in "$@"; do
    adb shell am start -a android.intent.action.VIEW -d "market://details?id=$pkg" \
      com.android.vending >/dev/null 2>&1
    sleep 6
    save "$pkg"
    echo "saved $pkg"
    adb shell input keyevent KEYCODE_BACK
    sleep 2
  done
  echo "done: $OUT"
  exit 0
fi

read -r W H < <(adb shell wm size | tr -d '\r' | awk -F'[ x]' '/Physical/{print $3, $4}')
# Back to the top of the chart: quick downward flicks.
for _ in $(seq 1 14); do
  adb shell input swipe $((W / 2)) $((H * 30 / 100)) $((W / 2)) $((H * 85 / 100)) 120
  sleep 0.4
done
sleep 2
prev=""
for i in $(seq -w 0 59); do
  save "$i"
  sum=$(md5 -q "$OUT/$i.xml" 2>/dev/null || md5sum "$OUT/$i.xml" | cut -d' ' -f1)
  if [[ -n "$sum" && "$sum" == "$prev" ]]; then
    echo "page $i is the same as the last one: end of the list"
    break
  fi
  prev=$sum
  echo "page $i saved"
  # A slow swipe up from 75% to 35% of the screen height scrolls without flinging.
  adb shell input swipe $((W / 2)) $((H * 75 / 100)) $((W / 2)) $((H * 35 / 100)) 700
  sleep 2
done
echo "done: $OUT"
echo "next: uv run python experiments/play-chart/parse_dump.py $OUT"
