"""Workspace layout, hashing and the single guarded write path."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .pages import Page, PageError, parse_page, render_index

# The only workspace-relative locations the engine ever writes to.
WRITABLE_PREFIXES = ("wiki/concepts/", "wiki/sources/", "proposals/", "runs/")
WRITABLE_FILES = ("wiki/index.md", "wiki/log.md")

LOG_HEADER = (
    "# Log\n\n"
    "Append-only record of applied ingests. Written by the engine; one entry per applied run.\n"
)

SECRET_RE = re.compile(r"(sk-ant-[A-Za-z0-9_\-]{6})[A-Za-z0-9_\-]*")


class WorkspaceError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def redact(text: str) -> str:
    """Remove anything that looks like an API key before it reaches logs."""
    text = SECRET_RE.sub(r"\1…[redacted]", text)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key and len(key) > 8:
        text = text.replace(key, "[redacted]")
    return text


class Workspace:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()

    # ---- layout -------------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def wiki_dir(self) -> Path:
        return self.root / "wiki"

    def exists(self) -> bool:
        return (self.wiki_dir / "concepts").is_dir() and self.raw_dir.is_dir()

    def require(self) -> None:
        if not self.exists():
            raise WorkspaceError(
                f"{self.root} is not a brain workspace (expected raw/ and wiki/concepts/). "
                "Create one with: python -m brain init <path>"
            )

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    # ---- guarded writes ----------------------------------------------
    def _check_writable(self, relpath: str) -> Path:
        target = (self.root / relpath).resolve()
        try:
            rel = target.relative_to(self.root).as_posix()
        except ValueError:
            raise WorkspaceError(f"refusing to write outside the workspace: {relpath}") from None
        if not (rel in WRITABLE_FILES or rel.startswith(WRITABLE_PREFIXES)):
            raise WorkspaceError(f"refusing to write to non-writable path: {rel}")
        return target

    def write_text(self, relpath: str, text: str) -> None:
        target = self._check_writable(relpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(text.encode("utf-8"))
        os.replace(tmp, target)

    def write_json(self, relpath: str, data) -> None:
        self.write_text(relpath, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def read_json(self, relpath: str):
        return json.loads((self.root / relpath).read_text(encoding="utf-8"))

    # ---- wiki state ---------------------------------------------------
    def load_pages(self) -> dict[str, Page]:
        pages: dict[str, Page] = {}
        for folder in ("concepts", "sources"):
            for path in sorted((self.wiki_dir / folder).glob("*.md")):
                page = parse_page(path.read_text(encoding="utf-8"), self.rel(path))
                if page.id in pages:
                    raise PageError(f"duplicate page id {page.id!r} in {page.path} and {pages[page.id].path}")
                pages[page.id] = page
        return pages

    def wiki_snapshot(self) -> dict[str, str]:
        """sha256 of every file under wiki/ — used to prove 'unchanged'."""
        return {
            self.rel(p): sha256_file(p)
            for p in sorted(self.wiki_dir.rglob("*"))
            if p.is_file()
        }

    def raw_snapshot(self) -> dict[str, str]:
        return {self.rel(p): sha256_file(p) for p in sorted(self.raw_dir.rglob("*")) if p.is_file()}

    def rebuild_index(self, pages: dict[str, Page] | None = None) -> None:
        self.write_text("wiki/index.md", render_index(pages if pages is not None else self.load_pages()))

    def ensure_log(self) -> None:
        if not (self.wiki_dir / "log.md").exists():
            self.write_text("wiki/log.md", LOG_HEADER)


def init_workspace(root: Path | str) -> Workspace:
    ws = Workspace(root)
    if ws.root.exists() and any(ws.root.iterdir()):
        raise WorkspaceError(f"{ws.root} exists and is not empty; choose an empty or new directory")
    for sub in ("raw", "wiki/concepts", "wiki/sources", "proposals", "runs"):
        (ws.root / sub).mkdir(parents=True, exist_ok=True)
    ws.ensure_log()
    ws.rebuild_index({})
    return ws
