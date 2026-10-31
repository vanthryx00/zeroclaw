"""Learning engine — the part that makes Aegis get smarter over time.

Three stores feed a single retrieval step:

* **Snippets** (``snippets.py``) — code the operator saved.
* **Experiences** — commands that worked, corrections, and facts.
* **Preferences** — how this operator likes to work.

Before every reply, :meth:`LearningEngine.context_for` ranks all three against
the current request with BM25 and folds the best matches into the prompt. No
network, no embeddings — just an accumulating local knowledge base.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .retrieval import BM25
from .snippets import SnippetStore


@dataclass
class Experience:
    id: str
    ts: float
    kind: str          # "success" | "lesson" | "correction" | "preference" | "fact"
    title: str
    content: str
    tags: List[str] = field(default_factory=list)
    score: float = 0.0  # net feedback
    uses: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "Experience":
        return cls(
            id=d.get("id", ""), ts=d.get("ts", 0.0), kind=d.get("kind", "lesson"),
            title=d.get("title", ""), content=d.get("content", ""),
            tags=list(d.get("tags", [])), score=d.get("score", 0.0),
            uses=d.get("uses", 0),
        )

    def searchable_text(self) -> str:
        return " ".join([self.title, self.kind, " ".join(self.tags), self.content])


class ExperienceStore:
    def __init__(self, path: str):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Experience]:
        if not self.path.is_file():
            return []
        out: List[Experience] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(Experience.from_dict(json.loads(line)))
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
        return out

    def _rewrite(self, items: Sequence[Experience]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for e in items:
                fh.write(json.dumps(e.to_dict()) + "\n")
        os.replace(tmp, self.path)

    def add(self, kind: str, title: str, content: str,
            tags: Optional[Sequence[str]] = None) -> Experience:
        exp = Experience(
            id=f"exp-{int(time.time()*1000)}",
            ts=time.time(), kind=kind, title=title.strip()[:200],
            content=content.strip(),
            tags=[t.strip() for t in (tags or []) if t.strip()],
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(exp.to_dict()) + "\n")
        return exp

    def all(self) -> List[Experience]:
        return self._load()

    def by_kind(self, kind: str) -> List[Experience]:
        return [e for e in self._load() if e.kind == kind]

    def feedback(self, exp_id: str, delta: float) -> bool:
        items = self._load()
        found = False
        for e in items:
            if e.id == exp_id:
                e.score += delta
                found = True
        if found:
            self._rewrite(items)
        return found

    def bump(self, exp_id: str) -> None:
        items = self._load()
        for e in items:
            if e.id == exp_id:
                e.uses += 1
        self._rewrite(items)

    def delete(self, exp_id: str) -> bool:
        items = self._load()
        kept = [e for e in items if e.id != exp_id]
        if len(kept) == len(items):
            return False
        self._rewrite(kept)
        return True

    def search(self, query: str, kind: Optional[str] = None, limit: int = 10) -> List[Experience]:
        items = self._load()
        if kind:
            items = [e for e in items if e.kind == kind]
        if not query.strip():
            return sorted(items, key=lambda e: e.ts, reverse=True)[:limit]
        index = BM25([(e.id, e.searchable_text()) for e in items])
        ranked = index.search(query, k=limit)
        by_id = {e.id: e for e in items}
        return [by_id[i] for i, _ in ranked if i in by_id]

    def stats(self) -> Dict:
        items = self._load()
        by_kind: Dict[str, int] = {}
        for e in items:
            by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
        return {"count": len(items), "kinds": by_kind}


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------

class LearningEngine:
    def __init__(self, cfg):
        data = cfg.learning
        self.cfg = cfg
        self.enabled = data.enabled
        self.max_items = data.max_context_items
        self.snippets = SnippetStore(data.snippet_file)
        self.experiences = ExperienceStore(data.experience_file)

    # -- context injection ---------------------------------------------
    def context_for(self, query: str) -> str:
        """Return a compact block of relevant learned material, or ''."""
        if not self.enabled or not query.strip():
            return ""

        parts: List[str] = []

        snips = self.snippets.search(query, limit=max(1, self.max_items // 2 + 1))
        if snips:
            lines = ["### Saved code snippets (from previous sessions)"]
            for s in snips:
                lines.append(f"- [{s.id}] {s.title} ({s.language})"
                             + (f" tags={','.join(s.tags)}" if s.tags else ""))
                if s.description:
                    lines.append(f"    {s.description}")
                preview = s.code.strip().splitlines()
                preview = "\n".join(preview[:12])
                lines.append(f"```{s.language}\n{preview}\n```")
            parts.append("\n".join(lines))

        exps = self.experiences.search(query, limit=self.max_items)
        # preferences are always relevant, so pull them regardless of ranking
        prefs = self.experiences.by_kind("preference")
        exps = [e for e in exps if e.kind != "preference"] + prefs
        if exps:
            lines = ["### Things you have learned"]
            seen = set()
            for e in exps:
                if e.id in seen:
                    continue
                seen.add(e.id)
                label = {"success": "worked before", "correction": "correction",
                         "preference": "operator preference", "fact": "fact",
                         "lesson": "lesson"}.get(e.kind, e.kind)
                lines.append(f"- [{e.id}] ({label}) {e.title}: {e.content[:300]}")
            parts.append("\n".join(lines))

        if not parts:
            return ""
        header = ("## Learned context (recall from earlier sessions; use it when "
                  "relevant, ignore it when not)\n")
        return header + "\n\n".join(parts)

    # -- recording ------------------------------------------------------
    def record_lesson(self, text: str, tags: Optional[Sequence[str]] = None,
                      title: str = "") -> Experience:
        return self.experiences.add("lesson", title or text[:80], text, tags)

    def record_preference(self, text: str, tags: Optional[Sequence[str]] = None) -> Experience:
        return self.experiences.add("preference", text[:80], text, tags)

    def record_fact(self, text: str, tags: Optional[Sequence[str]] = None) -> Experience:
        return self.experiences.add("fact", text[:80], text, tags)

    def record_correction(self, wrong: str, right: str,
                          tags: Optional[Sequence[str]] = None) -> Experience:
        return self.experiences.add(
            "correction", f"not: {wrong[:60]}", f"Instead: {right}", tags)

    def record_success(self, command: str, summary: str = "",
                       tags: Optional[Sequence[str]] = None) -> Experience:
        body = command if not summary else f"{command}\n-> {summary[:300]}"
        return self.experiences.add("success", command[:100], body, tags)

    def save_snippet(self, title: str, code: str, **kwargs):
        return self.snippets.save(title, code, **kwargs)

    def stats(self) -> Dict:
        return {"snippets": self.snippets.stats(), "experiences": self.experiences.stats()}
