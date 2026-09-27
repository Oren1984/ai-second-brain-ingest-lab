# SESSION_HANDOFF — ai-second-brain-ingest-lab

Continuity file for any agent resuming this work. Records real state only.

## Current status

**Complete and owner-approved (2026-09-27).** The owner reviewed the site and video manually and approved commit + push to `main` (`origin` = github.com/Oren1984/ai-second-brain-ingest-lab). The project is committed on `main` and pushed; see `git log` for the commit. **The site has not been published or deployed** — `site/` is only in the repository.

Final recorded demo run: `20260927T125935Z-mock-f471c0` (**mock** — re-run by the owner during manual review; site data, video, soundtrack and captions were regenerated together). Final checks before commit: `python tools/demo.py verify` 25/25, `python -m pytest` 23 passed, replay video 76.0 s with VP8 video + Opus audio.

Pre-commit hygiene (verified): only project files staged; no API keys (the only key-like string is the fake `sk-ant-api03-SECRETSECRETSECRET` in the redaction test); no absolute user paths; the downloaded MP3 (`.cache/`), `__pycache__/` and `.pytest_cache/` are gitignored and not committed.

## Phase 1 — Inspect & plan (done 2026-09-27)

### Repository evidence
- Repo contained only `README.md` (one line) and one commit (`9318bf4 Initial commit`); clean tree, branch `main`.
- No project-level `CLAUDE.md`. Global router (`~/.claude/CLAUDE.md`) applies: lean, least privilege, no commit/push/deploy without approval.
- Tooling on this machine: Python 3.12.10, pytest 8.3, Pillow 12.3, Node 24, Chrome, Playwright-cached `ffmpeg-win64.exe` (encoders: VP8/WebM; decoders: MJPEG).
- `anthropic` SDK not installed; `ANTHROPIC_API_KEY` not set → a genuine LLM run cannot be executed in this session.

### Scenario (fictional, labeled SAMPLE)
An AI-assurance wiki about RAG evaluation. Seed knowledge base: `rag-pipeline`, `retrieval-quality`, `faithfulness-evaluation`, `llm-as-judge`, plus one ingested source (`src-rag-eval-primer`). The faithfulness page currently concludes that *a high faithfulness score means the answer is correct and safe to ship*.
New source: a fictional post-incident review where an HR-policy assistant scored 0.96 faithfulness but answered from a **superseded** policy document. This contradicts the existing conclusion (faithful ≠ correct/current). The source also contains an embedded instruction addressed to AI assistants (prompt-injection test string).

### Design decisions
- Python stdlib CLI package `brain/` (`python -m brain ...`). Zero runtime deps for mock mode; `anthropic` SDK is an optional dependency imported only in `--mode llm`.
- Workspace layout: `raw/` (immutable sources) · `wiki/concepts/`, `wiki/sources/`, `wiki/index.md`, `wiki/log.md` (generated knowledge) · `proposals/<run>/` (staged, unapproved) · `runs/<run>.json` (audit records).
- Flow: `ingest` (read raw → load wiki → provider proposal → schema/policy validation → stage files + diffs) → `review` (per-change approve / reject / edit) → `apply` (build candidate wiki in memory → validate → atomic write → index → log) → `validate`.
- Mock provider returns a hand-authored fixture JSON **through the same parse/validate/stage/review/apply path**; it is labeled mock in run ids, run records, CLI banners, page `updated` fields, the log, site and video.
- Engine owns provenance fields (`id`, `updated`, `raw_path`, `raw_sha256`), the index and the log; the model may only create/update concept pages and this source's page.
- Presentation: static site in `site/` with data generated from the recorded run; replay video rendered from run artifacts (Pillow frames → ffmpeg VP8), labeled as a replay.

