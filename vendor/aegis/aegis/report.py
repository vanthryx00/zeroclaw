"""Report builder: turn findings, notes and tasks into a shareable document.

Produces Markdown by default and a self-contained HTML file (inline CSS, no
external assets) so a report can be opened offline or archived with the USB.
"""

from __future__ import annotations

import html
import time
from dataclasses import dataclass, field
from typing import List, Optional

from .findings import Finding, FindingStore, SEVERITIES
from .notes import NoteStore
from .tasks import TaskStore


@dataclass
class Report:
    title: str
    findings: List[Finding] = field(default_factory=list)
    notes: List[dict] = field(default_factory=list)
    tasks: List[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    generated: float = field(default_factory=time.time)

    # -- markdown -------------------------------------------------------
    def to_markdown(self) -> str:
        when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(self.generated))
        lines = [f"# {self.title}", "", f"_Generated {when}_", ""]

        if self.meta:
            lines.append("## Environment")
            for k, v in self.meta.items():
                lines.append(f"- **{k}**: {v}")
            lines.append("")

        counts = {s: 0 for s in SEVERITIES}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        lines.append("## Summary")
        lines.append("")
        lines.append("| Severity | Count |")
        lines.append("|---|---|")
        for s in reversed(SEVERITIES):
            lines.append(f"| {s.capitalize()} | {counts.get(s, 0)} |")
        lines.append(f"| **Total** | **{len(self.findings)}** |")
        lines.append("")

        if self.findings:
            lines.append("## Findings")
            lines.append("")
            for i, f in enumerate(self.findings, 1):
                lines.append(f"### {i}. [{f.severity.upper()}] {f.title}")
                lines.append("")
                if f.target:
                    lines.append(f"- **Target**: `{f.target}`")
                lines.append(f"- **Status**: {f.status}")
                if f.source:
                    lines.append(f"- **Source**: {f.source}")
                if f.tags:
                    lines.append(f"- **Tags**: {', '.join(f.tags)}")
                lines.append("")
                if f.detail:
                    lines.append(f.detail)
                    lines.append("")
                if f.evidence:
                    lines.append("```")
                    lines.append(f.evidence.strip()[:4000])
                    lines.append("```")
                    lines.append("")

        if self.tasks:
            lines.append("## Tasks")
            lines.append("")
            for t in self.tasks:
                box = "[x]" if t.get("status") == "done" else "[ ]"
                lines.append(f"- {box} {t.get('title', '')}")
            lines.append("")

        if self.notes:
            lines.append("## Notes")
            lines.append("")
            for n in self.notes:
                lines.append(f"### {n.get('title', '')}")
                lines.append("")
                if n.get("body"):
                    lines.append(n["body"])
                    lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    # -- html -----------------------------------------------------------
    def to_html(self) -> str:
        esc = html.escape
        when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(self.generated))
        sev_class = {"critical": "sev-critical", "high": "sev-high",
                     "medium": "sev-medium", "low": "sev-low", "info": "sev-info"}

        parts = [
            "<!doctype html><html><head><meta charset='utf-8'>",
            f"<title>{esc(self.title)}</title>",
            "<style>",
            "body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;",
            "max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a;line-height:1.55}",
            "h1{border-bottom:3px solid #2563eb;padding-bottom:.4rem}",
            "h2{margin-top:2rem;color:#1e3a8a}",
            ".badge{display:inline-block;padding:.15rem .5rem;border-radius:4px;"
            "font-size:.75rem;font-weight:700;color:#fff}",
            ".sev-critical{background:#7f1d1d}.sev-high{background:#b91c1c}",
            ".sev-medium{background:#d97706}.sev-low{background:#2563eb}",
            ".sev-info{background:#6b7280}",
            ".finding{border:1px solid #e5e7eb;border-left:4px solid #2563eb;",
            "border-radius:6px;padding:1rem;margin:1rem 0}",
            "pre{background:#f3f4f6;padding:.8rem;border-radius:6px;overflow-x:auto}",
            "table{border-collapse:collapse}td,th{border:1px solid #e5e7eb;padding:.4rem .8rem}",
            "code{background:#f3f4f6;padding:.1rem .3rem;border-radius:3px}",
            ".muted{color:#6b7280;font-size:.9rem}",
            "</style></head><body>",
            f"<h1>{esc(self.title)}</h1>",
            f"<p class='muted'>Generated {esc(when)}</p>",
        ]

        if self.meta:
            parts.append("<h2>Environment</h2><ul>")
            for k, v in self.meta.items():
                parts.append(f"<li><strong>{esc(str(k))}</strong>: {esc(str(v))}</li>")
            parts.append("</ul>")

        counts = {s: 0 for s in SEVERITIES}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        parts.append("<h2>Summary</h2><table><tr><th>Severity</th><th>Count</th></tr>")
        for s in reversed(SEVERITIES):
            parts.append(f"<tr><td>{s.capitalize()}</td><td>{counts.get(s, 0)}</td></tr>")
        parts.append(f"<tr><td><strong>Total</strong></td><td><strong>{len(self.findings)}</strong></td></tr>")
        parts.append("</table>")

        if self.findings:
            parts.append("<h2>Findings</h2>")
            for f in self.findings:
                cls = sev_class.get(f.severity, "sev-info")
                parts.append("<div class='finding'>")
                parts.append(f"<span class='badge {cls}'>{esc(f.severity.upper())}</span> "
                             f"<strong>{esc(f.title)}</strong>")
                if f.target:
                    parts.append(f"<div class='muted'>target: <code>{esc(f.target)}</code></div>")
                if f.detail:
                    parts.append(f"<p>{esc(f.detail)}</p>")
                if f.evidence:
                    parts.append(f"<pre>{esc(f.evidence.strip()[:4000])}</pre>")
                parts.append("</div>")

        if self.tasks:
            parts.append("<h2>Tasks</h2><ul>")
            for t in self.tasks:
                mark = "&#10003;" if t.get("status") == "done" else "&#9744;"
                parts.append(f"<li>{mark} {esc(str(t.get('title', '')))}</li>")
            parts.append("</ul>")

        if self.notes:
            parts.append("<h2>Notes</h2>")
            for n in self.notes:
                parts.append(f"<h3>{esc(str(n.get('title', '')))}</h3>")
                if n.get("body"):
                    parts.append(f"<pre>{esc(str(n['body']))}</pre>")

        parts.append("</body></html>")
        return "\n".join(parts)


class ReportBuilder:
    def __init__(self, findings: FindingStore, notes: Optional[NoteStore] = None,
                 tasks: Optional[TaskStore] = None):
        self.findings = findings
        self.notes = notes
        self.tasks = tasks

    def build(self, title: str, *, meta: Optional[dict] = None,
              min_severity: Optional[str] = None) -> Report:
        from .findings import SEVERITY_RANK
        fnds = self.findings.findings()
        if min_severity in SEVERITY_RANK:
            floor = SEVERITY_RANK[min_severity]
            fnds = [f for f in fnds if f.rank >= floor]
        fnds.sort(key=lambda f: (-f.rank, f.title.lower()))
        notes = [n.__dict__ for n in self.notes.notes()] if self.notes else []
        tasks = self.tasks.tasks() if self.tasks else []
        tasks = [t.__dict__ for t in tasks]
        return Report(title=title, findings=fnds, notes=notes, tasks=tasks,
                      meta=meta or {})
