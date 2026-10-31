"""Append-only audit log with a tamper-evident hash chain.

Every record includes the hash of the previous record, so any edit, deletion or
reordering of history is detectable with :meth:`AuditLog.verify`. The chain is a
plain SHA-256 link (not a blockchain) — it proves *internal consistency*, not
authenticity: an attacker who can rewrite the whole file can also recompute the
chain. For real integrity, copy the periodic head hash somewhere else.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GENESIS = "0" * 64


def _canonical(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(prev: str, payload: Dict[str, Any]) -> str:
    return hashlib.sha256((prev + "|" + _canonical(payload)).encode("utf-8")).hexdigest()


class AuditLog:
    """Writes one JSON object per line, each linked to the previous record."""

    def __init__(self, path: str):
        self.path = Path(os.path.expanduser(path))
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    # -- writing --------------------------------------------------------
    def _last_hash(self) -> str:
        if not self.path.exists():
            return GENESIS
        try:
            with self.path.open("rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 8192))
                tail = fh.read().decode("utf-8", errors="replace")
        except OSError:
            return GENESIS
        for line in reversed(tail.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line).get("hash", GENESIS)
            except json.JSONDecodeError:
                continue
        return GENESIS

    def record(self, **fields: Any) -> Dict[str, Any]:
        prev = self._last_hash()
        payload = {"ts": time.time(), "prev": prev, **fields}
        entry = {**payload, "hash": _hash(prev, payload)}
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return entry

    # -- reading --------------------------------------------------------
    def read_all(self) -> List[Dict[str, Any]]:
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
                        out.append({"__corrupt__": True, "raw": line[:200]})
        except OSError:
            return []
        return out

    def tail(self, n: int = 20) -> List[Dict[str, Any]]:
        return self.read_all()[-n:]

    # -- integrity ------------------------------------------------------
    def verify(self) -> Tuple[bool, int, str]:
        """Return (ok, index_of_first_problem, message)."""
        prev = GENESIS
        for i, rec in enumerate(self.read_all()):
            if rec.get("__corrupt__"):
                return False, i, "corrupt JSON line"
            stored = rec.get("hash")
            payload = {k: v for k, v in rec.items() if k != "hash"}
            if payload.get("prev") != prev:
                return False, i, f"broken link at record {i} (prev mismatch)"
            if stored != _hash(prev, payload):
                return False, i, f"hash mismatch at record {i} (tampered?)"
            prev = stored
        return True, -1, f"chain intact ({self.count()} records)"

    def head(self) -> str:
        return self._last_hash()

    def count(self) -> int:
        return len(self.read_all())

    def seal(self, out_path: str) -> str:
        """Write a detached proof file containing count + head hash."""
        head = self.head()
        count = self.count()
        payload = {"count": count, "head": head, "sealed": time.time(),
                   "path": str(self.path)}
        p = Path(os.path.expanduser(out_path))
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass
        return head