### Acceptance criteria
1. `python -m brain` runs the full E2E flow in mock mode with no network and no extra installs.
2. LLM mode uses the same code path; requires credentials only when selected; fails clearly without them.
3. Approved run: existing page meaningfully updated, source page created, new concept linked, index + log updated, validation passes.
4. Rejected run: wiki byte-identical. Raw source byte-identical in all cases.
5. Re-ingesting the same unchanged source: no new pages, no new log entries, no new run.
6. Model output cannot write outside allowed pages, cannot touch index/log/raw, cannot delete.
7. Tests cover approve/reject, repeat ingest, source preservation, links, failure handling; all pass.
8. Site and video are generated from the recorded run; `verify_demo` checks they agree with repository artifacts.
9. README states that the recorded demo is mock and how the video was produced.

## Phase 2 — Scenario, structure, schema, CLI (done)

### Done
- `schema/WIKI_SCHEMA.md` — page structure, linking, proposal format, allowed changes, untrusted-source rule, review rules, validation. Sent verbatim to the model as system instructions.
- `examples/scenario/seed/` — initial workspace (raw primer + 4 concept pages + 1 source page + generated index + seed log entry).
- `examples/scenario/incoming/sample-incident-review-stale-policy.md` — the new source (contains a deliberate prompt-injection string).
- `examples/scenario/mock_responses/sample-incident-review-stale-policy.json` — hand-authored mock proposal (5 changes, two deliberate overreaches c4/c5). Guarded by source sha256 and seed page hashes so it can't silently apply to a different state. Authored with a one-off script (not kept in repo).
- `examples/scenario/demo_decisions.json` — the scripted reviewer decisions (approve c1–c3, edit+approve c4, reject c5).
- `brain/` package: `pages.py` (front matter, links, index), `workspace.py` (layout, hashing, guarded writes, redaction), `validate.py`, `providers.py` (mock + Anthropic), `ingest.py` (ingest/review/apply/add), `cli.py`.
- `.gitattributes` forces LF and marks raw sources `-text` (core.autocrlf=true on this machine would otherwise change raw bytes and break sha256 provenance).

### Verified (manual run in a temp copy of the seed)
- ingest → proposal staged with diffs, injection patterns flagged; review via decisions file; apply wrote 4 changes, index rebuilt, log entry appended; validate PASSED (7 pages, 25 links, 1 needs-review warning).
- Re-ingest of the same source → `noop`, no run record, no log entry. Re-apply → `noop`. Raw sha256 unchanged.

### Decisions
- Raw sources must be inside `<workspace>/raw/`; `brain add` copies files in and never overwrites.
- Log lives in `wiki/log.md` and is written only on apply; a full rejection writes nothing under `wiki/` (the run record still records it).
- Pre-apply copies of touched files are kept in `proposals/<run>/before/` (rollback and before/after display).

## Phase 3 — Mock + LLM ingest through one flow; recorded demo (done)

### Done
- `tools/demo.py run|export|verify`. `run` resets `demo-workspace/` (only if the `.demo-workspace` marker is present and no foreign runs exist), then drives the **real CLI via subprocesses**: add → validate → ingest (mock) → show → review (decisions file) → apply → validate → repeat ingest → status. Output captured to `demo-workspace/transcript.json`.
- `export` derives `site/data/demo-run.js` from the artifacts only (run record, proposals/<run>/before, response.json, wiki/, transcript). Before-state is reconstructed from `before/` copies, not from the seed folder.
- `verify` checks wiki validity, run status/mode, raw bytes, existing-page update, rejected change absent, single log entry, repeat-ingest no-op, site data == fresh export, and (Phase 5) video manifest.

### Verified
- Recorded run `20260927T104722Z-mock-f471c0` (mock). verify: 15/16 PASS; the only failure is the not-yet-built replay video.
- `--mode llm` without `ANTHROPIC_API_KEY`: fails before any network call with a clear message; run recorded as `failed`; wiki untouched.
- LLM provider not executed against the live API (no key in this environment). Same `ProposalRequest` → text → `check_proposal` path as mock.

### Notes
- Windows console shows `—` as `�` when printing via cp1252; artifacts are UTF-8 (checked). CLI and demo.py reconfigure stdout to UTF-8.
- The recorded run id will change whenever `tools/demo.py run` is re-executed; site data and video must then be regenerated (verify catches drift).

