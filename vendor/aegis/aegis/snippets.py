"""Code snippet library — save, search, and recall snippets as you work.

Snippets are stored as JSONL under the platform data directory so they survive
across sessions and are portable between OSes. Language is auto-detected from
the filename and a few content heuristics.
"""

from __future__ import annotations

import json
import os
import random
import string
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .retrieval import BM25

# --------------------------------------------------------------------------
# Language detection
# --------------------------------------------------------------------------

EXT_LANG = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".java": "java", ".kt": "kotlin", ".swift": "swift",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".ps1": "powershell", ".psm1": "powershell",
    ".bat": "batch", ".cmd": "batch",
    ".sql": "sql", ".html": "html", ".htm": "html", ".css": "css",
    ".scss": "scss", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".ini": "ini", ".md": "markdown",
    ".dockerfile": "dockerfile", ".tf": "terraform",
    ".lua": "lua", ".pl": "perl", ".r": "r", ".jl": "julia",
}

_CONTENT_HINTS = [
    ("#!/bin/bash", "bash"), ("#!/usr/bin/env bash", "bash"),
    ("#!/usr/bin/env python", "python"), ("def ", "python"), ("import ", "python"),
    ("package main", "go"), ("func ", "go"),
    ("fn main", "rust"), ("use std::", "rust"),
    ("<?php", "php"), ("SELECT ", "sql"), ("<html", "html"),
    ("Get-ChildItem", "powershell"), ("$PSVersionTable", "powershell"),
    ("function ", "javascript"), ("const ", "javascript"), ("=>", "javascript"),
]


def detect_language(filename: str = "", code: str = "") -> str:
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in EXT_LANG:
            return EXT_LANG[ext]
        name = Path(filename).name.lower()
        if name in ("dockerfile", "makefile"):
            return name
    sample = (code or "")[:2000]
    for needle, lang in _CONTENT_HINTS:
        if needle in sample:
            return lang
    return "text"


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

@dataclass
class Snippet:
    id: str
    title: str
    language: str
    code: str
    tags: List[str] = field(default_factory=list)
    description: str = ""
    created: float = 0.0
    uses: int = 0
    source: str = ""  # e.g. "cli", "agent", "import"

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "Snippet":
        return cls(
            id=d.get("id", ""), title=d.get("title", ""),
            language=d.get("language", "text"), code=d.get("code", ""),
            tags=list(d.get("tags", [])), description=d.get("description", ""),
            created=d.get("created", 0.0), uses=d.get("uses", 0),
            source=d.get("source", ""),
        )

    def searchable_text(self) -> str:
        return " ".join([
            self.title, self.language, " ".join(self.tags),
            self.description, self.code,
        ])


def _new_id() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"snip-{suffix}"


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------

class SnippetStore:
    def __init__(self, path: str):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- persistence ---------------------------------------------------
    def _load(self) -> List[Snippet]:
        if not self.path.is_file():
            return []
        out: List[Snippet] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(Snippet.from_dict(json.loads(line)))
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
        return out

    def _rewrite(self, snippets: Sequence[Snippet]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for s in snippets:
                fh.write(json.dumps(s.to_dict()) + "\n")
        os.replace(tmp, self.path)

    def _append(self, snippet: Snippet) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(snippet.to_dict()) + "\n")

    # -- API -----------------------------------------------------------
    def save(self, title: str, code: str, *, language: Optional[str] = None,
             tags: Optional[Sequence[str]] = None, description: str = "",
             filename: str = "", source: str = "cli") -> Snippet:
        snippet = Snippet(
            id=_new_id(),
            title=title.strip() or "untitled",
            language=language or detect_language(filename, code),
            code=code,
            tags=[t.strip() for t in (tags or []) if t.strip()],
            description=description.strip(),
            created=time.time(),
            source=source,
        )
        self._append(snippet)
        return snippet

    def all(self) -> List[Snippet]:
        return self._load()

    def get(self, snippet_id: str) -> Optional[Snippet]:
        for s in self._load():
            if s.id == snippet_id:
                return s
        return None

    def delete(self, snippet_id: str) -> bool:
        snippets = self._load()
        kept = [s for s in snippets if s.id != snippet_id]
        if len(kept) == len(snippets):
            return False
        self._rewrite(kept)
        return True

    def bump(self, snippet_id: str) -> None:
        snippets = self._load()
        for s in snippets:
            if s.id == snippet_id:
                s.uses += 1
        self._rewrite(snippets)

    def search(self, query: str, *, language: Optional[str] = None,
               tag: Optional[str] = None, limit: int = 10) -> List[Snippet]:
        snippets = self._load()
        if language:
            snippets = [s for s in snippets if s.language == language]
        if tag:
            snippets = [s for s in snippets if tag in s.tags]
        if not query.strip():
            return sorted(snippets, key=lambda s: s.created, reverse=True)[:limit]

        index = BM25([(s.id, s.searchable_text()) for s in snippets])
        ranked = index.search(query, k=limit)
        by_id = {s.id: s for s in snippets}
        return [by_id[i] for i, _ in ranked if i in by_id]

    def stats(self) -> Dict:
        snippets = self._load()
        by_lang: Dict[str, int] = {}
        for s in snippets:
            by_lang[s.language] = by_lang.get(s.language, 0) + 1
        return {
            "count": len(snippets),
            "languages": dict(sorted(by_lang.items(), key=lambda kv: -kv[1])),
            "total_uses": sum(s.uses for s in snippets),
        }

    def export(self, dest_dir: str) -> List[Path]:
        """Write each snippet to a real file under *dest_dir*."""
        dest = Path(dest_dir).expanduser()
        dest.mkdir(parents=True, exist_ok=True)
        ext_for = {v: k for k, v in EXT_LANG.items()}
        written: List[Path] = []
        for s in self._load():
            ext = ext_for.get(s.language, ".txt")
            safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in s.title)[:60]
            path = dest / f"{safe_title}{ext}"
            path.write_text(s.code, encoding="utf-8")
            written.append(path)
        return written
