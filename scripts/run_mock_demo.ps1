# Reset and run the sample scenario in MOCK mode (no LLM, no network, no cost).
#
# Effects (nothing else is touched):
#   - deletes and recreates .\demo-workspace\  -- only if it carries the .demo-workspace marker
#     and contains no runs other than the demo's own (otherwise it stops without changing anything)
#   - overwrites site\data\demo-run.js
#   - re-renders site\media\demo-replay.* unless -SkipVideo is given (needs Pillow + ffmpeg), then mixes in
#     the licensed music if .cache\music\Clean Soul.mp3 exists (needs Node + Chrome; see docs\music-license.md)
# Your own workspaces (e.g. .\workspace\) and raw sources are never read or written.
param([switch]$SkipVideo)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "run_mock_demo: MOCK mode - proposal comes from a hand-authored fixture, not an LLM." -ForegroundColor Yellow
python tools/demo.py run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($SkipVideo) {
    Write-Host "run_mock_demo: skipped video; verify will report it as stale for the new run id." -ForegroundColor Yellow
} else {
    python tools/make_replay_video.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if (Test-Path ".cache\music\Clean Soul.mp3") {
        node tools/mix_soundtrack.mjs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } else {
        Write-Host "run_mock_demo: music file not found; the video stays silent. See docs\music-license.md to add it." -ForegroundColor Yellow
    }
}
Write-Host "`nrun_mock_demo: done. Open site\index.html, or check with: .\scripts\verify_demo.ps1"
