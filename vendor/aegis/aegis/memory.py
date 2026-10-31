"""Conversation memory.

Keeps a bounded in-memory transcript and persists it to disk so a session can
be resumed. Also exposes a lightweight JSONL store for saved "lessons" the
operator wants the copilot to remember across sessions.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .brain import Message


@dataclass
class Turn:
    role: str
    content: str
    ts: float


class Memory:
    def __init__(self, history_file: str, max_turns: int = 40):
        self.history_file = Path(history_file).expanduser()
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self.max_turns = max_turns
        self.turns: List[Turn] = []

    def add(self, role: str, content: str) -> None:
        self.turns.append(Turn(role, content, time.time()))
        # keep the tail bounded; never drop the system prompt (caller manages it)
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
        self._append_disk(role, content)

    def messages(self, system_prompt: str) -> List[Message]:
        msgs = [Message("system", system_prompt)]
        for turn in self.turns:
            msgs.append(Message(turn.role, turn.content))
        return msgs

    def clear(self) -> None:
        self.turns = []
        try:
            if self.history_file.is_file():
                self.history_file.write_text("", encoding="utf-8")
        except OSError:
            pass

    def _append_disk(self, role: str, content: str) -> None:
        try:
            with self.history_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": time.time(), "role": role, "content": content}) + "\n")
        except OSError:
            pass

    def load(self) -> None:
        if not self.history_file.is_file():
            return
        try:
            for line in self.history_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                self.turns.append(Turn(obj.get("role", "user"), obj.get("content", ""),
                                       obj.get("ts", 0.0)))
        except (OSError, json.JSONDecodeError):
            pass


class LessonStore:
    """Persistent notes the operator asks Aegis to remember."""

    def __init__(self, path: str):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, text: str, tags: Optional[List[str]] = None) -> None:
        entry = {"ts": time.time(), "text": text, "tags": tags or []}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

    def all(self) -> List[Dict]:
        if not self.path.is_file():
            return []
        out = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            pass
        return out

    def search(self, query: str) -> List[Dict]:
        q = query.lower()
        return [e for e in self.all()
                if q in e.get("text", "").lower()
                or any(q in t.lower() for t in e.get("tags", []))]
