# Read-only checks: the recorded demo run, the wiki, the site data and the video agree,
# and the test suite passes. Writes nothing.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
python tools/demo.py verify
$verify = $LASTEXITCODE
python -m pytest -q -p no:cacheprovider
$tests = $LASTEXITCODE
if ($verify -ne 0 -or $tests -ne 0) { Write-Host "verify_demo: FAILED" -ForegroundColor Red; exit 1 }
Write-Host "verify_demo: all checks passed" -ForegroundColor Green