## Phase 4 — Controls and tests (done)

### Controls in place (where)
- Governance: per-change human review gate (`record_review`); `apply` refuses unreviewed runs; schema doc defines allowed changes.
- Security: raw/ never in the write allowlist (`Workspace._check_writable`); page ids must be slugs (no path traversal); model cannot write index/log/other source pages or delete; source text sanitised and wrapped in `<untrusted_source>` (closing-tag escape neutralised); heuristic injection flags recorded; API key only from env, redacted from recorded errors; no tools given to the model.
- Observability: `runs/<id>.json` with mode, provider/model, source hash, stage events, security flags, proposal, decisions, applied/rejected, validation, errors.
- Quality: validator (fields, ids/paths, links, cited sources, raw hashes, duplicate titles, index freshness, needs-review and orphan warnings); preflight validation of the candidate wiki before any write; stale-proposal detection; mock fixture refuses a wiki state it wasn't written for.

### Tests — `python -m pytest` → 23 passed (tests/test_ingest.py)
Approve path (existing page update, links, index, log, reviewer edit, rejected change absent) · full rejection byte-identical · every change needs a decision · repeat ingest no-op (and pending proposal detection) · raw preserved + tamper detected · raw changed after proposal → apply refuses · write allowlist · validator errors · 7 hostile/invalid model outputs fail with nothing written · all-or-nothing apply · stale proposal · mock state guard · injection flagged + tag escape neutralised · LLM provider via stub client through same review/apply · LLM without key sends nothing · secret redaction · demo reset refuses unmarked dirs / foreign runs.

### Note
- This machine has pytest-asyncio installed globally; it prints a deprecation warning unrelated to this repo (`-p no:asyncio` silences it).

## Phase 5 — Static site and replay video (done)

