#!/usr/bin/env sh
# Reset and run the sample scenario in MOCK mode (no LLM, no network, no cost).
#
# Effects (nothing else is touched):
#   - deletes and recreates ./demo-workspace/ -- only if it carries the .demo-workspace marker
#     and contains no runs other than the demo's own (otherwise it stops without changing anything)
#   - overwrites site/data/demo-run.js
#   - re-renders site/media/demo-replay.* unless --skip-video is given (needs Pillow + ffmpeg), then mixes in
#     the licensed music if .cache/music/Clean Soul.mp3 exists (needs Node + Chrome; see docs/music-license.md)
# Your own workspaces (e.g. ./workspace/) and raw sources are never read or written.
set -e
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
command -v "$PY" >/dev/null 2>&1 || PY=python
echo "run_mock_demo: MOCK mode - proposal comes from a hand-authored fixture, not an LLM."
"$PY" tools/demo.py run
if [ "$1" = "--skip-video" ]; then
  echo "run_mock_demo: skipped video; verify will report it as stale for the new run id."
else
  "$PY" tools/make_replay_video.py
  if [ -f ".cache/music/Clean Soul.mp3" ]; then
    node tools/mix_soundtrack.mjs
  else
    echo "run_mock_demo: music file not found; the video stays silent. See docs/music-license.md to add it."
  fi
fi
echo "run_mock_demo: done. Open site/index.html, or check with: scripts/verify_demo.sh"
