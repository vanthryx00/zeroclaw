#!/usr/bin/env python3
"""
PhantomBounty — HackerOne Bug Bounty Coordination Module
For AUTHORIZED ASSESSMENTS ONLY. Paste a program's scope page; agents
read, approve, write, and proof the scope before you begin testing.
All work sessions are recorded as timestamped proof of findings.

Usage:
    python phantom_bounty.py new --program "Acme Corp" --paste scope.txt
    python phantom_bounty.py read --bounty-id BNT-XXXXXX
    python phantom_bounty.py approve --bounty-id BNT-XXXXXX
    python phantom_bounty.py report --bounty-id BNT-XXXXXX
    python phantom_bounty.py proof --bounty-id BNT-XXXXXX
    python phantom_bounty.py finding --bounty-id BNT-XXXXXX --title "XSS" --severity HIGH
    python phantom_bounty.py list
"""

import os
import sys
import json
import sqlite3
import hashlib
import datetime
import argparse
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

DB_PATH = os.environ.get("PHANTOM_DB", "./phantom_bounty.db")
OPERATOR_ID = os.environ.get("PHANTOM_OPERATOR", "OPERATOR")

def now_iso():
    return datetime.datetime.utcnow().isoformat() + "Z"

def gen_id(prefix, seed):
    return f"{prefix}-{hashlib.sha1(f'{seed}{now_iso()}'.encode()).hexdigest()[:6].upper()}"

