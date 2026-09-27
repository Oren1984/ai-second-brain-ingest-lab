"""Command line: python -m brain <command> [--workspace PATH]"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .ingest import IngestError, Run, add_source, apply_run, ingest, list_runs, record_review
from .providers import ProviderError, get_provider
from .validate import validate_workspace
from .workspace import Workspace, WorkspaceError, init_workspace

BANNER = {
    "mock": "[MOCK MODE] deterministic hand-authored fixture — no LLM is called",
    "llm": "[LLM MODE] genuine model call via the Anthropic API",
}


def _ws(args) -> Workspace:
    ws = Workspace(args.workspace)
    ws.require()
    return ws


def cmd_init(args):
    ws = init_workspace(args.path)
    print(f"created workspace {ws.root}\n  raw/  wiki/concepts/  wiki/sources/  wiki/index.md  wiki/log.md  proposals/  runs/")


def cmd_add(args):
    ws = _ws(args)
    dest = add_source(ws, args.file)
    print(f"raw source ready: {ws.rel(dest)}")


def cmd_ingest(args):
    ws = _ws(args)
    provider = get_provider(args.mode, model=args.model)
    print(BANNER[args.mode])
    result = ingest(ws, args.source, provider)
    print(f"{result.status}: {result.message}")
    if result.status == "proposed":
        print(f"\nNext: python -m brain show {result.run_id}    (read the proposal and diffs)")
        print(f"      python -m brain review {result.run_id}  (approve / reject / edit each change)")
    return 1 if result.status == "failed" else 0


def cmd_show(args):
    ws = _ws(args)
    run = Run.load(ws, args.run_id)
    path = ws.root / run.dir / "proposal.md"
    if not path.is_file():
        print(f"run {args.run_id} has no proposal (status {run.data['status']}): {run.data.get('error')}")
        return 1
    print(path.read_text(encoding="utf-8"))


def _interactive_decisions(ws: Workspace, run: Run) -> dict:
    decisions = {}
    print(BANNER[run.data["mode"]])
    p = run.data["proposal"]
    print(f"\nInterpretation: {p['interpretation']}\n")
    for note in p["security_notes"] + run.data.get("security_flags", []):
        print(f"  security: {note}")
    for ch in p["changes"]:
        staged = f"{run.dir}/pages/{ch['path']}"
        print(f"\n=== {ch['change_id']}: {ch['action']} {ch['page_id']} ===\nRationale: {ch['rationale']}\n")
        print(ch["diff"])
        while True:
            answer = input(f"{ch['change_id']} [a]pprove / [r]eject / [e]dit staged file then approve? ").strip().lower()
            if answer in ("a", "approve"):
                decisions[ch["change_id"]] = {"decision": "approve"}
            elif answer in ("r", "reject"):
                decisions[ch["change_id"]] = {"decision": "reject", "note": input("  reason (optional): ").strip()}
            elif answer in ("e", "edit"):
                print(f"  Edit this file in your editor, save, then press Enter:\n  {ws.root / staged}")
                input()
                decisions[ch["change_id"]] = {"decision": "approve", "note": "edited by reviewer"}
            else:
                continue
            break
    return decisions


def cmd_review(args):
    ws = _ws(args)
    run = Run.load(ws, args.run_id)
    if run.data["status"] != "proposed":
        print(f"run {args.run_id} is {run.data['status']}; nothing to review")
        return 1
    if args.decisions:
        with open(args.decisions, encoding="utf-8") as fh:
            spec = json.load(fh)
        decisions, reviewer = spec["decisions"], spec.get("reviewer", "decisions file")
    elif args.approve_all or args.reject_all:
        verdict = "approve" if args.approve_all else "reject"
        decisions = {c["change_id"]: {"decision": verdict, "note": args.note or ""} for c in run.data["proposal"]["changes"]}
        reviewer = f"{os.environ.get('USERNAME') or os.environ.get('USER') or 'reviewer'} (--{verdict}-all)"
    else:
        decisions = _interactive_decisions(ws, run)
        reviewer = f"{os.environ.get('USERNAME') or os.environ.get('USER') or 'reviewer'} (interactive)"
    run = record_review(ws, args.run_id, decisions, reviewer)
    for cid, d in run.data["review"]["decisions"].items():
        print(f"  {cid}: {d['decision']}" + (f" — {d['note']}" if d["note"] else ""))
    print(f"\nreview recorded. Next: python -m brain apply {args.run_id}")


def cmd_apply(args):
    ws = _ws(args)
    result = apply_run(ws, args.run_id)
    print(f"{result.status}: {result.message}")
    run = Run.load(ws, args.run_id)
    if run.data.get("apply", {}).get("validation"):
        v = run.data["apply"]["validation"]
        for w in v["warnings"]:
            print(f"  warning: {w}")
        for e in v["errors"]:
            print(f"  error: {e}")


def cmd_validate(args):
    report = validate_workspace(_ws(args))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        s = report.stats
        print(f"validation {'PASSED' if report.ok else 'FAILED'}: {s.get('pages', 0)} pages "
              f"({s.get('concepts', 0)} concepts, {s.get('sources', 0)} sources), {s.get('links', 0)} links")
        for e in report.errors:
            print(f"  error:   {e}")
        for w in report.warnings:
            print(f"  warning: {w}")
    return 0 if report.ok else 1


def cmd_status(args):
    runs = list_runs(_ws(args))
    if not runs:
        print("no runs yet")
    for r in runs:
        print(f"{r['run_id']}  {r['mode']:<4}  {r['status']:<9}  {r['source']['path']}"
              + (f"  error: {r['error']}" if r.get("error") else ""))


def cmd_reindex(args):
    ws = _ws(args)
    ws.rebuild_index()
    print("wiki/index.md regenerated")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain", description="Human-guided ingest into a Markdown second brain.")
    parser.add_argument("--workspace", "-w", default=os.environ.get("BRAIN_WORKSPACE", "workspace"),
                        help="workspace directory (default: $BRAIN_WORKSPACE or ./workspace)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create an empty workspace")
    p.add_argument("path")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add", help="copy a file into raw/ (never overwrites)")
    p.add_argument("file")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("ingest", help="read a raw source and stage a proposal (writes nothing to wiki/)")
    p.add_argument("source", help="path to a file in the workspace raw/ folder")
    p.add_argument("--mode", choices=["mock", "llm"], required=True)
    p.add_argument("--model", help="LLM model id (default: $BRAIN_LLM_MODEL or claude-opus-5)")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("show", help="print a staged proposal with diffs")
    p.add_argument("run_id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("review", help="record approve/reject/edit decisions for each change")
    p.add_argument("run_id")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--decisions", help="JSON file with per-change decisions (non-interactive)")
    g.add_argument("--approve-all", action="store_true")
    g.add_argument("--reject-all", action="store_true")
    p.add_argument("--note", help="note recorded with --approve-all/--reject-all")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("apply", help="write approved changes, rebuild index, append log, validate")
    p.add_argument("run_id")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("validate", help="check links, sources, required fields, duplicates, index")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    sub.add_parser("status", help="list runs").set_defaults(func=cmd_status)
    sub.add_parser("reindex", help="regenerate wiki/index.md from pages").set_defaults(func=cmd_reindex)
    return parser


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except (IngestError, ProviderError, WorkspaceError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
