"""Notes / journal: free-form research continuity that survives sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .store import JsonlStore


@dataclass
class Note:
    id: str
    title: str
    body: str = ""
    tags: List[str] = field(default_factory=list)
    created: float = 0.0

    @classmethod
    def from_record(cls, rec: Dict[str, Any]) -> "Note":
        return cls(
            id=rec.get("id", ""),
            title=rec.get("title", ""),
            body=rec.get("body", ""),
            tags=list(rec.get("tags", [])),
            created=rec.get("created", 0.0),
        )


class NoteStore(JsonlStore):
    def __init__(self, path: str):
        super().__init__(path, prefix="note")

    def add_note(self, title: str, body: str = "",
                 tags: Optional[List[str]] = None) -> Note:
        rec = self.add({
            "title": title,
            "body": body,
            "tags": [t for t in (tags or []) if t],
        })
        return Note.from_record(rec)

    def notes(self) -> List[Note]:
        return [Note.from_record(r) for r in self.all()]

    def get_note(self, rec_id: str) -> Optional[Note]:
        rec = self.get(rec_id)
        return Note.from_record(rec) if rec else None

    def append_to(self, rec_id: str, text: str) -> Optional[Note]:
        rec = self.get(rec_id)
        if not rec:
            return None
        body = (rec.get("body", "") + "\n" + text).strip()
        return Note.from_record(self.update(rec_id, body=body) or {})

    def search(self, query: str = "", *, tag: Optional[str] = None) -> List[Note]:
        q = (query or "").lower()
        out = []
        for n in self.notes():
            if tag and tag not in n.tags:
                continue
            if q and q not in f"{n.title}\n{n.body}\n{' '.join(n.tags)}".lower():
                continue
            out.append(n)
        out.sort(key=lambda n: n.created, reverse=True)
        return out
