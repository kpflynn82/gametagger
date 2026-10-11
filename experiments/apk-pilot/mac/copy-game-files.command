#!/bin/bash
# Read-only: copies the installed files (APK set) of the pilot games already installed on the
# emulator to play-chart/apks/<package>/. Installs nothing and opens nothing.
# Large "adb pull" transfers dropped the emulator connection, so each file is streamed in 8 MB
# pieces with "adb exec-out dd", then its size and SHA-256 are checked against the device's.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/Library/Android/sdk/platform-tools:/opt/homebrew/bin:/usr/local/bin:$PATH"
OUT="play-chart/apks"; mkdir -p "$OUT"
copy() {  # copy DEVICE_PATH LOCAL_FILE
  local src="$1" dst="$2" size chunks i want got
  size=$(adb shell stat -c %s "$src" | tr -d '\r')
  chunks=$(( (size + 8388607) / 8388608 ))
  : > "$dst.part"
  for ((i = 0; i < chunks; i++)); do
    for try in 1 2 3 4 5; do
      adb wait-for-device
      # The redirect runs on the device, so dd's own status lines never enter the copy.
      if adb exec-out "dd if='$src' bs=8388608 skip=$i count=1 2>/dev/null" > "$dst.chunk" && [[ -s "$dst.chunk" ]]; then break; fi
      echo "    piece $i failed (try $try); waiting"; sleep 5
    done
    cat "$dst.chunk" >> "$dst.part"
  done
  rm -f "$dst.chunk"
  want=$(adb shell sha256sum "$src" | tr -d '\r' | cut -d' ' -f1)
  got=$(shasum -a 256 "$dst.part" | cut -d' ' -f1)
  if [[ "$want" == "$got" ]]; then mv "$dst.part" "$dst"; echo "  copied $(basename "$dst") ($(du -h "$dst" | cut -f1), sha256 ok)";
  else echo "  FAILED $(basename "$dst"): sha256 differs (device $want, copy $got)"; fi
}
{
  echo "=== $(date) ==="
  for p in com.scopely.monopolygo com.dreamgames.royalmatch com.king.candycrushsaga com.moonactive.coinmaster com.cyphergames.royalsmash; do
    adb wait-for-device
    paths=$(adb shell pm path "$p" 2>/dev/null | tr -d '\r' | sed -n 's/^package://p')
    if [[ -z "$paths" ]]; then echo "--- $p: not installed"; continue; fi
    echo "--- $p: $(adb shell dumpsys package "$p" | grep -m1 versionName | tr -d '\r ')"
    mkdir -p "$OUT/$p"
    for f in $paths; do
      name=$(basename "$f")
      if [[ -f "$OUT/$p/$name" && "$(stat -f %z "$OUT/$p/$name")" == "$(adb shell stat -c %s "$f" | tr -d '\r')" ]]; then echo "  $name already copied"; continue; fi
      copy "$f" "$OUT/$p/$name"
    done
  done
  echo "done"
} 2>&1 | tee -a "$OUT/log.txt"
echo; echo "You can close this window."
