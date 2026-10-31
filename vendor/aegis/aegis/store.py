"""A tiny append-friendly JSONL record store shared by the agent's data tools.

Records are plain dicts with at least an ``id`` and ``created`` timestamp. The
store is deliberately simple and dependency-free: it reads the whole file into
memory (these collections are small and personal), and rewrites on mutation.

Concurrency note: this is a single-user tool. For multi-process safety the
:meth:`add` path appends a single line, which is atomic enough on local
filesystems for our purposes.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def new_id(prefix: str) -> str:
    """A short, sortable, collision-resistant id like ``fnd-18f3a2b7c1``."""
    return f"{prefix}-{int(time.time() * 1000):x}{secrets.token_hex(2)}"


class JsonlStore:
    def __init__(self, path: str, prefix: str = "rec"):
        self.path = Path(os.path.expanduser(path))
        self.prefix = prefix
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    # -- io -------------------------------------------------------------
    def _read(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        out: List[Dict[str, Any]] = []
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return out

    def _rewrite(self, records: List[Dict[str, Any]]) -> None:
        try:
            with self.path.open("w", encoding="utf-8") as fh:
                for rec in records:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _append(self, record: Dict[str, Any]) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # -- api ------------------------------------------------------------
    def add(self, record: Dict[str, Any], *, id_prefix: Optional[str] = None) -> Dict[str, Any]:
        rec = dict(record)
        rec.setdefault("id", new_id(id_prefix or self.prefix))
        rec.setdefault("created", time.time())
        self._append(rec)
        return rec

    def all(self) -> List[Dict[str, Any]]:
        return self._read()

    def get(self, rec_id: str) -> Optional[Dict[str, Any]]:
        for rec in self._read():
            if rec.get("id") == rec_id:
                return rec
        return None

    def update(self, rec_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        records = self._read()
        found = None
        for rec in records:
            if rec.get("id") == rec_id:
                rec.update(fields)
                rec["updated"] = time.time()
                found = rec
                break
        if found is not None:
            self._rewrite(records)
        return found

    def delete(self, rec_id: str) -> bool:
        records = self._read()
        kept = [r for r in records if r.get("id") != rec_id]
        if len(kept) == len(records):
            return False
        self._rewrite(kept)
        return True

    def clear(self) -> int:
        n = len(self._read())
        self._rewrite([])
        return n

    def count(self) -> int:
        return len(self._read())

    def filter(self, predicate: Callable[[Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
        return [r for r in self._read() if predicate(r)]
