from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from bugreaper.core.models import ScanResult, Severity


def generate_json(result: ScanResult) -> str:
    data = {
        "report_type": "BugReaper X Security Assessment",
        "generated_by": "REAPER v4.0 — Kairyx Security Solutions",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "target": result.target.url,
        "scan_id": result.id,
        "risk_score": result.risk_score,
        "duration_seconds": result.duration_seconds,
        "vulnerability_counts": result.vuln_counts,
        "vulnerabilities": [v.model_dump() for v in result.vulnerabilities],
        "attack_chains": result.attack_chains,
        "ai_analysis": result.ai_analysis,
    }
    return json.dumps(data, indent=2, default=str)


def generate_html(result: ScanResult) -> str:
    counts = result.vuln_counts
    sev_colors = {
        "god-tier": "#ff00ff", "critical": "#dc2626", "high": "#ea580c",
        "medium": "#d97706", "low": "#2563eb", "info": "#6b7280",
    }

    vuln_rows = ""
    for v in sorted(result.vulnerabilities, key=lambda x: (
        ["info", "low", "medium", "high", "critical", "god-tier"].index(x.severity.value)
    ), reverse=True):
        color = sev_colors.get(v.severity.value, "#6b7280")
        vuln_rows += f"""
        <tr>
            <td><span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;text-transform:uppercase">{v.severity.value}</span></td>
            <td><strong>{v.title}</strong></td>
            <td>{v.url or '-'}</td>
            <td>{v.scanner}</td>
            <td style="font-size:12px">{(v.remediation or '')[:100]}</td>
        </tr>"""

    ai_section = ""
    if result.ai_analysis:
        ai_section = f"""
        <div class="section">
            <h2>🤖 REAPER AI Analysis</h2>
            <div style="background:#0f172a;color:#e2e8f0;padding:20px;border-radius:8px;white-space:pre-wrap;font-size:13px">{result.ai_analysis}</div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>BugReaper X — Security Assessment Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#0f172a; color:#e2e8f0; }}
  .header {{ background:linear-gradient(135deg,#1e3a8a,#dc2626); padding:40px; text-align:center; }}
  .header h1 {{ font-size:2.5rem; font-weight:900; letter-spacing:-1px; }}
  .header p {{ color:#93c5fd; margin-top:8px; }}
  .content {{ max-width:1200px; margin:0 auto; padding:40px 20px; }}
  .section {{ background:#1e293b; border-radius:12px; padding:24px; margin-bottom:24px; border:1px solid #334155; }}
  h2 {{ font-size:1.25rem; font-weight:700; margin-bottom:16px; color:#93c5fd; }}
  .stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:16px; }}
  .stat {{ background:#0f172a; border-radius:8px; padding:16px; text-align:center; border:1px solid #334155; }}
  .stat .number {{ font-size:2.5rem; font-weight:900; }}
  .stat .label {{ font-size:11px; text-transform:uppercase; color:#94a3b8; margin-top:4px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ background:#0f172a; padding:10px 12px; text-align:left; color:#94a3b8; text-transform:uppercase; font-size:11px; }}
  td {{ padding:10px 12px; border-bottom:1px solid #1e293b; vertical-align:top; }}
  tr:hover td {{ background:#1e293b; }}
  .risk {{ font-size:3rem; font-weight:900; }}
  .footer {{ text-align:center; color:#475569; padding:40px; font-size:12px; }}
</style>
</head>
<body>
<div class="header">
  <h1>⚡ REAPER Security Report</h1>
  <p>BugReaper X v4.0 — Kairyx Security Solutions, Fort Saskatchewan, Alberta</p>
  <p style="margin-top:8px;font-size:13px">Target: <strong>{result.target.url}</strong> | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
</div>
<div class="content">
  <div class="section">
    <h2>Risk Overview</h2>
    <div class="stats">
      <div class="stat"><div class="risk" style="color:#dc2626">{result.risk_score}</div><div class="label">Risk Score</div></div>
      <div class="stat"><div class="number" style="color:#ff00ff">{counts.get('god-tier',0)}</div><div class="label">God-Tier</div></div>
      <div class="stat"><div class="number" style="color:#dc2626">{counts.get('critical',0)}</div><div class="label">Critical</div></div>
      <div class="stat"><div class="number" style="color:#ea580c">{counts.get('high',0)}</div><div class="label">High</div></div>
      <div class="stat"><div class="number" style="color:#d97706">{counts.get('medium',0)}</div><div class="label">Medium</div></div>
      <div class="stat"><div class="number" style="color:#2563eb">{counts.get('low',0)}</div><div class="label">Low</div></div>
      <div class="stat"><div class="number" style="color:#6b7280">{counts.get('info',0)}</div><div class="label">Info</div></div>
      <div class="stat"><div class="number">{len(result.vulnerabilities)}</div><div class="label">Total</div></div>
    </div>
  </div>
  {ai_section}
  <div class="section">
    <h2>Vulnerability Findings</h2>
    <table>
      <thead><tr><th>Severity</th><th>Title</th><th>URL</th><th>Scanner</th><th>Remediation</th></tr></thead>
      <tbody>{vuln_rows}</tbody>
    </table>
  </div>
</div>
<div class="footer">
  <p>REAPER — Reconnaissance, Exploitation, and Penetration Intelligence Engine with Autonomous Reporting</p>
  <p>Kairyx Security Solutions | Fort Saskatchewan, Alberta | security@kairyx.io | bugreaper-x.ca</p>
</div>
</body>
</html>"""


