#!/bin/bash
# Read-only on the game: starts the Android 17 emulator (the one the teardown player used) if it
# is not running, lists MONOPOLY GO!'s app folder on shared storage, and copies its files smaller
# than 30 MB (except downloaded art bundles) to play-chart/mgo-data/, each checked by SHA-256. It does not open the game.
cd "$(dirname "$0")" || exit 1
SDK="$HOME/Library/Android/sdk"
export PATH="$SDK/platform-tools:$SDK/emulator:/opt/homebrew/bin:/usr/local/bin:$PATH"
PKG=com.scopely.monopolygo
OUT="play-chart/mgo-data"; mkdir -p "$OUT"
find16k() { for s in $(adb devices | awk 'NR>1 && $2=="device"{print $1}'); do
  [[ "$(adb -s "$s" shell getconf PAGE_SIZE | tr -d '\r')" == 16384 ]] && { echo "$s"; return; }; done; }
{
  echo "=== $(date) ==="
  echo "AVDs: $(emulator -list-avds | tr '\n' ' ')"
  SERIAL=$(find16k); STARTED=""
  if [[ -z "$SERIAL" ]]; then
    for avd in $(emulator -list-avds); do
      cfg="$HOME/.android/avd/$avd.avd/config.ini"
      if grep -qiE "16k|android-37|CinnamonBun" "$cfg" 2>/dev/null; then AVD=$avd; break; fi
    done
    if [[ -z "${AVD:-}" ]]; then echo "stopped: no Android 17 emulator found"; exit 1; fi
    echo "starting $AVD"
    nohup emulator -avd "$AVD" >/dev/null 2>&1 &
    STARTED=1
    for i in $(seq 1 60); do sleep 5; SERIAL=$(find16k); [[ -n "$SERIAL" ]] && break; done
    if [[ -z "$SERIAL" ]]; then echo "stopped: emulator did not come up"; exit 1; fi
    for i in $(seq 1 60); do [[ "$(adb -s "$SERIAL" shell getprop sys.boot_completed | tr -d '\r')" == 1 ]] && break; sleep 5; done
  fi
  export ANDROID_SERIAL=$SERIAL
  echo "device $SERIAL: android $(adb shell getprop ro.build.version.release | tr -d '\r'), $PKG $(adb shell dumpsys package $PKG | grep -m1 versionName | tr -d '\r ')"
  ROOT="/sdcard/Android/data/$PKG"
  adb shell "find $ROOT -type f -exec stat -c '%s %n' {} + 2>/dev/null" | tr -d '\r' | sort -k2 > "$OUT/files.txt"
  echo "$(wc -l < "$OUT/files.txt") files, $(awk '{s+=$1} END {printf "%.0f MB", s/1e6}' "$OUT/files.txt") in $ROOT"
  while read -r size path; do
    [[ "$size" -gt 31457280 ]] && continue
    rel="${path#$ROOT/}"; dst="$OUT/$rel"
    # Downloaded art and shader bundles (about 820 MB) are skipped; their names are in files.txt.
    [[ "$rel" == files/UnityCache/* || "$rel" == cache/UnityShaderCache/* ]] && continue
    [[ -f "$dst" && "$(stat -f %z "$dst")" == "$size" ]] && continue
    mkdir -p "$(dirname "$dst")"
    # adb reads standard input, which here is files.txt: give it nothing instead.
    adb exec-out "cat '$path' 2>/dev/null" </dev/null > "$dst"
    want=$(adb shell "sha256sum '$path'" </dev/null | tr -d '\r' | cut -d' ' -f1)
    got=$(shasum -a 256 "$dst" | cut -d' ' -f1)
    [[ "$want" == "$got" ]] || echo "  checksum differs: $rel"
  done < "$OUT/files.txt"
  echo "copied $(find "$OUT" -type f ! -name files.txt ! -name log.txt | wc -l | tr -d ' ') files to $OUT"
  if [[ -n "$STARTED" ]]; then adb emu kill >/dev/null 2>&1; echo "stopped the emulator this launcher started"; fi
  echo "done"
} 2>&1 | tee -a "$OUT/log.txt"
echo; echo "You can close this window."
