#!/usr/bin/env bash
# Read Google Play's Top grossing chart from the Android emulator. Free; no keys needed.
#
#   scripts/mac/play-chart.sh                 # open the chart and read it
#   scripts/mac/play-chart.sh --check PKG...  # open these games' store pages and save what they say
#
# Start an emulator with a Google Play system image, signed in. The script opens the Play Store,
# declines any welcome or location prompt ("Not now", "No thanks"), taps Games > Top charts > Top
# grossing, then scrolls the list. Those are the only taps: never a game, Install or a purchase.
# Screenshots and screen text go to benchmark-runs/play-chart/ (never committed);
# experiments/play-chart/parse_dump.py turns them into a chart file.
#
# The Play Store hides games the emulator cannot run (Township among them), so the chart has gaps.
# See experiments/play-chart/README.md.
set -euo pipefail
cd "$(dirname "$0")/../.."
if ! command -v adb >/dev/null && [[ -x "$HOME/Library/Android/sdk/platform-tools/adb" ]]; then
  export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
fi
command -v adb >/dev/null || { echo "Missing: adb. Install Android Studio first."; exit 1; }
# With several emulators running, prefer one with the standard 4 KB page size.
if [[ -z "${ANDROID_SERIAL:-}" ]]; then
  for s in $(adb devices | awk 'NR>1 && $2=="device"{print $1}'); do
    if [[ "$(adb -s "$s" shell getconf PAGE_SIZE | tr -d '\r')" == 4096 ]]; then
      export ANDROID_SERIAL=$s
      break
    fi
  done
fi

OUT="benchmark-runs/play-chart/$(date +%Y%m%d-%H%M)"
mkdir -p "$OUT"
exec > >(tee "$OUT/log.txt") 2>&1

echo "=== $(date) ==="
adb devices
prop() { adb shell getprop "$1" | tr -d '\r'; }
echo "page size: $(adb shell getconf PAGE_SIZE | tr -d '\r')  serial: ${ANDROID_SERIAL:-default}"
echo "model: $(prop ro.product.model)  android: $(prop ro.build.version.release)"
echo "locale: $(prop persist.sys.locale) / $(prop ro.product.locale)  sim country: $(prop gsm.sim.operator.iso-country)"
echo "play store: $(adb shell dumpsys package com.android.vending | grep -m1 versionName | tr -d '\r ')"

dump() {  # save the screen's accessibility text to $1
  adb shell uiautomator dump /sdcard/gt-window.xml >/dev/null 2>&1
  adb pull /sdcard/gt-window.xml "$1" >/dev/null 2>&1
}
save() {  # save a screenshot and the screen's text as $OUT/$1.png and $OUT/$1.xml
  adb exec-out screencap -p >"$OUT/$1.png"
  dump "$OUT/$1.xml"
}
tap() {  # tap the first element whose text or description is exactly $1
  dump "$OUT/nav.xml"
  local xy
  xy=$(python3 - "$OUT/nav.xml" "$1" <<'PY'
import re, sys, xml.etree.ElementTree as ET
for n in ET.parse(sys.argv[1]).iter("node"):
    if sys.argv[2] in ((n.get("text") or "").strip(), (n.get("content-desc") or "").strip()):
        a, b, c, d = map(int, re.findall(r"\d+", n.get("bounds")))
        print((a + c) // 2, (b + d) // 2)
        break
PY
)
  if [[ -z "$xy" ]]; then
    echo "could not find '$1' on screen"
    return 1
  fi
  echo "tap '$1' at $xy"
  # shellcheck disable=SC2086
  adb shell input tap $xy
  sleep 5
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
echo "screen ${W}x${H}"

# Open the chart: Play Store > Games > Top charts > Top grossing.
adb shell am force-stop com.android.vending
sleep 1
adb shell monkey -p com.android.vending -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
sleep 8
for _ in 1 2 3; do  # a new phone shows welcome and location prompts first: decline them
  dump "$OUT/nav.xml"
  if grep -q '"Not now"' "$OUT/nav.xml"; then
    tap "Not now"
  elif grep -q '"No thanks"' "$OUT/nav.xml"; then
    tap "No thanks"
  else
    break
  fi
done
tap "Games" && tap "Top charts" || { echo "stopped: could not reach Top charts"; exit 1; }
dump "$OUT/nav.xml"
if ! grep -q '"Top grossing"' "$OUT/nav.xml"; then
  tap "Top free" || tap "Top paid" || true
  tap "Top grossing" || { echo "stopped: could not choose Top grossing"; exit 1; }
fi
dump "$OUT/nav.xml"
grep -q '"Top grossing"' "$OUT/nav.xml" || { echo "stopped: Top grossing is not selected"; exit 1; }
rm -f "$OUT/nav.xml"
echo "on Top grossing"

prev=""
for i in $(seq -w 0 59); do
  focus=$(adb shell dumpsys window | grep -m1 mCurrentFocus | tr -d '\r')
  if [[ "$focus" != *com.android.vending* ]]; then
    # A new phone can update the Play Store in the background, which closes it.
    echo "stopped at page $i: the Play Store left the screen ($focus). Run again."
    break
  fi
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
