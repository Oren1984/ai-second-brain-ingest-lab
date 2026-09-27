"""Demo driver for the sample scenario.

  python tools/demo.py run      reset ./demo-workspace, run the mock scenario via the real CLI,
                                capture a transcript, export site data
  python tools/demo.py export   regenerate site/data/demo-run.js from ./demo-workspace
  python tools/demo.py verify   check the recorded run, the wiki, and the site data agree

Effects of `run` (and nothing else is touched):
  - deletes and recreates ./demo-workspace — only if it carries the .demo-workspace marker
    and contains no runs other than the ones this script recorded
  - overwrites site/data/demo-run.js
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from brain.ingest import _prepare_page  # noqa: E402
from brain.pages import parse_page, render_page  # noqa: E402
from brain.validate import check_pages, validate_workspace  # noqa: E402
from brain.workspace import Workspace, sha256_file  # noqa: E402

DEMO = REPO / "demo-workspace"
MARKER = DEMO / ".demo-workspace"
SCENARIO = REPO / "examples" / "scenario"
SOURCE_NAME = "sample-incident-review-stale-policy.md"
SITE_DATA = REPO / "site" / "data" / "demo-run.js"
WS_ARG = "demo-workspace"


def fail(msg: str) -> None:
    print(f"demo: {msg}", file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------------- reset
def safe_reset() -> None:
    if DEMO.exists():
        if not MARKER.is_file():
            fail(f"{DEMO} exists but has no .demo-workspace marker. It may be your own data; "
                 "refusing to delete it. Move or rename it and run again.")
        marker = json.loads(MARKER.read_text(encoding="utf-8"))
        known = set(marker.get("run_ids", []))
        found = {p.stem for p in (DEMO / "runs").glob("*.json")}
        extra = sorted(found - known)
        if extra:
            fail(f"{DEMO} contains runs this script did not create ({', '.join(extra)}). "
                 "Refusing to delete them. Move the folder aside and run again.")
        print(f"demo: resetting {DEMO.name}/ (marker present; only demo runs {sorted(known) or '[]'} inside)")
        shutil.rmtree(DEMO)
    shutil.copytree(SCENARIO / "seed", DEMO)
    (DEMO / "proposals").mkdir()
    (DEMO / "runs").mkdir()
    write_marker([])


def write_marker(run_ids: list[str]) -> None:
    MARKER.write_text(json.dumps({
        "created_by": "tools/demo.py run",
        "purpose": "Disposable demo workspace. `tools/demo.py run` may delete and recreate it.",
        "run_ids": run_ids,
    }, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- run
def cli(transcript: list, *args: str, label: str, expect: int = 0) -> str:
    cmd = [sys.executable, "-m", "brain", "-w", WS_ARG, *args]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    output = (proc.stdout + proc.stderr).rstrip("\n")
    shown = "python -m brain -w demo-workspace " + " ".join(args)
    transcript.append({"label": label, "command": shown, "exit_code": proc.returncode, "output": output})
    print(f"\n$ {shown}\n{output}")
    if proc.returncode != expect:
        fail(f"step '{label}' exited {proc.returncode} (expected {expect})")
    return output


def cmd_run() -> None:
    safe_reset()
    t: list = []
    cli(t, "add", f"examples/scenario/incoming/{SOURCE_NAME}", label="Add the new source to raw/")
    cli(t, "validate", label="Validate the initial wiki")
    out = cli(t, "ingest", f"raw/{SOURCE_NAME}", "--mode", "mock", label="Ingest: build context, get proposal, stage it")
    run_id = next(line.split("proposals/")[1].split("/")[0] for line in out.splitlines() if "proposals/" in line)
    write_marker([run_id])
    cli(t, "show", run_id, label="Human reads the proposal and diffs")
    cli(t, "review", run_id, "--decisions", "examples/scenario/demo_decisions.json",
        label="Human decisions (pre-recorded decisions file)")
    cli(t, "apply", run_id, label="Apply approved changes, index, log")
    cli(t, "validate", label="Validate the updated wiki")
    cli(t, "ingest", f"raw/{SOURCE_NAME}", "--mode", "mock", label="Repeat ingest of the unchanged source")
    cli(t, "status", label="Run history")
    (DEMO / "transcript.json").write_text(json.dumps(t, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    cmd_export()
    print(f"\ndemo: recorded mock run {run_id}\ndemo: wrote {SITE_DATA.relative_to(REPO)}")


# ------------------------------------------------------------------ export
def graph(pages: dict) -> dict:
    nodes = [{"id": p.id, "title": p.title, "type": p.type, "status": p.meta.get("status")}
             for p in sorted(pages.values(), key=lambda p: p.id)]
    edges = sorted({(p.id, t) for p in pages.values() for t in p.links() if t in pages and t != p.id})
    return {"nodes": nodes, "edges": [list(e) for e in edges]}


def page_payload(pages: dict, ws_root: Path | None = None, texts: dict | None = None) -> dict:
    out = {}
    for pid, p in sorted(pages.items()):
        text = texts[pid] if texts else (ws_root / p.path).read_text(encoding="utf-8")
        out[pid] = {"path": p.path, "title": p.title, "type": p.type, "status": p.meta.get("status"),
                    "summary": p.meta.get("summary"), "text": text}
    return out


def load_recorded_run() -> tuple[Workspace, dict]:
    ws = Workspace(DEMO)
    runs = sorted((DEMO / "runs").glob("*.json"))
    if len(runs) != 1:
        fail(f"expected exactly one recorded run in demo-workspace/runs, found {len(runs)}; run: python tools/demo.py run")
    return ws, json.loads(runs[0].read_text(encoding="utf-8"))


def build_export() -> dict:
    ws, run = load_recorded_run()
    rid = run["run_id"]
    pdir = DEMO / "proposals" / rid
    after_pages = ws.load_pages()
    after_texts = {pid: (DEMO / p.path).read_text(encoding="utf-8") for pid, p in after_pages.items()}

    # Reconstruct the pre-apply wiki from the saved before/ copies.
    before_texts = dict(after_texts)
    for ch in run["apply"]["applied"]:
        c = next(x for x in run["proposal"]["changes"] if x["change_id"] == ch["change_id"])
        saved = pdir / "before" / c["path"]
        if saved.is_file():
            before_texts[c["page_id"]] = saved.read_text(encoding="utf-8")
        else:
            before_texts.pop(c["page_id"])
    before_pages = {pid: parse_page(txt, after_pages[pid].path) for pid, txt in before_texts.items()}

    # What the provider proposed (engine-normalised) vs what was finally written.
    response = json.loads((pdir / "response.json").read_text(encoding="utf-8"))
    src = run["source"]
    proposed_texts, proposed_pages = {}, dict(before_pages)
    for i, raw in enumerate(response["changes"], 1):
        page = _prepare_page(raw["content"], raw, rid, src["path"], src["sha256"])
        proposed_texts[f"c{i}"] = render_page(page)
        proposed_pages[page.id] = page

    decisions = run["review"]["decisions"]
    applied = {a["change_id"]: a for a in run["apply"]["applied"]}
    changes = []
    for c in run["proposal"]["changes"]:
        cid = c["change_id"]
        changes.append({
            **{k: c[k] for k in ("change_id", "action", "page_id", "page_type", "path", "rationale", "diff")},
            "decision": decisions[cid]["decision"],
            "note": decisions[cid]["note"],
            "edited_by_reviewer": applied.get(cid, {}).get("edited_by_reviewer", False),
            "proposed_text": proposed_texts[cid],
            "final_text": after_texts.get(c["page_id"]) if cid in applied else None,
        })

    g_before, g_after, g_prop = graph(before_pages), graph(after_pages), graph(proposed_pages)
    after_edges = {tuple(e) for e in g_after["edges"]}
    before_edges = {tuple(e) for e in g_before["edges"]}
    touched = {c["page_id"]: ("created" if c["action"] == "create" else "updated") for c in changes if c["change_id"] in applied}
    rejected_pages = [c["page_id"] for c in changes if c["decision"] == "reject"]

    before_report = check_pages(before_pages, raw_root=DEMO)
    final_report = validate_workspace(ws)
    log_text = (DEMO / "wiki" / "log.md").read_text(encoding="utf-8")
    transcript = json.loads((DEMO / "transcript.json").read_text(encoding="utf-8"))
    artifact_paths = sorted(
        [p for p in DEMO.rglob("*") if p.is_file() and p.name != ".demo-workspace"],
        key=lambda p: p.as_posix(),
    )
    return {
        "schema": "demo-run/1",
        "honesty": {
            "mode": run["mode"],
            "statement": ("Recorded MOCK run: the proposal came from a hand-authored fixture, not from an LLM. "
                          "It passed through the same parser, policy checks, staging, review, apply and validation "
                          "code a genuine LLM run uses. Reviewer decisions were supplied from a pre-recorded "
                          "decisions file."),
            "reviewer": run["review"]["reviewer"],
        },
        "run": run,
        "source": {"path": src["path"], "sha256": src["sha256"],
                   "text": (DEMO / src["path"]).read_text(encoding="utf-8"),
                   "flags": run["security_flags"]},
        "proposal": run["proposal"],
        "changes": changes,
        "before": {"pages": page_payload(before_pages, texts=before_texts),
                   "validation": before_report.to_dict(),
                   "index": (pdir / "before" / "wiki" / "index.md").read_text(encoding="utf-8")},
        "after": {"pages": page_payload(after_pages, texts=after_texts),
                  "validation": final_report.to_dict(),
                  "index": (DEMO / "wiki" / "index.md").read_text(encoding="utf-8"),
                  "log": log_text},
        "graph": {
            "before": g_before,
            "after": g_after,
            "added_edges": sorted([list(e) for e in after_edges - before_edges]),
            "rejected_edges": sorted([list(e) for e in {tuple(e) for e in g_prop["edges"]} - after_edges]),
            "touched": touched,
            "rejected_pages": rejected_pages,
        },
        "transcript": transcript,
        "artifacts": {p.relative_to(REPO).as_posix(): sha256_file(p) for p in artifact_paths},
    }


def cmd_export() -> None:
    data = build_export()
    SITE_DATA.parent.mkdir(parents=True, exist_ok=True)
    SITE_DATA.write_text(
        "// GENERATED by `python tools/demo.py export` from demo-workspace/. Do not edit by hand.\n"
        "window.DEMO_RUN = " + json.dumps(data, indent=1, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )


def probe_streams(path: Path) -> list[str] | None:
    """Stream codecs via `ffmpeg -i` if an ffmpeg is available; None when it is not."""
    candidates = [os.environ.get("FFMPEG"), shutil.which("ffmpeg")]
    candidates += sorted(glob.glob(str(Path.home() / "AppData/Local/ms-playwright/ffmpeg-*/ffmpeg-*.exe")))
    candidates += sorted(glob.glob(str(Path.home() / ".cache/ms-playwright/ffmpeg-*/ffmpeg-*")))
    exe = next((c for c in candidates if c), None)
    if not exe:
        return None
    out = subprocess.run([exe, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    return [f"{kind.lower()}:{codec}" for kind, codec in re.findall(r"Stream #0:\d+.*?: (Video|Audio): (\w+)", out)]


def read_site_data() -> dict:
    text = SITE_DATA.read_text(encoding="utf-8")
    start = text.index("window.DEMO_RUN = ") + len("window.DEMO_RUN = ")
    return json.loads(text[start:].rstrip().rstrip(";"))


# ------------------------------------------------------------------ verify
def cmd_verify() -> None:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    ws, run = load_recorded_run()
    report = validate_workspace(ws)
    check("wiki validates", report.ok, "; ".join(report.errors))
    check("run is applied", run["status"] == "applied", run["status"])
    check("run is labelled mock", run["mode"] == "mock" and "-mock-" in run["run_id"])

    incoming = SCENARIO / "incoming" / SOURCE_NAME
    raw = DEMO / "raw" / SOURCE_NAME
    check("raw source byte-identical to sample", raw.read_bytes() == incoming.read_bytes())
    check("raw hash matches run record", sha256_file(raw) == run["source"]["sha256"])
    for seed_raw in (SCENARIO / "seed" / "raw").glob("*"):
        check(f"seed raw unchanged: {seed_raw.name}", (DEMO / "raw" / seed_raw.name).read_bytes() == seed_raw.read_bytes())

    pages = ws.load_pages()
    fe = pages["faithfulness-evaluation"]
    check("existing page updated by this run", fe.meta.get("updated") == run["run_id"])
    check("rejected change not applied", pages["llm-as-judge"].meta.get("updated") == "seed")
    check("source page created", "src-sample-incident-review-stale-policy" in pages)
    check("no duplicate source pages", sum(p.type == "source" for p in pages.values()) == 2)
    log = (DEMO / "wiki" / "log.md").read_text(encoding="utf-8")
    check("exactly one log entry for the run", log.count(run["run_id"]) == 1)
    transcript = json.loads((DEMO / "transcript.json").read_text(encoding="utf-8"))
    check("repeat ingest was a no-op", any(s["output"].startswith("[MOCK MODE]") and "noop:" in s["output"]
                                           for s in transcript if s["label"].startswith("Repeat")))

    if SITE_DATA.is_file():
        site = read_site_data()
        fresh = build_export()
        check("site data run id matches", site["run"]["run_id"] == run["run_id"])
        check("site data matches artifacts", site == fresh,
              "site/data/demo-run.js is stale; run: python tools/demo.py export")
        check("site data labelled mock", site["honesty"]["mode"] == "mock")
    else:
        check("site data present", False, "missing site/data/demo-run.js")

    video = REPO / "site" / "media" / "demo-replay.webm"
    meta = REPO / "site" / "media" / "demo-replay.json"
    if video.is_file() and meta.is_file():
        m = json.loads(meta.read_text(encoding="utf-8"))
        check("video rendered from this run", m.get("run_id") == run["run_id"], str(m.get("run_id")))
        check("video file matches its manifest", sha256_file(video) == m.get("sha256"))
        check("video rendered from current site data", m.get("source_data_sha256") == sha256_file(SITE_DATA),
              "site data changed after the video was rendered; run: python tools/make_replay_video.py")
        cap_js = REPO / "site" / "data" / "replay-captions.js"
        vtt = REPO / "site" / "media" / "demo-replay.en.vtt"
        if cap_js.is_file() and vtt.is_file():
            cap_text = cap_js.read_text(encoding="utf-8")
            caps = json.loads(cap_text[cap_text.index("= ") + 2:].rstrip().rstrip(";"))
            check("captions belong to this run", caps.get("run_id") == run["run_id"])
            check("captions match the video manifest", len(caps["cues"]) == m.get("captions", {}).get("cues")
                  and all(c["text"] in vtt.read_text(encoding="utf-8") for c in caps["cues"]))
        else:
            check("captions present", False, "run: python tools/make_replay_video.py")
        audio = m.get("audio")
        if audio:
            track = audio["track"]
            streams = probe_streams(video)
            if streams is not None:
                check("video has vp8 video + opus audio streams", streams == ["video:vp8", "audio:opus"], str(streams))
            check("music level is background (body RMS <= -18 dBFS, peak <= -3 dBFS)",
                  audio["mix"]["mixed_body"]["rms_dbfs"] <= -18 and audio["mix"]["mixed_body"]["peak_dbfs"] <= -3)
            check("music fades in and out", audio["mix"]["edges"]["first_100ms"] < -40 and audio["mix"]["edges"]["last_100ms"] < -40)
            credit_ok = all(track["title"] in (REPO / f).read_text(encoding="utf-8") and track["license_url"] in (REPO / f).read_text(encoding="utf-8")
                            for f in ("README.md", "docs/music-license.md"))
            check("music credited in README and docs/music-license.md", credit_ok)
            check("site shows music credit from caption data", "audio" in caps and caps["audio"]["license_url"] == track["license_url"])
        else:
            check("soundtrack (optional)", True, "")
    else:
        check("replay video present", False, "run: python tools/make_replay_video.py")

    width = max(len(n) for n, _, _ in checks)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {'' if ok else detail}")
    failed = [n for n, ok, _ in checks if not ok]
    print(f"\nverify_demo: {len(checks) - len(failed)}/{len(checks)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    commands = {"run": cmd_run, "export": cmd_export, "verify": cmd_verify}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        print(__doc__)
        sys.exit(2)
    commands[sys.argv[1]]()
