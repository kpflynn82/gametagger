#!/bin/bash
# Pilot for REA: installs 5 free games from the Play Store on the emulator (official installs on
# the signed-in test account) and copies each installed game's APK files to play-chart/apks/.
# The only taps are "Install" on each game's own store page (and "Skip" if Play offers to add a
# payment method). It never opens a game, buys anything or changes settings.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/Library/Android/sdk/platform-tools:/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ -z "${ANDROID_SERIAL:-}" ]]; then
  for s in $(adb devices | awk 'NR>1 && $2=="device"{print $1}'); do
    if [[ "$(adb -s "$s" shell getconf PAGE_SIZE | tr -d '\r')" == 4096 ]]; then export ANDROID_SERIAL=$s; break; fi
  done
fi
OUT="play-chart/apks"; mkdir -p "$OUT"
NAV="$OUT/nav.xml"
dump() { adb shell uiautomator dump /sdcard/gt-window.xml >/dev/null 2>&1; adb pull /sdcard/gt-window.xml "$NAV" >/dev/null 2>&1; }
tap() {
  dump
  local xy
  xy=$(python3 - "$NAV" "$1" <<'PY'
import re, sys, xml.etree.ElementTree as ET
for n in ET.parse(sys.argv[1]).iter("node"):
    if sys.argv[2] in ((n.get("text") or "").strip(), (n.get("content-desc") or "").strip()):
        a, b, c, d = map(int, re.findall(r"\d+", n.get("bounds")))
        print((a + c) // 2, (b + d) // 2); break
PY
)
  if [[ -z "$xy" ]]; then echo "  could not find '$1' on screen"; return 1; fi
  echo "  tap '$1' at $xy"; adb shell input tap $xy; sleep 4
}
installed() { adb shell pm path "$1" 2>/dev/null | grep -q '^package:'; }
GAMES=("com.scopely.monopolygo|MONOPOLY GO!" "com.dreamgames.royalmatch|Royal Match" "com.king.candycrushsaga|Candy Crush Saga" "com.moonactive.coinmaster|Coin Master" "com.cyphergames.royalsmash|Royal Smash")
{
  echo "=== $(date) ==="
  adb devices
  echo "serial: ${ANDROID_SERIAL:-default}  page size: $(adb shell getconf PAGE_SIZE | tr -d '\r')  android: $(adb shell getprop ro.build.version.release | tr -d '\r')"
  for g in "${GAMES[@]}"; do
    p="${g%%|*}"; title="${g#*|}"
    echo "--- $p ($title)"
    if installed "$p"; then
      echo "  already installed"
    else
      adb shell input keyevent KEYCODE_HOME; sleep 1
      adb shell am start -a android.intent.action.VIEW -d "market://details?id=$p" com.android.vending >/dev/null 2>&1
      # Wait until this game's own store page is on screen (its title and an action button).
      ok=""
      for i in $(seq 1 12); do
        sleep 3; rm -f "$NAV"; dump
        if [[ -f "$NAV" ]] && grep -qF "$title" "$NAV" && grep -qE '"(Install|Open|Uninstall|Update|Cancel)"|compatible with this version' "$NAV"; then ok=1; break; fi
      done
      if [[ -z "$ok" ]]; then adb exec-out screencap -p > "$OUT/$p-store.png"; echo "  skipped: its store page did not appear (screenshot saved)"; continue; fi
      if grep -q "compatible with this version" "$NAV"; then echo "  skipped: Play says this device isn't compatible"; continue; fi
      if grep -q '"Cancel"' "$NAV"; then
        echo "  already downloading"
      else
        if ! tap "Install"; then adb exec-out screencap -p > "$OUT/$p-store.png"; echo "  skipped: no Install button (screenshot saved)"; continue; fi
        dump
        if grep -q '"Skip"' "$NAV"; then tap "Skip"; fi
      fi
      for i in $(seq 1 120); do
        if installed "$p"; then echo "  installed after $((i * 10)) s"; break; fi
        sleep 10
      done
      if ! installed "$p"; then echo "  not installed after 20 minutes; moving on"; continue; fi
    fi
    adb shell dumpsys package "$p" | grep -m1 versionName | tr -d '\r'
    mkdir -p "$OUT/$p"
    for f in $(adb shell pm path "$p" | tr -d '\r' | sed 's/^package://'); do
      adb pull "$f" "$OUT/$p/" >/dev/null && echo "  copied $(basename "$f") ($(du -h "$OUT/$p/$(basename "$f")" | cut -f1))"
    done
    adb shell input keyevent KEYCODE_BACK
  done
  rm -f "$NAV"
  echo "done"
} 2>&1 | tee -a "$OUT/log.txt"
echo; echo "You can close this window."
