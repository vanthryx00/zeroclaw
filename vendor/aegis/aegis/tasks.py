"""Task planner: multi-step work that survives across sessions.

Tasks can be plain, or generated from a plan the model proposes. They carry a
status and priority so a long job ("harden this box", "recover this disk") has a
checklist instead of living in the conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .store import JsonlStore

STATUSES = ["todo", "doing", "blocked", "done"]
PRIORITIES = ["low", "normal", "high", "urgent"]
PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}


@dataclass
class Task:
    id: str
    title: str
    status: str = "todo"
    priority: str = "normal"
    detail: str = ""
    tags: List[str] = field(default_factory=list)
    created: float = 0.0

    @classmethod
    def from_record(cls, rec: Dict[str, Any]) -> "Task":
        return cls(
            id=rec.get("id", ""),
            title=rec.get("title", ""),
            status=rec.get("status", "todo"),
            priority=rec.get("priority", "normal"),
            detail=rec.get("detail", ""),
            tags=list(rec.get("tags", [])),
            created=rec.get("created", 0.0),
        )

    @property
    def done(self) -> bool:
        return self.status == "done"

    def box(self) -> str:
        return {"done": "[x]", "doing": "[~]", "blocked": "[!]", "todo": "[ ]"}.get(
            self.status, "[ ]")

    def line(self) -> str:
        pr = "" if self.priority == "normal" else f" ({self.priority})"
        return f"{self.box()} {self.title}{pr}"


class TaskStore(JsonlStore):
    def __init__(self, path: str):
        super().__init__(path, prefix="task")

    def add_task(self, title: str, *, status: str = "todo", priority: str = "normal",
                 detail: str = "", tags: Optional[List[str]] = None) -> Task:
        st = status if status in STATUSES else "todo"
        pr = priority if priority in PRIORITIES else "normal"
        rec = self.add({
            "title": title,
            "status": st,
            "priority": pr,
            "detail": detail,
            "tags": [t for t in (tags or []) if t],
        })
        return Task.from_record(rec)

    def add_plan(self, steps: List[str], *, tags: Optional[List[str]] = None) -> List[Task]:
        """Turn a list of step strings into an ordered todo list."""
        return [self.add_task(s, tags=tags) for s in steps if s.strip()]

    def tasks(self, *, status: Optional[str] = None) -> List[Task]:
        out = [Task.from_record(r) for r in self.all()]
        if status:
            out = [t for t in out if t.status == status]
        out.sort(key=lambda t: (t.done, -PRIORITY_RANK.get(t.priority, 1), t.created))
        return out

    def get_task(self, rec_id: str) -> Optional[Task]:
        rec = self.get(rec_id)
        return Task.from_record(rec) if rec else None

    def set_status(self, rec_id: str, status: str) -> Optional[Task]:
        if status not in STATUSES:
            return None
        rec = self.update(rec_id, status=status)
        return Task.from_record(rec) if rec else None

    def next_task(self) -> Optional[Task]:
        for t in self.tasks():
            if t.status in ("doing", "todo"):
                return t
        return None

    def progress(self) -> Dict[str, int]:
        tasks = self.tasks()
        return {
            "total": len(tasks),
            "done": sum(1 for t in tasks if t.done),
            "remaining": sum(1 for t in tasks if not t.done),
        }

    def render(self) -> str:
        tasks = self.tasks()
        if not tasks:
            return "(no tasks)"
        lines = [t.line() for t in tasks]
        p = self.progress()
        lines.append(f"\n{p['done']}/{p['total']} done")
        return "\n".join(lines)