def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.cursor().executescript("""
        CREATE TABLE IF NOT EXISTS bounties (
            bounty_id TEXT PRIMARY KEY, operator_id TEXT NOT NULL,
            program TEXT NOT NULL, platform TEXT DEFAULT 'hackerone',
            raw_scope TEXT, status TEXT DEFAULT 'scope_pending',
            created_at TEXT NOT NULL, approved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS scope_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bounty_id TEXT NOT NULL, version TEXT NOT NULL,
            agent TEXT NOT NULL, doc_type TEXT NOT NULL,
            content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approval_checklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bounty_id TEXT NOT NULL, item TEXT NOT NULL,
            checked INTEGER DEFAULT 0, operator_notes TEXT,
            checked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS findings (
            finding_id TEXT PRIMARY KEY, bounty_id TEXT NOT NULL,
            title TEXT NOT NULL, severity TEXT NOT NULL,
            target TEXT, description TEXT, steps TEXT,
            impact TEXT, status TEXT DEFAULT 'draft',
            created_at TEXT NOT NULL, submitted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS proof_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bounty_id TEXT NOT NULL, finding_id TEXT,
            actor TEXT NOT NULL, action TEXT NOT NULL,
            detail TEXT, timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bounty_id TEXT NOT NULL, agent TEXT NOT NULL,
            phase TEXT NOT NULL, verdict TEXT NOT NULL,
            notes TEXT, created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn

IN_SCOPE_PATTERNS = [
    r"in[\s-]*scope[:\s]+([^\n]+)",
    r"targets?[:\s]+([^\n]+)",
    r"\*\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}",
    r"https?://[^\s\"'>]+",
    r"\b(?:app|api|www|admin|portal|stage|dev)\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}",
]

RULE_PATTERNS = [
    r"rate[\s-]*limit", r"dos|denial[\s-]*of[\s-]*service",
    r"social engineering", r"phishing", r"physical",
    r"no\s+automated\s+scan", r"responsible disclosure",
]

def parse_scope(text):
    result = {"in_scope": [], "out_of_scope": [], "rewards": [], "rules": [], "raw_mentions": []}
    lines = text.split("\n")
    in_block, out_block = False, False
    for line in lines:
        ll = line.strip().lower()
        if re.search(r"in[\s-]*scope|targets?\s*:", ll):
            in_block, out_block = True, False
        elif re.search(r"out[\s-]*of[\s-]*scope|excluded|do not test", ll):
            in_block, out_block = False, True
        elif re.search(r"reward|bounty|payment|^---+$", ll):
            in_block = out_block = False
        if in_block and line.strip() and not re.search(r"in[\s-]*scope", ll):
            items = re.findall(r"[\*\[]?([a-zA-Z0-9\-_.*/:]+\.[a-zA-Z]{2,}[^\s,;]*)", line)
            result["in_scope"].extend(items)
        elif out_block and line.strip() and not re.search(r"out[\s-]*of[\s-]*scope", ll):
            items = re.findall(r"[\*\[]?([a-zA-Z0-9\-_.*/:]+\.[a-zA-Z]{2,}[^\s,;]*)", line)
            result["out_of_scope"].extend(items)
    for r in [(r"\$[\d,]+(?:\s*-\s*\$[\d,]+)?", "rewards"), (r"reward[:\s]+([^\n]+)", "rewards")]:
        result["rewards"].extend(re.findall(r[0], text, re.IGNORECASE)[:3])
    for pat in RULE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            result["rules"].append(pat.replace(r"\s*", " ").replace(r"\s", " ").strip())
    wildcards = re.findall(r"\*\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}", text)
    urls = re.findall(r"https?://[^\s\"'>]{4,60}", text)
    result["raw_mentions"] = list(set(wildcards + urls))[:20]
    result["in_scope"] = list(dict.fromkeys(result["in_scope"]))[:30]
    result["out_of_scope"] = list(dict.fromkeys(result["out_of_scope"]))[:20]
    return result

@dataclass
class AgentDecision:
    agent: str; phase: str; verdict: str; notes: str = ""

class ScopeReaderAgent:
    def analyze(self, scope_data, raw_text):
        flags = []
        if not scope_data["in_scope"] and not scope_data["raw_mentions"]:
            flags.append("CRITICAL: No in-scope targets detected — verify manually before testing.")
        if not scope_data["out_of_scope"]:
            flags.append("WARNING: No explicit out-of-scope section — treat parent org as sensitive.")
        wildcards = [s for s in scope_data["in_scope"] if s.startswith("*")]
        if wildcards:
            flags.append(f"NOTE: {len(wildcards)} wildcard entries — enumerate carefully: {wildcards[:3]}")
        if "dos" in raw_text.lower() or "denial" in raw_text.lower():
            flags.append("RULE: DoS testing likely PROHIBITED — confirm before load testing.")
        if "automated" in raw_text.lower():
            flags.append("RULE: Automated scanning may be restricted — review rate-limit policy.")
        if not scope_data["rewards"]:
            flags.append("NOTE: No reward table found — may be private program or VDP.")
        verdict = "APPROVED" if not any(f.startswith("CRITICAL") for f in flags) else "NEEDS_REVIEW"
        return AgentDecision("SCOPE_READER", "read", verdict, "\n".join(flags) if flags else "Scope appears well-defined.")

class ScopeWriterAgent:
    def write(self, bounty_id, program, scope_data, reader_notes):
        lines = [
            f"# PHANTOM BOUNTY — SCOPE DOCUMENT",
            f"Program: {program}", f"Bounty ID: {bounty_id}",
            f"Generated: {now_iso()}", f"Operator: {OPERATOR_ID}", "",
            "## IN-SCOPE TARGETS", "```",
        ]
        targets = scope_data["in_scope"] or scope_data["raw_mentions"][:10]
        for t in targets: lines.append(f"  {t}")
        if not targets: lines.append("  [MANUAL ENTRY REQUIRED]")
        lines += ["```", "", "## OUT-OF-SCOPE TARGETS", "```"]
        for t in scope_data.get("out_of_scope", []): lines.append(f"  {t}")
        if not scope_data.get("out_of_scope"): lines.append("  [NONE EXPLICITLY LISTED — TREAT ALL NON-IN-SCOPE AS OOB]")
        lines += ["```", "", "## PROGRAM RULES"]
        for r in scope_data.get("rules", []): lines.append(f"  - {r}")
        if not scope_data.get("rules"): lines.append("  [No explicit rules extracted — review program page manually]")
        lines += ["", "## REWARD TABLE"]
        for r in scope_data.get("rewards", []): lines.append(f"  {r}")
        if not scope_data.get("rewards"): lines.append("  [Not extracted — check program page]")
        lines += ["", "## READER AGENT FLAGS", reader_notes, "",
                  "## TESTING AUTHORIZATION",
                  f"  Authorized by: {OPERATOR_ID}",
                  "  Do not test out-of-scope targets.",
                  "  Rate-limit all automated tools.",
                  "  Report findings responsibly.",
        ]
        return "\n".join(lines)

class ScopeProoferAgent:
    def proofread(self, scope_doc, scope_data, raw_text):
        issues = []
        if "[MANUAL ENTRY REQUIRED]" in scope_doc:
            issues.append("CRITICAL: In-scope section empty — must be manually populated before testing.")
        if len(scope_data.get("in_scope", [])) > 25:
            issues.append(f"NOTE: {len(scope_data['in_scope'])} in-scope entries — very broad scope.")
        if "production" in raw_text.lower() and "production" not in scope_doc.lower():
            issues.append("NOTE: 'production' mentioned in raw scope but not captured — verify.")
        verdict = "PASS" if not any(i.startswith("CRITICAL") for i in issues) else "FAIL"
        notes = "\n".join(issues) if issues else "Proof-read complete. No critical issues found."
        return AgentDecision("SCOPE_PROOFER", "proofread", verdict, notes)

class ProofRecorder:
    def __init__(self, db, bounty_id):
        self.db = db; self.bounty_id = bounty_id

    def log(self, actor, action, detail="", finding_id=None):
        self.db.execute(
            "INSERT INTO proof_log (bounty_id,finding_id,actor,action,detail,timestamp) VALUES (?,?,?,?,?,?)",
            (self.bounty_id, finding_id, actor, action, detail, now_iso()))
        self.db.commit()

    def get_proof(self):
        return self.db.execute(
            "SELECT actor,action,detail,finding_id,timestamp FROM proof_log WHERE bounty_id=? ORDER BY timestamp",
            (self.bounty_id,)).fetchall()

    def export_proof(self):
        proof = self.get_proof()
        lines = [
            "PHANTOM BOUNTY — PROOF OF WORK LOG",
            f"Bounty: {self.bounty_id}  Operator: {OPERATOR_ID}",
            f"Exported: {now_iso()}", "=" * 70, "",
        ]
        for p in proof:
            fid = f" [{p['finding_id']}]" if p["finding_id"] else ""
            lines.append(f"  {p['timestamp'][:19]}  [{p['actor']:<14}]{fid}  {p['action']}  {p['detail'][:60]}")
        return "\n".join(lines)

DEFAULT_CHECKLIST = [
    "In-scope targets are clearly defined and confirmed.",
    "Out-of-scope targets noted and will NOT be tested.",
    "Testing rules reviewed (rate-limits, DoS restrictions, auth).",
    "Reward structure understood.",
    "Testing approach stays within authorized scope.",
    "Proof recording enabled for all findings.",
    "No personal data accessed beyond what proves the vulnerability.",
    "Testing will stop immediately if out-of-scope activity is detected.",
]

def build_checklist(db, bounty_id):
    for item in DEFAULT_CHECKLIST:
        db.execute("INSERT INTO approval_checklist (bounty_id,item) VALUES (?,?)", (bounty_id, item))
    db.commit()

def show_checklist(db, bounty_id):
    rows = db.execute("SELECT id,item,checked,operator_notes FROM approval_checklist WHERE bounty_id=?", (bounty_id,)).fetchall()
    print(f"\n  OPERATOR APPROVAL CHECKLIST — {bounty_id}")
    print("  " + "-" * 65)
    for r in rows:
        mark = "[x]" if r["checked"] else "[ ]"
        note = f"  // {r['operator_notes']}" if r["operator_notes"] else ""
        print(f"  {r['id']:>2}. {mark} {r['item']}{note}")
    checked = sum(1 for r in rows if r["checked"])
    print(f"\n  {checked}/{len(rows)} items checked.")
    return checked, len(rows)

def check_item(db, bounty_id, item_id, notes=""):
    db.execute(
        "UPDATE approval_checklist SET checked=1,operator_notes=?,checked_at=? WHERE bounty_id=? AND id=?",
        (notes, now_iso(), bounty_id, item_id))
    db.commit()

def check_all(db, bounty_id):
    db.execute("UPDATE approval_checklist SET checked=1,checked_at=? WHERE bounty_id=?", (now_iso(), bounty_id))
    db.commit()

def cmd_new(args, db):
    raw = ""
    if args.paste:
        p = Path(args.paste)
        if not p.exists(): print(f"[-] File not found: {args.paste}"); return
        raw = p.read_text()
    else:
        print("  Paste program scope/rules below. Press Ctrl+D when done:")
        try: raw = sys.stdin.read()
        except KeyboardInterrupt: print("\n[-] Cancelled"); return
    if not raw.strip(): print("[-] No scope text provided."); return

    bid = gen_id("BNT", args.program)
    db.execute(
        "INSERT INTO bounties (bounty_id,operator_id,program,platform,raw_scope,status,created_at) VALUES (?,?,?,?,?,?,?)",
        (bid, OPERATOR_ID, args.program, args.platform, raw, "scope_analysis", now_iso()))
    db.commit()
    proof = ProofRecorder(db, bid)
    proof.log(OPERATOR_ID, "scope_pasted", f"program={args.program} len={len(raw)}")

    print(f"\n[+] Bounty {bid} | Program: {args.program}")
    print("  [01] SCOPE_READER  — parsing and flagging ambiguities...")
    scope_data = parse_scope(raw)
    reader_result = ScopeReaderAgent().analyze(scope_data, raw)
    db.execute("INSERT INTO agent_decisions (bounty_id,agent,phase,verdict,notes,created_at) VALUES (?,?,?,?,?,?)",
               (bid, reader_result.agent, reader_result.phase, reader_result.verdict, reader_result.notes, now_iso()))
    proof.log("SCOPE_READER", "scope_read", f"verdict={reader_result.verdict}")
    print(f"       Verdict: {reader_result.verdict}")
    for note in reader_result.notes.split("\n"): print(f"       {note}")

    print("\n  [02] SCOPE_WRITER  — generating canonical scope document...")
    scope_doc = ScopeWriterAgent().write(bid, args.program, scope_data, reader_result.notes)
    db.execute("INSERT INTO scope_docs (bounty_id,version,agent,doc_type,content,created_at) VALUES (?,?,?,?,?,?)",
               (bid, "v1", "SCOPE_WRITER", "canonical_scope", scope_doc, now_iso()))
    proof.log("SCOPE_WRITER", "scope_written", "canonical scope doc v1")
    print("       Scope document written (v1).")

    print("\n  [03] SCOPE_PROOFER — proof-reading and cross-checking...")
    proof_result = ScopeProoferAgent().proofread(scope_doc, scope_data, raw)
    db.execute("INSERT INTO agent_decisions (bounty_id,agent,phase,verdict,notes,created_at) VALUES (?,?,?,?,?,?)",
               (bid, proof_result.agent, proof_result.phase, proof_result.verdict, proof_result.notes, now_iso()))
    proof.log("SCOPE_PROOFER", "scope_proofread", f"verdict={proof_result.verdict}")
    print(f"       Verdict: {proof_result.verdict}")
    for note in proof_result.notes.split("\n"): print(f"       {note}")

    status = "scope_ready" if (reader_result.verdict != "NEEDS_REVIEW" and proof_result.verdict == "PASS") else "scope_review_required"
    db.execute("UPDATE bounties SET status=? WHERE bounty_id=?", (status, bid)); db.commit()
    build_checklist(db, bid)
    print()
    show_checklist(db, bid)
    print(f"\n  Status: {status}")
    print(f"  Next: python phantom_bounty.py read --bounty-id {bid}")

def cmd_read(args, db):
    row = db.execute("SELECT * FROM bounties WHERE bounty_id=?", (args.bounty_id,)).fetchone()
    if not row: print("[-] Not found"); return
    docs = db.execute("SELECT version,agent,doc_type,content,created_at FROM scope_docs WHERE bounty_id=? ORDER BY created_at DESC", (args.bounty_id,)).fetchall()
    decisions = db.execute("SELECT agent,phase,verdict,notes FROM agent_decisions WHERE bounty_id=? ORDER BY created_at", (args.bounty_id,)).fetchall()
    print(f"\n{'='*70}\n  BOUNTY: {row['bounty_id']}  |  {row['program']}  |  Status: {row['status']}\n{'='*70}\n")
    for d in decisions:
        print(f"  [{d['agent']:<14}] {d['phase']:>12}  Verdict: {d['verdict']}")
        for note in d["notes"].split("\n"): print(f"             {note}")
    if docs:
        print(f"\n  CANONICAL SCOPE DOCUMENT (latest):\n  {'-'*60}")
        print(docs[0]["content"])
    show_checklist(db, args.bounty_id)

def cmd_approve(args, db):
    row = db.execute("SELECT * FROM bounties WHERE bounty_id=?", (args.bounty_id,)).fetchone()
    if not row: print("[-] Not found"); return
    show_checklist(db, args.bounty_id)
    print()
    if args.check_all:
        check_all(db, args.bounty_id)
        print("  [+] All checklist items marked.")
    elif args.check_item:
        check_item(db, args.bounty_id, args.check_item, args.notes or "")
        print(f"  [+] Item {args.check_item} checked.")
        show_checklist(db, args.bounty_id); return
    checked, total = show_checklist(db, args.bounty_id)
    if checked < total:
        print(f"\n  [{checked}/{total}] Not all items checked. Use --check-all or --check-item N."); return
    proof = ProofRecorder(db, args.bounty_id)
    proof.log(OPERATOR_ID, "operator_approved", f"all {total} checklist items confirmed")
    db.execute("UPDATE bounties SET status='approved',approved_at=? WHERE bounty_id=?", (now_iso(), args.bounty_id))
    db.commit()
    print(f"\n  [APPROVED] {args.bounty_id} is ready for testing.")

def cmd_finding(args, db):
    row = db.execute("SELECT * FROM bounties WHERE bounty_id=?", (args.bounty_id,)).fetchone()
    if not row: print("[-] Bounty not found"); return
    if row["status"] != "approved":
        print(f"  [!] Bounty not approved yet. Run: python phantom_bounty.py approve --bounty-id {args.bounty_id} --check-all")
    fid = gen_id("FND", f"{args.bounty_id}{args.title}")
    db.execute(
        "INSERT INTO findings (finding_id,bounty_id,title,severity,target,description,steps,impact,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (fid, args.bounty_id, args.title, args.severity.upper(), args.target or "",
         args.description or "", args.steps or "", args.impact or "", "draft", now_iso()))
    db.commit()
    ProofRecorder(db, args.bounty_id).log(OPERATOR_ID, "finding_created", f"title={args.title} severity={args.severity}", fid)
    print(f"\n[+] Finding {fid}\n  Title:    {args.title}\n  Severity: {args.severity.upper()}\n  Target:   {args.target or '(not set)'}")

def cmd_report(args, db):
    row = db.execute("SELECT * FROM bounties WHERE bounty_id=?", (args.bounty_id,)).fetchone()
    if not row: print("[-] Not found"); return
    findings = db.execute("SELECT * FROM findings WHERE bounty_id=? ORDER BY created_at", (args.bounty_id,)).fetchall()
    proof = ProofRecorder(db, args.bounty_id)
    print(f"\n{'='*70}\n  PHANTOM BOUNTY REPORT — {row['bounty_id']}\n  Program: {row['program']}  |  Operator: {row['operator_id']}  |  Status: {row['status']}\n  Approved: {row['approved_at'] or 'NOT YET APPROVED'}\n{'='*70}\n")
    if not findings:
        print("  No findings yet.")
    else:
        print(f"  FINDINGS ({len(findings)})\n  " + "-"*60)
        for f in findings:
            sev_col = {"CRITICAL":"\033[31m","HIGH":"\033[33m","MEDIUM":"\033[36m","LOW":"\033[32m"}.get(f["severity"],"\033[0m")
            print(f"  [{sev_col}{f['severity']:<8}\033[0m] {f['finding_id']}  {f['title']}")
            if f["target"]: print(f"              Target: {f['target']}")
            if f["description"]: print(f"              Desc:   {f['description'][:80]}")
            print()
    print("\n  PROOF OF WORK SUMMARY\n  " + "-"*60)
    for p in proof.get_proof()[-20:]:
        fid = f" [{p['finding_id']}]" if p["finding_id"] else ""
        print(f"  {p['timestamp'][:19]}  [{p['actor']:<14}]{fid}  {p['action']}")

def cmd_proof(args, db):
    row = db.execute("SELECT * FROM bounties WHERE bounty_id=?", (args.bounty_id,)).fetchone()
    if not row: print("[-] Not found"); return
    export = ProofRecorder(db, args.bounty_id).export_proof()
    print(export)
    if args.output:
        Path(args.output).write_text(export)
        print(f"\n[+] Proof log saved: {args.output}")

def cmd_list(args, db):
    rows = db.execute("SELECT bounty_id,operator_id,program,status,created_at FROM bounties ORDER BY created_at DESC").fetchall()
    if not rows: print("No bounties. Start: python phantom_bounty.py new --program 'Acme Corp' --paste scope.txt"); return
    print(f"\n  {'ID':<15} {'OPERATOR':<12} {'PROGRAM':<25} {'STATUS':<25} CREATED")
    print("  " + "-"*85)
    for r in rows:
        print(f"  {r['bounty_id']:<15} {r['operator_id']:<12} {r['program']:<25} {r['status']:<25} {r['created_at'][:19]}")

def main():
    p = argparse.ArgumentParser(prog="phantom_bounty")
    sub = p.add_subparsers(dest="command")
    n = sub.add_parser("new"); n.add_argument("--program",required=True); n.add_argument("--paste"); n.add_argument("--platform",default="hackerone")
    r = sub.add_parser("read"); r.add_argument("--bounty-id",required=True)
    a = sub.add_parser("approve"); a.add_argument("--bounty-id",required=True); a.add_argument("--check-item",type=int); a.add_argument("--check-all",action="store_true"); a.add_argument("--notes",default="")
    f = sub.add_parser("finding"); f.add_argument("--bounty-id",required=True); f.add_argument("--title",required=True); f.add_argument("--severity",default="MEDIUM",choices=["CRITICAL","HIGH","MEDIUM","LOW","INFORMATIONAL"]); f.add_argument("--target",default=""); f.add_argument("--description",default=""); f.add_argument("--steps",default=""); f.add_argument("--impact",default="")
    rp = sub.add_parser("report"); rp.add_argument("--bounty-id",required=True)
    pr = sub.add_parser("proof"); pr.add_argument("--bounty-id",required=True); pr.add_argument("--output")
    sub.add_parser("list")
    args = p.parse_args()
    if not args.command: p.print_help(); return
    db = init_db(DB_PATH)
    {"new":cmd_new,"read":cmd_read,"approve":cmd_approve,"finding":cmd_finding,"report":cmd_report,"proof":cmd_proof,"list":cmd_list}[args.command](args, db)

if __name__ == "__main__":
    main()