### Done
- `site/` — plain static files (`index.html`, `styles.css`, `app.js`, `data/demo-run.js`, `media/`). No external requests, no build step; works from `file://` and any static host. Sections: hero + honesty banner + stats, story cards, pipeline (from run events, human gate highlighted), raw source (injection highlighted), wiki before, proposal & per-change review (with reviewer correction diff), before/after (side-by-side + unified), knowledge graph before/after (state, not process), validation, log entry, CLI transcript, video. Light/dark themes.
- All displayed values come from `data/demo-run.js`; every untrusted string is HTML-escaped before insertion.
- `tools/make_replay_video.py` — renders 12 scenes with Pillow from the site data and encodes VP8/WebM via ffmpeg (found through `$FFMPEG`, PATH, or Playwright's cached build; that build needs `-i pipe:0`). Outputs `site/media/demo-replay.webm` (99 s, ~4 MB), poster PNG, and `demo-replay.json` manifest (run id, sha256, source-data sha256, scenes). Every frame carries "REPLAY · MOCK RUN · <id>" and a "not a screen recording / no LLM" footer.
- `docs/img/*.png` — screenshots of the real rendered site (headless Chrome) for the docs.

### Verified
- `python tools/demo.py verify` → 18/18 (adds: video run id, video sha, video rendered from current site data).
- Real Chrome (via extension, served from 127.0.0.1): page renders 5 changes / 12 pipeline events, no console errors, video decodes (99 s, 1280×720), dark mode OK.
- 375 px layout emulated (headless Chrome enforces ~500 px min window, so media queries were forced in a probe copy): only overflow was the header badge → fixed (run id hidden on narrow screens).
- Every frame of the video reviewed via contact sheets; layout fixes applied (graph/claim overlap, injection shown in source scene).

### Limitations
- Deep links (`index.html#graph`) re-apply the hash after rendering; could not be observed in the automation tab (it stays `visibilityState=hidden`, so smooth scroll never advances). Normal browsers should be fine; unverified.
- Video is a replay rendered from artifacts, not a screen recording (stated on the site, in the video, and in its manifest).

## Phase 6 — Scripts, README, final verification (done)

### Done
- `scripts/run_mock_demo.ps1|.sh` (reset + run + export + video; `-SkipVideo`/`--skip-video`) and `scripts/verify_demo.ps1|.sh` (read-only: `tools/demo.py verify` + pytest). Effects are stated in each script header and printed at run time; reset refuses unmarked dirs or foreign runs.
- Privacy sweep of all files to be committed: the transcript leaked an absolute home path via `brain add` → `add` now prints workspace-relative paths and the demo passes a relative path. Re-scan: no usernames, emails, or key-like strings.
- Final E2E from a clean reset via PowerShell scripts: run `20260927T112029Z-mock-f471c0`, verify 18/18, tests 23 passed.

## Documentation phase (done)

- `docs/architecture.md` (components, layout, mermaid E2E sequence, stage table, design decisions, limits), `docs/controls.md` (governance/security/observability/quality with code locations and tests), `docs/usage.md` (PowerShell + sh, own workspace, LLM config), `docs/demo.md` (scenario, mock vs genuine table, how site/video are produced and verified), `docs/img/` (screenshots of the real rendered site, recaptured after the final run so the run id matches).
- `README.md` rewritten around What / Why / How: honesty note up front, flow diagram (mermaid), verbatim before/after from the recorded run, run metrics, screenshots, links to site/video/docs, short run instructions.
- Claim check (scripted): all relative links in README/docs resolve; README before/after blocks are verbatim substrings of the seed page and the recorded page; metrics (pages 5→7, wikilinks 15→25, 3 approved + 1 edited + 1 rejected, validation passed with 1 needs-review warning, 99 s video, 23 tests) match artifacts.

## Reproduce from a clean checkout (exact commands, repo root)

Prerequisites: Python 3.10+ (tested 3.12), `pip install -r requirements-dev.txt` (pytest, Pillow); for the
video an ffmpeg with the libvpx encoder (`$FFMPEG`, PATH, or Playwright's bundled copy); for the soundtrack
Node 18+ and Google Chrome.

Windows PowerShell:

```powershell
git clone https://github.com/Oren1984/ai-second-brain-ingest-lab.git
cd ai-second-brain-ingest-lab
pip install -r requirements-dev.txt

# 1. One-time: download the licensed music (CC BY 4.0, see docs/music-license.md). It stays in the
#    gitignored .cache/ folder and is never committed; the mixer checks its sha256.
New-Item -ItemType Directory -Force .cache\music | Out-Null
Invoke-WebRequest "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Clean%20Soul.mp3" -OutFile ".cache\music\Clean Soul.mp3"

# 2. Reset demo-workspace\, run the mock scenario through the real CLI, export site data,
#    render the replay video, then mix in the soundtrack (skipped with a warning if step 1 was not done).
.\scripts\run_mock_demo.ps1

# 3. Read-only checks: artifacts, site data, video, captions, soundtrack, credits + tests.
.\scripts\verify_demo.ps1

start site\index.html
```

sh / Git Bash equivalent:

```sh
mkdir -p .cache/music
curl -L -o ".cache/music/Clean Soul.mp3" "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Clean%20Soul.mp3"
scripts/run_mock_demo.sh && scripts/verify_demo.sh
```

Soundtrack only (on an existing silent render): `python tools/make_replay_video.py` then `node tools/mix_soundtrack.mjs`.
Expected result: `site/media/demo-replay.webm` 76.0 s, VP8 1280×720 + Opus 48 kHz stereo, body ≈ −23 dBFS RMS,
peaks −6 dBFS; `verify` 25/25. Each run creates a new run id (timestamp); site data, captions and video are
regenerated together. The docs screenshots in `docs/img/` do not show the run id.

## Known limitations / open items for the owner
- No genuine LLM run has been executed (no API key in this environment). To do one: see `docs/usage.md` → "Genuine LLM mode". A recorded LLM run would replace or sit alongside the mock demo; site/video tooling already labels mode from the run record.
- Replay video, not screen recording.
- Deep-link hash scrolling on the site unverified in automation (tab hidden).
- Whole wiki sent as context (fine at demo scale).
- Global blueprint modules (`~/.claude/modules`) were not instantiated: the owner's brief asked for a small number of files and a focused `docs/` folder; `docs/` + `schema/` cover context/architecture/rules/testing.

## Visual-upgrade phase (done 2026-09-27)

### Inputs reviewed
- Reference video: `~/Downloads/WhatsApp Video 2026-09-27 at 14.33.33.mp4` (29 s phone capture of an Instagram story, "fragments form new project": glowing points coalescing into a sphere). Used only for its sense of motion. The owner's site screenshots were not found on disk; the prior site was reviewed from the repo.
- Portfolio tokens fetched from `https://nfc4u.co.il/Salami/Ai-Systems-Portfolio/assets/css/tokens.css` (navy `#08111F`, cyan `#22D3EE`, violet `#8B5CF6`, Inter / JetBrains Mono).
- Email verified from the raw portfolio HTML (its only `mailto:`): `orensalmi1984@gmail.com`.

### Done
- **Site** (`site/index.html`, `styles.css`, `app.js` rewritten): dark "Midnight AI" design; hero with a compact, unambiguous MOCK disclosure (run id moved to the footer), animated constellation drawn from the recorded graph (static under `prefers-reduced-motion`, paused off-screen), stats row; video moved near the top with a text transcript of the captions; 3-phase flow (ingest / human review / apply) built from run events; inputs, review, before/after, graph, audit, "What is real in this demo", and a Contact section (portfolio, LinkedIn, GitHub, email). Skip link, focus styles, `aria-pressed` toggles, graph `<desc>`. Web fonts load non-blocking (a render-blocking font link had delayed all page scripts under slow network — found in QA and fixed).
- **Video** (`tools/make_replay_video.py` rewritten): 9 animated scenes, 76 s, 1280×720, 30 fps, rendered 2× and downsampled; story = fragments coalesce into the initial graph → source (injection flagged) → staged proposal with dashed proposed links → per-change verdicts (from the pre-recorded file, stated on screen) incl. the reviewer's correction → before/after conclusion → graph grows (new nodes/links, needs-review ring, rejected link) → validation + log + repeat-ingest no-op → outro. Process rail on every frame shows the graph is one stage. All values from run data. Burned-in captions; also `site/media/demo-replay.en.vtt` and `site/data/replay-captions.js`. `--preview DIR` renders stills.
- **Voiceover:** evaluated, not produced — only local voice is legacy SAPI "Microsoft Zira Desktop" and the available ffmpeg has no audio encoder. Timed script generated at `docs/video-narration-script.md` (~188 wpm; flagged as brisk for narration). **No music.**
- `tools/demo.py verify` gained two checks (captions belong to the run; captions match manifest) → 20 checks.
- Docs updated only where presentation changed: README (video length/captions/no audio, before/after screenshot, contact), `docs/demo.md` (video method, site fonts/visual direction, voiceover/music), `docs/img/*` recaptured from the new site (`pipeline.png` removed, `contact.png` added).

### Verified
- `python -m pytest` 23 passed; `python tools/demo.py verify` 20/20 (run `20260927T121442Z-mock-f471c0` — the demo was re-run via `run_mock_demo` at 15:14 during this phase, outside this agent's commands; site data, video and captions were regenerated together and agree).
- Headless Chrome over CDP (scratch script, not in repo): video loads and plays (76 s, 1280×720, advances in real time, no errors); desktop 1440 px no overflow, disclosure above the fold; true 390 px mobile emulation: zero overflowing elements; no console errors or failed requests.
- Real Chrome (extension): keyboard Tab order (skip link → brand → nav), Enter follows nav links, Space/Enter toggle `aria-pressed` buttons and update the graph description; contact hrefs exact. Portfolio and GitHub URLs return 200; LinkedIn returns 999 to non-browser clients (its bot response), URL as supplied by the owner.
- Video frames reviewed via per-scene stills (fixed: opaque translucent fills, missing ✓ glyph, clumped intro fragments, truncated log lines).

### Limitations
- Media playback could not be exercised in the extension tab (background tabs defer media loading); verified headlessly instead.
- Smallest rendered text on mobile is ~10.5 px (mono tags/labels).
- Video is 8.2 MB (particle motion is costly for VP8).

## Music phase (done 2026-09-27)

### Track and license
- **"Clean Soul" — Kevin MacLeod (incompetech.com)**, ISRC USUAN1300033, **CC BY 4.0**. Full record in `docs/music-license.md` (source URL, file sha256, exact attribution, changes, evidence, verification date 2026-09-27, residual notes).
- Verified from primary sources: incompetech FAQ (video use allowed incl. monetized; credit in video or description; exact credit format; edits must be disclosed), incompetech licensing page (free = Creative Commons, credit required), incompetech catalogue `pieces.json`, file served from incompetech.com (ID3: title/artist/"Royalty Free"), CC BY 4.0 deed (redistribute in any medium, adapt, with credit + license link + change notice). The track-level page on the publisher's licensing platform 404'd — noted, not relied on.
- Source MP3 stored only in gitignored `.cache/music/` (not committed or redistributed standalone); `tools/mix_soundtrack.mjs` refuses a file whose sha256 differs from the verified download.

### Done
- `tools/mix_soundtrack.mjs` (Node built-ins + Chrome + existing ffmpeg): headless Chrome decodes the MP3, Web Audio offline render applies gain (target −23 dBFS RMS, peak ceiling −6 dBFS → +7.2 dB), 3 s smoothstep fade-in, 5 s fade-out, trim to 76 s; MediaRecorder encodes Opus 128 kb/s; ffmpeg stream-copies audio next to the existing video. Updates `site/media/demo-replay.json` (`audio` block: track, license, levels, fades) and `site/data/replay-captions.js` (`audio` credit for the site).
- Site: credit under the video and in the footer (data-driven), video lede and "What is real" updated (music, no narration). README: Credits section + intro wording. Docs: `docs/music-license.md` (new), `docs/demo.md`, `docs/usage.md`; generated `docs/video-narration-script.md` wording corrected (no longer claims "no music").
- `scripts/run_mock_demo.ps1|.sh`: after rendering, mix music if `.cache/music/Clean Soul.mp3` exists, else keep the silent video and say so.
- `tools/demo.py verify`: +5 checks when a soundtrack is present — vp8+opus streams (via `ffmpeg -i` when available), background level, fades, credit in README + docs, credit in site data → 25 checks.

### Verified
- Full clean run via `.\scripts\run_mock_demo.ps1` (demo → render → mix) then `.\scripts\verify_demo.ps1`: 25/25, 23 tests passed. Run `20260927T124539Z-mock-f471c0`.
- Video stream bit-identical before/after muxing (extracted video streams: same sha256, same 8,459,113 bytes) → captions, visuals, timing, disclosures unchanged.
- File: 76.0 s, VP8 1280×720 30 fps + Opus 48 kHz stereo; 9.66 MB (was 8.46 MB silent).
- Levels (mixer): body −23.4 dBFS RMS, peak −6.0 dBFS; first 100 ms −180 dBFS, last 100 ms −73.6 dBFS.
- Headless Chrome playback with sound, desktop 1440 px and mobile 390 px emulation: audio decoded (webkitAudioDecodedByteCount > 0), no media errors; player-measured RMS −55.6 dBFS in the first 0.8 s (fade-in), −31.2 dBFS over 30–33 s (a sparse passage), −41.8 dBFS in the last 0.6 s (fade-out); credit text rendered under the video, in the footer and in "What is real".

### Limitations
- Loudness is measured as RMS/peak dBFS (no LUFS meter available locally); −23 dBFS RMS is roughly broadcast-reference level — calm, quieter than typical social video.
- Audio playback on a real phone was not tested (mobile emulation only).
- Re-uploads to platforms with automated content matching may be flagged; the credit in `docs/music-license.md` is the basis for disputes.

## Release state
- Owner approved commit + push to `main` after manual review (2026-09-27); committed and pushed to `origin/main`.
- **Not done, needs separate approval:** publishing/deploying `site/`, recording the narration (script in `docs/video-narration-script.md`), a genuine LLM demo run.
