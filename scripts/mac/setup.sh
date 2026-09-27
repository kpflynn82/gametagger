#!/usr/bin/env bash
# One-time Mac setup: the tools GameTagger's video and Android features need.
set -euo pipefail
cd "$(dirname "$0")/../.."

if ! command -v brew >/dev/null; then
  echo "Homebrew is needed first. Install it from https://brew.sh, then run this again."
  exit 1
fi
echo "Installing ffmpeg (video), yt-dlp (YouTube downloads), uv (Python) and adb (Android)..."
brew install ffmpeg yt-dlp uv
brew install --cask android-platform-tools
echo "Installing GameTagger's Python packages..."
uv sync --frozen --extra dev
echo
echo "Done. Checks:"
for tool in ffmpeg yt-dlp uv adb; do
  if command -v "$tool" >/dev/null; then echo "  $tool: ok"; else echo "  $tool: MISSING"; fi
done
echo
echo "For the Android player you also need Android Studio and an emulator; see docs/MAC_TOOLS.md."
