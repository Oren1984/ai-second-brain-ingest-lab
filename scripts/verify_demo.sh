#!/usr/bin/env sh
# Read-only checks: the recorded demo run, the wiki, the site data and the video agree,
# and the test suite passes. Writes nothing.
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
command -v "$PY" >/dev/null 2>&1 || PY=python
status=0
"$PY" tools/demo.py verify || status=1
"$PY" -m pytest -q -p no:cacheprovider || status=1
[ $status -eq 0 ] && echo "verify_demo: all checks passed" || echo "verify_demo: FAILED"
exit $status