def generate_markdown(result: ScanResult) -> str:
    lines = [
        f"# BugReaper X Security Report",
        f"",
        f"**Target:** {result.target.url}",
        f"**Risk Score:** {result.risk_score}/10",
        f"**Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Tool:** REAPER v4.0 — Kairyx Security Solutions",
        f"",
        f"## Vulnerability Summary",
        f"",
        f"| Severity | Count |",
        f"|----------|-------|",
    ]
    for sev in ["god-tier", "critical", "high", "medium", "low", "info"]:
        lines.append(f"| {sev.capitalize()} | {result.vuln_counts.get(sev, 0)} |")

    lines += ["", "## Findings", ""]
    for v in sorted(result.vulnerabilities, key=lambda x: (
        ["info", "low", "medium", "high", "critical", "god-tier"].index(x.severity.value)
    ), reverse=True):
        lines += [
            f"### [{v.severity.value.upper()}] {v.title}",
            f"",
            f"- **URL:** {v.url or 'N/A'}",
            f"- **Scanner:** {v.scanner}",
            f"- **Description:** {v.description}",
        ]
        if v.remediation:
            lines.append(f"- **Remediation:** {v.remediation}")
        lines.append("")

    if result.ai_analysis:
        lines += ["## REAPER AI Analysis", "", result.ai_analysis, ""]

    return "\n".join(lines)


def generate_csv(result: ScanResult) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Severity", "CVSS", "URL", "Parameter", "Scanner", "Description", "Remediation", "Tags"])
    for v in result.vulnerabilities:
        writer.writerow([
            v.id, v.title, v.severity.value, v.cvss_score or "",
            v.url or "", v.parameter or "", v.scanner,
            v.description, v.remediation or "", ",".join(v.tags),
        ])
    return output.getvalue()


def generate_sarif(result: ScanResult) -> str:
    rules = {}
    results = []

    for v in result.vulnerabilities:
        rule_id = f"REAPER-{v.scanner.upper()}-{v.severity.value.upper()}"
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": v.title,
                "shortDescription": {"text": v.title},
                "fullDescription": {"text": v.description},
                "help": {"text": v.remediation or ""},
                "defaultConfiguration": {"level": _sarif_level(v.severity.value)},
            }
        results.append({
            "ruleId": rule_id,
            "level": _sarif_level(v.severity.value),
            "message": {"text": v.description},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": v.url or result.target.url}}}],
        })

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "BugReaper X REAPER",
                    "version": "4.0.0",
                    "informationUri": "https://bugreaper-x.ca",
                    "rules": list(rules.values()),
                }
            },
            "results": results,
        }],
    }
    return json.dumps(sarif, indent=2)


def _sarif_level(severity: str) -> str:
    return {"critical": "error", "god-tier": "error", "high": "error",
            "medium": "warning", "low": "note", "info": "note"}.get(severity, "note")


def generate_pdf(result: ScanResult, output_path: str) -> str:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import inch

        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=24, spaceAfter=12)
        story.append(Paragraph("BugReaper X Security Report", title_style))
        story.append(Paragraph(f"Target: {result.target.url}", styles["Normal"]))
        story.append(Paragraph(f"Risk Score: {result.risk_score}/10", styles["Normal"]))
        story.append(Spacer(1, 0.3 * inch))

        story.append(Paragraph("Vulnerability Summary", styles["Heading1"]))
        counts = result.vuln_counts
        table_data = [["Severity", "Count"]]
        for sev in ["god-tier", "critical", "high", "medium", "low", "info"]:
            table_data.append([sev.upper(), str(counts.get(sev, 0))])
        t = Table(table_data, colWidths=[3 * inch, 2 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.3 * inch))

        story.append(Paragraph("Findings", styles["Heading1"]))
        for v in sorted(result.vulnerabilities, key=lambda x: (
            ["info", "low", "medium", "high", "critical", "god-tier"].index(x.severity.value)
        ), reverse=True)[:50]:
            story.append(Paragraph(f"[{v.severity.value.upper()}] {v.title}", styles["Heading2"]))
            story.append(Paragraph(v.description[:400], styles["Normal"]))
            if v.remediation:
                story.append(Paragraph(f"Fix: {v.remediation[:300]}", styles["Normal"]))
            story.append(Spacer(1, 0.1 * inch))

        doc.build(story)
        return output_path
    except ImportError:
        return ""


def generate_report(result: ScanResult, fmt: str, output_path: str | None = None) -> str:
    fmt = fmt.lower()
    if fmt == "json":
        content = generate_json(result)
    elif fmt == "html":
        content = generate_html(result)
    elif fmt == "markdown":
        content = generate_markdown(result)
    elif fmt == "csv":
        content = generate_csv(result)
    elif fmt == "sarif":
        content = generate_sarif(result)
    elif fmt == "pdf":
        if output_path:
            return generate_pdf(result, output_path)
        return ""
    else:
        content = generate_json(result)

    if output_path and fmt != "pdf":
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return output_path
    return content
