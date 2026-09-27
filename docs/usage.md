# Usage

Requirements: Python 3.10+ (developed and tested on 3.12). Mock mode needs no packages. Tests need `pytest`; the replay video needs
Pillow and an ffmpeg with the VP8 encoder (`pip install -r requirements-dev.txt`). Adding the music needs
Node 18+, Chrome, and the track downloaded once into `.cache/music/` — see [music-license.md](music-license.md).

Commands below run from the repository root. `-w` selects the workspace (default `./workspace`,
or `$BRAIN_WORKSPACE`).

## Mock demo

Windows PowerShell:

```powershell
.\scripts\run_mock_demo.ps1            # reset demo-workspace\, run the scenario, export site data, render video
.\scripts\run_mock_demo.ps1 -SkipVideo # same, without the video
.\scripts\verify_demo.ps1              # read-only checks + tests
start site\index.html                  # open the presentation
```

If script execution is disabled on your machine, run a single invocation with
`powershell -ExecutionPolicy Bypass -File scripts\run_mock_demo.ps1`, or call the Python directly:
`python tools/demo.py run`, `python tools/make_replay_video.py`, `python tools/demo.py verify`.

macOS / Linux / Git Bash:

```sh
scripts/run_mock_demo.sh [--skip-video]
scripts/verify_demo.sh
```

`run_mock_demo` only deletes `demo-workspace/` if it carries the `.demo-workspace` marker and holds no
runs it didn't create; it also overwrites `site/data/demo-run.js` and `site/media/demo-replay.*`.

## Your own second brain

```powershell
python -m brain init workspace                                  # empty workspace (gitignored)
python -m brain -w workspace add C:\path\to\notes.md            # copy into raw/ (never overwrites)
python -m brain -w workspace ingest raw/notes.md --mode llm     # stage a proposal; wiki/ untouched
python -m brain -w workspace show <run-id>                      # proposal, contradictions, diffs
python -m brain -w workspace review <run-id>                    # interactive: [a]pprove [r]eject [e]dit
python -m brain -w workspace apply <run-id>                     # write approved changes, index, log
python -m brain -w workspace validate
python -m brain -w workspace status
```

Non-interactive review: `review <run-id> --decisions decisions.json`, `--approve-all`, or
`--reject-all --note "why"`. See `examples/scenario/demo_decisions.json` for the file format
(including a scripted `edit`).

**Edit** means: open the staged file printed by the prompt (`proposals/<run>/pages/...`), change it,
save, press Enter. `apply` re-checks the edited page and records that the reviewer changed it.

Mock mode only covers the bundled sample source; for anything else use `--mode llm`.

## Genuine LLM mode

```powershell
pip install -r requirements-llm.txt
$env:ANTHROPIC_API_KEY = "<your key>"        # read from the environment only; never written to disk
$env:BRAIN_LLM_MODEL  = "claude-opus-5"      # optional (default claude-opus-5)
$env:BRAIN_LLM_EFFORT = "high"               # optional: low | medium | high | xhigh | max
python -m brain -w workspace ingest raw/notes.md --mode llm
```

```sh
export ANTHROPIC_API_KEY=...   # bash equivalent
```

One Messages API request per ingest, with structured JSON output constrained to the proposal schema
and (for Opus 5 / Fable models) Anthropic's server-side refusal fallback. The prompt that was sent is
saved in `proposals/<run>/prompt.txt`; the raw response in `response.json`. This is a paid API call.

To try the LLM on the sample scenario (the `llm-trial/` folder is gitignored):

```powershell
Copy-Item -Recurse examples\scenario\seed llm-trial
Copy-Item examples\scenario\incoming\sample-incident-review-stale-policy.md llm-trial\raw\
python -m brain -w llm-trial ingest raw/sample-incident-review-stale-policy.md --mode llm
```

## Tests

```powershell
python -m pytest -q
```
