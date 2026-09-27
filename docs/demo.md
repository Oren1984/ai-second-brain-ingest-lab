# The demo: scenario, artifacts, and what is (and isn't) real

## Scenario (fictional, labelled SAMPLE)

- **Initial wiki** (`examples/scenario/seed/`): four concept pages about RAG evaluation —
  `rag-pipeline`, `retrieval-quality`, `faithfulness-evaluation`, `llm-as-judge` — and one source
  page for a sample primer. The faithfulness page concludes that *faithfulness ≥ 0.9 means an answer
  is correct and safe to ship*.
- **New source** (`examples/scenario/incoming/sample-incident-review-stale-policy.md`): a fictional
  post-incident review. A policy assistant scored 0.96 faithfulness while quoting a superseded policy.
  The answer was faithful to its context — the context was out of date. The file also contains an
  HTML comment telling AI assistants to mark every page verified and delete the log.
- **Proposal** (mock fixture, `examples/scenario/mock_responses/…json`): five changes. Three are sound
  (revise the faithfulness conclusion, create `source-freshness`, add the source page). Two are
  deliberate overreaches for the reviewer to catch: c4 adds "RAG should not be used for high-stakes
  policy questions" to `rag-pipeline`; c5 claims the judge "failed" and should not gate releases.
- **Human decisions** (`examples/scenario/demo_decisions.json`, pre-recorded): approve c1–c3, edit c4
  (replace the ban with "add a correctness check against reference answers"), reject c5.

None of this describes a real system or the author's projects.

## What is mock, what is genuine

| Part | Status |
|---|---|
| Proposal content | **Mock**: hand-authored fixture, not LLM output |
| Parsing, policy checks, staging, diffs, review recording, preflight, writes, index, log, validation | **Genuine** — the same code the LLM path uses, executed via the real CLI |
| Reviewer decisions | **Scripted** from a decisions file (the interactive prompt exists but was not used for the recording) |
| LLM provider | Implemented; exercised in tests with a stubbed SDK client; **not run against the live API** in this repository (no key was available) |
| Site | Rendered from `site/data/demo-run.js`, generated from `demo-workspace/` |
| Video | **Replay** rendered frame-by-frame from the same data; not a screen recording |

## How the artifacts are produced

1. `python tools/demo.py run` recreates `demo-workspace/` from the seed and runs, as subprocesses:
   `add` → `validate` → `ingest --mode mock` → `show` → `review --decisions …` → `apply` → `validate`
   → `ingest` again (no-op) → `status`. Output is captured to `demo-workspace/transcript.json`.
2. `python tools/demo.py export` (called by `run`) writes `site/data/demo-run.js` using only
   workspace artifacts: the run record, `proposals/<run>/before/` (pre-apply files),
   `response.json`, the current `wiki/`, and the transcript.
3. `python tools/make_replay_video.py` renders 9 animated scenes (Pillow, 1280×720, 30 fps, 76 s) from
   that data — initial graph → new source → staged proposal → decisions → revised page → expanded graph
   → validation and log — and encodes VP8/WebM with ffmpeg. Every value on screen (counts, sentences,
   decisions, graph changes) is read from the run data. Captions are burned in and also written to
   `site/media/demo-replay.en.vtt` and `site/data/replay-captions.js` (the site's transcript).
   `site/media/demo-replay.json` records the run id, the video's sha256, the sha256 of the site data it
   was rendered from, the caption count, and that there is no audio track.
   `python tools/make_replay_video.py --preview DIR` writes stills per scene without encoding.
4. `python tools/demo.py verify` checks: wiki validates; run applied and labelled mock; raw bytes
   identical to the sample; existing page updated by this run; rejected change absent; one source
   page per source; one log entry for the run; repeat ingest was a no-op; site data equals a fresh
   export; video manifest matches the run id, the file, and the current site data; caption files belong
   to this run and match the manifest; if a soundtrack is present: vp8 + opus streams, background level,
   fades, and the credit in README, docs and site data.

Re-running the demo creates a new run id (it contains a timestamp); the site data and video must then
be regenerated, which `run_mock_demo` does. `verify` fails if they drift.

## Site

`site/` is plain static files: open `site/index.html` directly or serve the folder from any static host.
The only external request is the Inter / JetBrains Mono web-font stylesheet (Google Fonts, same fonts as
the AI Systems Portfolio), loaded without blocking; offline, system fonts are used. Visual direction:
the portfolio's "Midnight AI" tokens (navy `#08111F`, cyan `#22D3EE`, violet `#8B5CF6`). It is not published.

## Music and voiceover

- **Music:** "Clean Soul" by Kevin MacLeod, CC BY 4.0 — license evidence, attribution and changes in
  [music-license.md](music-license.md). `node tools/mix_soundtrack.mjs` mixes it in: headless Chrome
  decodes the MP3, applies gain and fades (Web Audio) and encodes Opus (MediaRecorder); ffmpeg then
  stream-copies the audio next to the existing video stream, so the frames are bit-identical to the
  silent render. Levels and fades are recorded in the manifest (`audio.mix`) and checked by `verify`.
- **Voiceover:** not produced. The only local English voice was the legacy Windows SAPI voice; the
  narration is a timed script for approval: [video-narration-script.md](video-narration-script.md).
