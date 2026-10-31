"""Sandboxed file reading and writing.

The agent can read and write files, but only inside the workspace root (plus an
explicit allowlist). This is the filesystem counterpart to the shell safety
classifier: paths are resolved and checked before anything touches disk.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


class WorkspaceError(Exception):
    """Raised when a path escapes the workspace sandbox."""


class FileWorkspace:
    def __init__(self, root: str, extra_roots: Optional[List[str]] = None,
                 max_read_bytes: int = 512_000):
        self.root = Path(root).expanduser().resolve()
        self.extra_roots = [Path(p).expanduser().resolve() for p in (extra_roots or [])]
        self.max_read_bytes = max_read_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    # -- path resolution ------------------------------------------------
    def resolve(self, path: str) -> Path:
        """Resolve *path* relative to the workspace, rejecting escapes."""
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()

        allowed = [self.root] + self.extra_roots
        for base in allowed:
            if resolved == base or base in resolved.parents:
                return resolved
        raise WorkspaceError(
            f"path '{path}' is outside the workspace ({self.root}). "
            "Writes are confined to the workspace."
        )

    # -- reads ----------------------------------------------------------
    def read(self, path: str, *, max_bytes: Optional[int] = None) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise WorkspaceError(f"not a file: {path}")
        limit = max_bytes or self.max_read_bytes
        with target.open("r", encoding="utf-8", errors="replace") as fh:
            data = fh.read(limit + 1)
        if len(data) > limit:
            data = data[:limit] + "\n...[truncated]"
        return data

    def exists(self, path: str) -> bool:
        try:
            return self.resolve(path).exists()
        except WorkspaceError:
            return False

    def list(self, subdir: str = "") -> List[str]:
        target = self.resolve(subdir) if subdir else self.root
        if not target.is_dir():
            return []
        out = []
        for entry in sorted(target.iterdir()):
            out.append(entry.name + ("/" if entry.is_dir() else ""))
        return out

    def tree(self, max_depth: int = 3) -> str:
        lines: List[str] = []

        def walk(directory: Path, prefix: str, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                entries = sorted(directory.iterdir(),
                                 key=lambda p: (p.is_file(), p.name.lower()))
            except OSError:
                return
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                lines.append(f"{prefix}{entry.name}{'/' if entry.is_dir() else ''}")
                if entry.is_dir():
                    walk(entry, prefix + "  ", depth + 1)

        walk(self.root, "", 1)
        return "\n".join(lines) or "(empty workspace)"

    # -- writes ---------------------------------------------------------
    def write(self, path: str, content: str, *, overwrite: bool = True) -> Path:
        target = self.resolve(path)
        if target.exists() and not overwrite:
            raise WorkspaceError(f"file exists: {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def append(self, path: str, content: str) -> Path:
        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(content)
        return target

    def mkdir(self, path: str) -> Path:
        target = self.resolve(path)
        target.mkdir(parents=True, exist_ok=True)
        return target
