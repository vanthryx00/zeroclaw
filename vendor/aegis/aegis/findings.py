"""Structured findings: the record of what a scan, review, or audit turned up.

A finding is a first-class object with a severity, a target, evidence and a
status, so results stop living in scrollback and start feeding reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .store import JsonlStore

SEVERITIES = ["info", "low", "medium", "high", "critical"]
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}
STATUSES = ["open", "confirmed", "false_positive", "fixed", "wont_fix"]


@dataclass
class Finding:
    id: str
    title: str
    severity: str = "info"
    detail: str = ""
    target: str = ""
    evidence: str = ""
    tags: List[str] = field(default_factory=list)
    source: str = ""
    status: str = "open"
    created: float = 0.0

    @classmethod
    def from_record(cls, rec: Dict[str, Any]) -> "Finding":
        return cls(
            id=rec.get("id", ""),
            title=rec.get("title", ""),
            severity=rec.get("severity", "info"),
            detail=rec.get("detail", ""),
            target=rec.get("target", ""),
            evidence=rec.get("evidence", ""),
            tags=list(rec.get("tags", [])),
            source=rec.get("source", ""),
            status=rec.get("status", "open"),
            created=rec.get("created", 0.0),
        )

    @property
    def rank(self) -> int:
        return SEVERITY_RANK.get(self.severity, 0)

    def one_line(self) -> str:
        tgt = f" [{self.target}]" if self.target else ""
        return f"{self.severity.upper():<8} {self.title}{tgt}"


class FindingStore(JsonlStore):
    def __init__(self, path: str):
        super().__init__(path, prefix="fnd")

    def add_finding(self, title: str, *, severity: str = "info", detail: str = "",
                    target: str = "", evidence: str = "", tags: Optional[List[str]] = None,
                    source: str = "", status: str = "open") -> Finding:
        sev = severity.lower().strip()
        if sev not in SEVERITIES:
            sev = "info"
        if status not in STATUSES:
            status = "open"
        rec = self.add({
            "title": title,
            "severity": sev,
            "detail": detail,
            "target": target,
            "evidence": evidence[:8000],
            "tags": [t for t in (tags or []) if t],
            "source": source,
            "status": status,
        })
        return Finding.from_record(rec)

    def findings(self) -> List[Finding]:
        return [Finding.from_record(r) for r in self.all()]

    def get_finding(self, rec_id: str) -> Optional[Finding]:
        rec = self.get(rec_id)
        return Finding.from_record(rec) if rec else None

    def search(self, query: str = "", *, severity: Optional[str] = None,
               status: Optional[str] = None, tag: Optional[str] = None) -> List[Finding]:
        q = (query or "").lower()
        out: List[Finding] = []
        for f in self.findings():
            if severity and f.severity != severity:
                continue
            if status and f.status != status:
                continue
            if tag and tag not in f.tags:
                continue
            if q and q not in " ".join(
                    [f.title, f.detail, f.target, f.evidence, " ".join(f.tags)]).lower():
                continue
            out.append(f)
        out.sort(key=lambda f: (-f.rank, f.title.lower()))
        return out

    def set_status(self, rec_id: str, status: str) -> Optional[Finding]:
        if status not in STATUSES:
            return None
        rec = self.update(rec_id, status=status)
        return Finding.from_record(rec) if rec else None

    def summary(self) -> Dict[str, Any]:
        findings = self.findings()
        by_sev = {s: 0 for s in SEVERITIES}
        by_status: Dict[str, int] = {}
        for f in findings:
            by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
            by_status[f.status] = by_status.get(f.status, 0) + 1
        return {
            "total": len(findings),
            "by_severity": by_sev,
            "by_status": by_status,
            "open_high_plus": sum(1 for f in findings
                                  if f.status == "open" and f.rank >= SEVERITY_RANK["high"]),
        }
