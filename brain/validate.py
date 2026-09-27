"""Quality checks for a wiki state (on disk, or an in-memory candidate before apply)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .pages import ID_RE, PAGE_TYPES, REQUIRED_FIELDS, STATUSES, Page, normalise_title, page_relpath, render_index
from .workspace import Workspace, sha256_file

FORBIDDEN_CONTENT = ("<script", "javascript:")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "stats": self.stats}


def check_pages(pages: dict[str, Page], raw_root: Path | None = None) -> Report:
    r = Report()
    titles: dict[str, str] = {}
    inbound: dict[str, int] = {pid: 0 for pid in pages}
    link_count = 0

    for pid, page in sorted(pages.items()):
        where = page.path or pid
        missing = [f for f in REQUIRED_FIELDS if f not in page.meta or page.meta[f] in ("", None)]
        if missing:
            r.errors.append(f"{where}: missing required field(s): {', '.join(missing)}")
        if not ID_RE.match(pid):
            r.errors.append(f"{where}: invalid id {pid!r}")
        if page.type not in PAGE_TYPES:
            r.errors.append(f"{where}: type must be one of {PAGE_TYPES}, got {page.type!r}")
        elif page.path and page.path != page_relpath(pid, page.type):
            r.errors.append(f"{where}: expected at {page_relpath(pid, page.type)} (id/type/file mismatch)")
        if page.type == "source" and not pid.startswith("src-"):
            r.errors.append(f"{where}: source page ids must start with 'src-'")
        if page.type == "concept" and pid.startswith("src-"):
            r.errors.append(f"{where}: concept page ids must not start with 'src-'")
        if page.meta.get("status") not in STATUSES:
            r.errors.append(f"{where}: status must be one of {STATUSES}")
        elif page.meta.get("status") == "needs-review":
            r.warnings.append(f"{pid}: status is needs-review")

        norm = normalise_title(page.title)
        if norm in titles:
            r.errors.append(f"{where}: duplicate title (same as {titles[norm]})")
        titles.setdefault(norm, pid)

        lowered = page.body.lower()
        for bad in FORBIDDEN_CONTENT:
            if bad in lowered:
                r.errors.append(f"{where}: forbidden content {bad!r}")

        for src in page.sources:
            target = pages.get(src)
            if target is None:
                r.errors.append(f"{where}: cites unknown source {src!r}")
            elif target.type != "source":
                r.errors.append(f"{where}: 'sources' entry {src!r} is not a source page")
        if page.type == "concept" and not page.sources:
            r.errors.append(f"{where}: concept pages must cite at least one source")

        for link in page.links():
            link_count += 1
            if link not in pages:
                r.errors.append(f"{where}: broken link [[{link}]]")
            elif link != pid:
                inbound[link] += 1

        if page.type == "source":
            raw_path, raw_sha = page.meta.get("raw_path"), page.meta.get("raw_sha256")
            if not raw_path or not raw_sha:
                r.errors.append(f"{where}: source page needs raw_path and raw_sha256")
            elif raw_root is not None:
                raw_file = raw_root / str(raw_path)
                if not str(raw_path).startswith("raw/") or not raw_file.is_file():
                    r.errors.append(f"{where}: raw file {raw_path} not found")
                elif sha256_file(raw_file) != raw_sha:
                    r.errors.append(f"{where}: raw file {raw_path} changed since ingest (sha256 mismatch)")

    for pid, count in sorted(inbound.items()):
        if count == 0 and pages[pid].type == "concept":
            r.warnings.append(f"{pid}: no inbound links (orphan)")

    r.stats = {
        "pages": len(pages),
        "concepts": sum(p.type == "concept" for p in pages.values()),
        "sources": sum(p.type == "source" for p in pages.values()),
        "links": link_count,
        "needs_review": sum(p.meta.get("status") == "needs-review" for p in pages.values()),
    }
    return r


def validate_workspace(ws: Workspace) -> Report:
    try:
        pages = ws.load_pages()
    except ValueError as exc:  # parse errors and duplicate ids
        return Report(errors=[str(exc)])
    report = check_pages(pages, raw_root=ws.root)
    index = ws.wiki_dir / "index.md"
    if not index.exists():
        report.errors.append("wiki/index.md is missing")
    elif index.read_text(encoding="utf-8").replace("\r\n", "\n") != render_index(pages):
        report.errors.append("wiki/index.md is out of date with the pages (run: python -m brain reindex)")
    if not (ws.wiki_dir / "log.md").exists():
        report.errors.append("wiki/log.md is missing")
    return report
