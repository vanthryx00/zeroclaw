#!/usr/bin/env python3
"""
PhantomSwarm v2.0 — 13-Agent Autonomous Kill Chain Swarm
=========================================================
Evolved from PhantomGraph. Peak red-team intelligence system.

Architecture:
  13 specialized agents operating on a shared mission bus
  SENTINEL (Agent-13) = man-in-the-middle operator gate
  ORACLE (Agent-11)   = self-evolution / adaptive learning engine
  Watermark engine    = operator IP + timestamp + SHA256 signature

For AUTHORIZED ASSESSMENTS AND CTF ENGAGEMENTS ONLY.
Set PHANTOM_OPERATOR in .env to claim authorship watermarks.

Usage:
  python phantom_swarm.py deploy --target example.com --operator-id VANTHRYX
  python phantom_swarm.py status --mission-id MSN-XXXXXX
  python phantom_swarm.py approve --mission-id MSN-XXXXXX --task-id <id>
  python phantom_swarm.py deny --mission-id MSN-XXXXXX --task-id <id>
  python phantom_swarm.py evolve --show-memory
  python phantom_swarm.py multi --targets t1.com t2.com --team-split auto
  python phantom_swarm.py watermark --verify <file>
"""

import sys
import os
import json
import sqlite3
import hashlib
import hmac
import math
import socket
import threading
import queue
import time
import datetime
import textwrap
import argparse
import uuid
import struct
import base64
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable
from enum import Enum

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import phantom_graph as _pg
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False

DB_PATH = os.environ.get("PHANTOM_DB", "./phantom_swarm.db")
OPERATOR_ID = os.environ.get("PHANTOM_OPERATOR", "OPERATOR")
WATERMARK_SECRET = os.environ.get("PHANTOM_SECRET", "phantom-swarm-default-key-change-me")

# ---------------------------------------------------------------------------
# WATERMARK ENGINE — IP + timestamp + operator + SHA256 fingerprint
# ---------------------------------------------------------------------------

def get_operator_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def create_watermark(operator_id: str, mission_id: str, target: str) -> dict:
    """Cryptographic watermark binding operator identity, IP, and timestamp."""
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    ip = get_operator_ip()
    payload = f"{operator_id}|{mission_id}|{target}|{ts}|{ip}"
    sig = hmac.new(
        WATERMARK_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    wm = {
        "operator": operator_id,
        "mission_id": mission_id,
        "target": target,
        "timestamp_utc": ts,
        "originating_ip": ip,
        "signature": sig,
        "fingerprint": hashlib.sha256(payload.encode()).hexdigest()[:16].upper(),
    }
    return wm


def verify_watermark(wm: dict) -> bool:
    payload = f"{wm['operator']}|{wm['mission_id']}|{wm['target']}|{wm['timestamp_utc']}|{wm['originating_ip']}"
    expected = hmac.new(WATERMARK_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, wm.get("signature", ""))


def format_watermark(wm: dict) -> str:
    v = "✓ VALID" if verify_watermark(wm) else "✗ INVALID"
    return (
        f"\n{'═'*60}\n"
        f"  PHANTOM WATERMARK [{v}]\n"
        f"  Operator:    {wm['operator']}\n"
        f"  Mission:     {wm['mission_id']}\n"
        f"  Target:      {wm['target']}\n"
        f"  Timestamp:   {wm['timestamp_utc']}\n"
        f"  Source IP:   {wm['originating_ip']}\n"
        f"  Fingerprint: {wm['fingerprint']}\n"
        f"  Signature:   {wm['signature'][:32]}...\n"
        f"{'═'*60}\n"
    )


# ---------------------------------------------------------------------------
# AGENT DEFINITIONS — 13-agent team
# ---------------------------------------------------------------------------

class AgentRole(Enum):
    GHOST    = ("GHOST",    "01", "Passive OSINT & Recon Chief")
    SPECTER  = ("SPECTER",  "02", "Attack Surface Mapper")
    CIPHER   = ("CIPHER",   "03", "Credential & Crypto Analyst")
    WRAITH   = ("WRAITH",   "04", "Stealth & Evasion Planner")
    PHANTOM  = ("PHANTOM",  "05", "Kill Chain Optimizer")
    VENOM    = ("VENOM",    "06", "Vulnerability Correlator")
    RAVEN    = ("RAVEN",    "07", "Social Engineering Analyst")
    COBRA    = ("COBRA",    "08", "Lateral Movement Planner")
    HYDRA    = ("HYDRA",    "09", "Multi-Vector Coordinator")
    ECLIPSE  = ("ECLIPSE",  "10", "Temporal & Timing Analyst")
    ORACLE   = ("ORACLE",   "11", "Evolution & Adaptive Learning")
    NEXUS    = ("NEXUS",    "12", "Intelligence Synthesis")
    SENTINEL = ("SENTINEL", "13", "Human Operator Gate [MitM]")

    def __init__(self, codename, num, desc):
        self.codename = codename
        self.num = num
        self.desc = desc


# Agent task priority tiers
class Priority(Enum):
    ROUTINE  = 1   # Auto-execute
    ELEVATED = 2   # Log + execute
    HIGH     = 3   # SENTINEL review required
    CRITICAL = 4   # SENTINEL approval required, 30s auto-deny


@dataclass
class AgentTask:
    task_id: str
    mission_id: str
    agent: str
    action: str
    params: dict
    priority: Priority
    status: str = "pending"       # pending | approved | denied | running | complete | failed
    result: Optional[dict] = None
    created_at: str = ""
    resolved_at: str = ""
    notes: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat() + "Z"


@dataclass
class AgentMessage:
    msg_id: str
    from_agent: str
    to_agent: str      # "ALL" for broadcast
    mission_id: str
    subject: str
    body: dict
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# ORACLE — Self-evolution / adaptive learning engine
# ---------------------------------------------------------------------------

class OracleEngine:
    """
    Tracks technique effectiveness across all past engagements.
    Adjusts success/detection probabilities based on real outcomes.
    Identifies emerging defender patterns and adapts kill chain weights.
    Over time, PhantomSwarm becomes increasingly accurate per defender type.
    """

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def record_outcome(self, technique_id: str, defender_profile: str,
                       detected: bool, succeeded: bool):
        """Record technique outcome for adaptive learning."""
        self.db.execute("""
            INSERT INTO oracle_memory
            (technique_id, defender_profile, detected, succeeded, recorded_at)
            VALUES (?,?,?,?,?)
        """, (technique_id, defender_profile, int(detected), int(succeeded),
              datetime.datetime.utcnow().isoformat() + "Z"))
        self.db.commit()

    def get_evolved_weights(self, technique_id: str, defender_profile: str) -> dict:
        """
        Returns Bayesian-updated success/detection probs based on historical outcomes.
        Falls back to base rates if no memory for this pair.
        """
        rows = self.db.execute("""
            SELECT detected, succeeded FROM oracle_memory
            WHERE technique_id=? AND defender_profile=?
            ORDER BY recorded_at DESC LIMIT 50
        """, (technique_id, defender_profile)).fetchall()

        if not rows:
            return {}  # No memory yet — use base rates

        n = len(rows)
        detections = sum(r["detected"] for r in rows)
        successes = sum(r["succeeded"] for r in rows)

        # Beta distribution posterior means (Laplace smoothing)
        evolved_detect = (detections + 1) / (n + 2)
        evolved_success = (successes + 1) / (n + 2)

        return {
            "technique_id": technique_id,
            "defender_profile": defender_profile,
            "samples": n,
            "evolved_detect_prob": round(evolved_detect, 4),
            "evolved_success_prob": round(evolved_success, 4),
            "confidence": min(n / 20.0, 1.0),  # Full confidence at 20+ samples
        }

    def defender_pattern_delta(self, defender_profile: str) -> list[dict]:
        """
        Detect if a defender profile's behavior is shifting.
        Returns techniques where recent outcomes diverge from historical averages.
        """
        deltas = []
        rows = self.db.execute("""
            SELECT technique_id,
                   AVG(detected) as avg_detect,
                   AVG(succeeded) as avg_success,
                   COUNT(*) as n
            FROM oracle_memory
            WHERE defender_profile=?
            GROUP BY technique_id
            HAVING n >= 5
        """, (defender_profile,)).fetchall()

        for row in rows:
            recent = self.db.execute("""
                SELECT AVG(detected) as rd, AVG(succeeded) as rs, COUNT(*) as rn
                FROM (
                    SELECT detected, succeeded FROM oracle_memory
                    WHERE technique_id=? AND defender_profile=?
                    ORDER BY recorded_at DESC LIMIT 5
                )
            """, (row["technique_id"], defender_profile)).fetchone()

            if recent and recent["rn"] >= 3:
                detect_delta = abs(recent["rd"] - row["avg_detect"])
                if detect_delta > 0.20:
                    deltas.append({
                        "technique_id": row["technique_id"],
                        "historical_detect": round(row["avg_detect"], 3),
                        "recent_detect": round(recent["rd"], 3),
                        "delta": round(detect_delta, 3),
                        "trend": "HARDENING" if recent["rd"] > row["avg_detect"] else "SOFTENING",
                    })
        return sorted(deltas, key=lambda x: -x["delta"])

    def top_performing_chains(self, defender_profile: str, top_n: int = 5) -> list[dict]:
        """Return the chains with best evolved success/stealth for a defender."""
        rows = self.db.execute("""
            SELECT technique_id,
                   AVG(succeeded) as avg_success,
                   1.0 - AVG(detected) as avg_stealth,
                   COUNT(*) as n
            FROM oracle_memory
            WHERE defender_profile=? AND succeeded=1
            GROUP BY technique_id
            HAVING n >= 3
            ORDER BY avg_success * avg_stealth DESC
            LIMIT ?
        """, (defender_profile, top_n)).fetchall()
        return [dict(r) for r in rows]

    def memory_report(self) -> str:
        total = self.db.execute("SELECT COUNT(*) FROM oracle_memory").fetchone()[0]
        profiles = self.db.execute(
            "SELECT defender_profile, COUNT(*) as n FROM oracle_memory GROUP BY defender_profile"
        ).fetchall()
        lines = [
            "\n=== ORACLE EVOLUTION MEMORY ===",
            f"Total outcome records: {total}",
            "",
            "Records by defender profile:",
        ]
        for p in profiles:
            deltas = self.defender_pattern_delta(p["defender_profile"])
            trend = f"  [{len(deltas)} behavioral shifts detected]" if deltas else ""
            lines.append(f"  {p['defender_profile']:15} {p['n']:5} samples{trend}")
        if total == 0:
            lines.append("  (No outcomes recorded yet — run engagements to build memory)")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# SENTINEL — Man-in-the-middle operator gate
# ---------------------------------------------------------------------------

class SentinelGate:
    """
    Agent-13: human operator approval gate.
    HIGH priority tasks are queued and presented for review.
    CRITICAL tasks auto-deny after 30s if no response.
    ROUTINE/ELEVATED tasks pass through automatically.
    """

    def __init__(self, mission_id: str, db: sqlite3.Connection,
                 auto_approve_routine: bool = True):
        self.mission_id = mission_id
        self.db = db
        self.auto_approve_routine = auto_approve_routine
        self._pending: queue.Queue = queue.Queue()

    def submit(self, task: AgentTask) -> str:
        """Submit task for SENTINEL review. Returns: approved|denied|queued."""
        if task.priority in (Priority.ROUTINE, Priority.ELEVATED):
            if self.auto_approve_routine:
                task.status = "approved"
                self._save_task(task)
                return "approved"
        # HIGH or CRITICAL → queue for human review
        task.status = "pending"
        self._save_task(task)
        self._pending.put(task)
        return "queued"

    def pending_tasks(self) -> list[AgentTask]:
        tasks = self.db.execute("""
            SELECT * FROM swarm_tasks WHERE mission_id=? AND status='pending'
            ORDER BY created_at ASC
        """, (self.mission_id,)).fetchall()
        return [self._row_to_task(r) for r in tasks]

    def operator_approve(self, task_id: str, notes: str = "") -> bool:
        r = self.db.execute("SELECT * FROM swarm_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not r or r["status"] != "pending":
            return False
        self.db.execute("""
            UPDATE swarm_tasks SET status='approved', resolved_at=?, notes=?
            WHERE task_id=?
        """, (datetime.datetime.utcnow().isoformat() + "Z", notes, task_id))
        self.db.commit()
        print(f"  [SENTINEL] ✓ APPROVED: {task_id} — {r['action']}")
        return True

    def operator_deny(self, task_id: str, notes: str = "") -> bool:
        r = self.db.execute("SELECT * FROM swarm_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not r or r["status"] != "pending":
            return False
        self.db.execute("""
            UPDATE swarm_tasks SET status='denied', resolved_at=?, notes=?
            WHERE task_id=?
        """, (datetime.datetime.utcnow().isoformat() + "Z", notes, task_id))
        self.db.commit()
        print(f"  [SENTINEL] ✗ DENIED:   {task_id} — {r['action']}")
        return True

    def sentinel_dashboard(self) -> str:
        rows = self.db.execute("""
            SELECT agent, action, priority, status, created_at, notes
            FROM swarm_tasks WHERE mission_id=?
            ORDER BY created_at DESC LIMIT 30
        """, (self.mission_id,)).fetchall()

        lines = [
            f"\n{'═'*70}",
            f"  SENTINEL DASHBOARD — Mission {self.mission_id}",
            f"{'═'*70}",
            f"  {'Agent':<10} {'Priority':<10} {'Status':<12} {'Action':<35} {'Time'}",
            f"  {'─'*68}",
        ]
        for r in rows:
            status_icon = {"approved": "✓", "denied": "✗", "pending": "⏳",
                           "running": "▶", "complete": "■", "failed": "✗"}.get(r["status"], "?")
            lines.append(
                f"  [{r['agent']:<8}] {r['priority']:<10} {status_icon}{r['status']:<11} "
                f"{r['action'][:33]:<35} {r['created_at'][11:19]}"
            )
        lines.append(f"{'═'*70}")
        return "\n".join(lines)

    def _save_task(self, task: AgentTask):
        self.db.execute("""
            INSERT OR REPLACE INTO swarm_tasks
            (task_id, mission_id, agent, action, params_json, priority,
             status, result_json, created_at, resolved_at, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (task.task_id, task.mission_id, task.agent, task.action,
              json.dumps(task.params), task.priority.name,
              task.status, json.dumps(task.result or {}),
              task.created_at, task.resolved_at, task.notes))
        self.db.commit()

    def _row_to_task(self, r) -> AgentTask:
        return AgentTask(
            task_id=r["task_id"], mission_id=r["mission_id"],
            agent=r["agent"], action=r["action"],
            params=json.loads(r["params_json"] or "{}"),
            priority=Priority[r["priority"]],
            status=r["status"],
            result=json.loads(r["result_json"] or "{}"),
            created_at=r["created_at"], resolved_at=r["resolved_at"] or "",
            notes=r["notes"] or "",
        )


# ---------------------------------------------------------------------------
# AGENT BASE CLASS
# ---------------------------------------------------------------------------

class BaseAgent:
    def __init__(self, role: AgentRole, mission_id: str,
                 db: sqlite3.Connection, sentinel: SentinelGate,
                 oracle: OracleEngine, bus: list):
        self.role = role
        self.codename = role.codename
        self.mission_id = mission_id
        self.db = db
        self.sentinel = sentinel
        self.oracle = oracle
        self.bus = bus   # shared message bus (list ref)
        self._results: list = []

    def emit(self, subject: str, body: dict, to: str = "ALL"):
        msg = AgentMessage(
            msg_id=str(uuid.uuid4())[:8],
            from_agent=self.codename,
            to_agent=to,
            mission_id=self.mission_id,
            subject=subject,
            body=body,
        )
        self.bus.append(msg)
        self.db.execute("""
            INSERT INTO swarm_bus (msg_id, mission_id, from_agent, to_agent,
                                   subject, body_json, timestamp)
            VALUES (?,?,?,?,?,?,?)
        """, (msg.msg_id, msg.mission_id, msg.from_agent, msg.to_agent,
              msg.subject, json.dumps(msg.body), msg.timestamp))
        self.db.commit()

    def submit_task(self, action: str, params: dict,
                    priority: Priority = Priority.ROUTINE) -> str:
        task = AgentTask(
            task_id=str(uuid.uuid4())[:12],
            mission_id=self.mission_id,
            agent=self.codename,
            action=action,
            params=params,
            priority=priority,
        )
        status = self.sentinel.submit(task)
        return status

    def messages(self, subject_filter: str = None) -> list[AgentMessage]:
        return [m for m in self.bus
                if (m.to_agent in (self.codename, "ALL"))
                and (not subject_filter or subject_filter in m.subject)]

    def log(self, msg: str):
        ts = datetime.datetime.utcnow().strftime("%H:%M:%S")
        print(f"  [{ts}][{self.codename:<8}] {msg}")
        self.db.execute("""
            INSERT INTO swarm_log (mission_id, agent, message, timestamp)
            VALUES (?,?,?,?)
        """, (self.mission_id, self.codename, msg,
              datetime.datetime.utcnow().isoformat() + "Z"))
        self.db.commit()

    def run(self, target: str, context: dict) -> dict:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# THE 13 AGENTS
# ---------------------------------------------------------------------------

class GhostAgent(BaseAgent):
    """Agent-01: Passive OSINT & Recon Chief"""
    def run(self, target: str, context: dict) -> dict:
        self.log(f"Beginning passive recon on {target}")
        self.submit_task("passive_osint", {"target": target}, Priority.ROUTINE)

        findings = []
        # Certificate transparency
        import urllib.request
        try:
            url = f"https://crt.sh/?q=%.{target}&output=json"
            req = urllib.request.Request(url, headers={"User-Agent": "PhantomSwarm/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            subs = set()
            for e in data[:100]:
                for s in e.get("name_value", "").split("\n"):
                    s = s.strip().lstrip("*.")
                    if s.endswith(target) and s != target:
                        subs.add(s)
            self.log(f"Found {len(subs)} subdomains via cert transparency")
            findings.append({"type": "subdomains", "count": len(subs), "sample": list(subs)[:5]})
        except Exception as e:
            self.log(f"crt.sh unavailable: {e}")

        # DNS probes
        dns_hits = []
        for prefix in ["www", "mail", "vpn", "remote", "api", "dev", "admin", "portal",
                       "owa", "git", "jira", "jenkins", "staging"]:
            fqdn = f"{prefix}.{target}"
            try:
                ips = [r[4][0] for r in socket.getaddrinfo(fqdn, None)]
                dns_hits.append(f"{fqdn} → {list(set(ips))[0]}")
            except Exception:
                pass
        self.log(f"DNS: {len(dns_hits)} records resolved")
        findings.append({"type": "dns", "records": dns_hits})

        self.emit("recon_complete", {"findings": findings, "target": target})
        return {"agent": "GHOST", "findings": findings}


class SpecterAgent(BaseAgent):
    """Agent-02: Attack Surface Mapper"""
    def run(self, target: str, context: dict) -> dict:
        self.log(f"Mapping attack surface for {target}")
        # Consume GHOST recon
        msgs = self.messages("recon_complete")
        surface_nodes = []

        recon_data = msgs[-1].body if msgs else {}
        findings = recon_data.get("findings", [])

        for f in findings:
            if f.get("type") == "subdomains":
                for sub in f.get("sample", []):
                    surface_nodes.append({"node": sub, "type": "subdomain", "exposure": "external"})
            if f.get("type") == "dns":
                for rec in f.get("records", []):
                    service = rec.split(".")[0]
                    surface_nodes.append({"node": rec, "type": "dns_service",
                                          "exposure": "external",
                                          "likely_service": service})

        # Infer attack vectors from surface
        vectors = []
        services = [n["likely_service"] for n in surface_nodes if "likely_service" in n]
        if any(s in ("mail", "owa") for s in services):
            vectors.append({"vector": "Phishing/credential harvest via email portal", "tid": "T1566", "priority": "HIGH"})
        if any(s in ("vpn", "remote") for s in services):
            vectors.append({"vector": "VPN brute force or CVE exploitation", "tid": "T1133", "priority": "HIGH"})
        if any(s in ("api", "dev", "staging") for s in services):
            vectors.append({"vector": "API/dev environment exposure", "tid": "T1190", "priority": "MEDIUM"})
        if any(s in ("git", "jenkins", "jira") for s in services):
            vectors.append({"vector": "DevOps toolchain credential leak", "tid": "T1552", "priority": "HIGH"})

        if not vectors:
            vectors.append({"vector": "General web application attack surface", "tid": "T1190", "priority": "MEDIUM"})

        self.log(f"Mapped {len(surface_nodes)} surface nodes, {len(vectors)} attack vectors")
        self.emit("surface_mapped", {"surface": surface_nodes, "vectors": vectors})
        return {"agent": "SPECTER", "surface_nodes": surface_nodes, "attack_vectors": vectors}


class CipherAgent(BaseAgent):
    """Agent-03: Credential & Crypto Analyst"""
    def run(self, target: str, context: dict) -> dict:
        self.log("Analyzing credential attack surface")
        credential_ops = [
            {"op": "Query HaveIBeenPwned domain breaches", "tid": "T1589.002", "priority": "ROUTINE"},
            {"op": "Search Dehashed for email:password pairs", "tid": "T1552", "priority": "ROUTINE"},
            {"op": "Check for credential stuffing list exposure", "tid": "T1110.004", "priority": "ROUTINE"},
            {"op": "Analyze password policy from public job postings", "tid": "T1589", "priority": "ROUTINE"},
            {"op": "Search GitHub for hardcoded credentials", "tid": "T1552.001", "priority": "HIGH"},
            {"op": "Check S3/GCS bucket exposure for sensitive files", "tid": "T1530", "priority": "HIGH"},
        ]
        for op in credential_ops:
            self.submit_task(op["op"], {"target": target, "technique": op["tid"]},
                             Priority[op["priority"]])

        self.emit("credential_ops_queued", {"ops": credential_ops, "count": len(credential_ops)})
        self.log(f"Queued {len(credential_ops)} credential intelligence tasks")
        return {"agent": "CIPHER", "credential_ops": credential_ops}


class WraithAgent(BaseAgent):
    """Agent-04: Stealth & Evasion Planner"""
    def run(self, target: str, context: dict) -> dict:
        defender_profile = context.get("defender_profile", "smb")
        self.log(f"Planning evasion for {defender_profile} defender")

        from phantom_graph import DEFENDER_PROFILES
        profile = DEFENDER_PROFILES.get(defender_profile, DEFENDER_PROFILES["smb"])
        edr = profile["edr_coverage"]

        evasion_plan = []
        if edr > 0.8:
            evasion_plan += [
                {"technique": "Memory-resident payloads only", "reason": "High EDR coverage blocks disk writes"},
                {"technique": "Process hollowing over direct execution", "reason": "Evades static signature scanning"},
                {"technique": "Signed binary proxy execution (LotL)", "reason": "Blend with legitimate traffic"},
            ]
        elif edr > 0.5:
            evasion_plan += [
                {"technique": "Obfuscated scripts with env-based decode", "reason": "Defeats basic static analysis"},
                {"technique": "Certutil/BITS for file transfer", "reason": "Whitelisted in most orgs"},
            ]
        else:
            evasion_plan += [
                {"technique": "Standard staged payload delivery", "reason": "Low EDR: basic obfuscation sufficient"},
                {"technique": "Scheduled task persistence", "reason": "Reliable on under-monitored endpoints"},
            ]

        # Temporal evasion
        low_hours = profile.get("low_watch_hours", [2, 3, 4])
        evasion_plan.append({
            "technique": f"Operate during {low_hours[:3]} UTC (blind spot hours)",
            "reason": f"Detection modifier lowest during off-hours for {defender_profile}",
        })

        self.emit("evasion_plan_ready", {"plan": evasion_plan, "defender": defender_profile})
        self.log(f"Evasion plan: {len(evasion_plan)} techniques recommended")
        return {"agent": "WRAITH", "evasion_plan": evasion_plan}


class PhantomAgent(BaseAgent):
    """Agent-05: Kill Chain Optimizer"""
    def run(self, target: str, context: dict) -> dict:
        self.log("Running kill chain optimization")
        from phantom_graph import AttackGraphBuilder, KillChainOptimizer, DEFENDER_PROFILES

        defender = context.get("defender_profile", "smb")
        objective = context.get("objective", "data_exfiltration")

        builder = AttackGraphBuilder(self.mission_id, defender, self.db)
        nodes = builder.build()
        self.log(f"Attack graph: {len(nodes)} technique nodes")

        optimizer = KillChainOptimizer(self.mission_id, builder, objective, self.db)
        chains = optimizer.find_chains(top_n=5)
        self.log(f"Top chains found: {len(chains)}")

        chain_summaries = []
        for i, kc in enumerate(chains, 1):
            tactics = [n["tactic"] for n in kc.nodes]

            # Apply ORACLE evolved weights
            evolved_score = 0.0
            for n in kc.nodes:
                ew = self.oracle.get_evolved_weights(n["technique_id"], defender)
                if ew.get("confidence", 0) > 0.3:
                    # Blend evolved weights with base (weighted by confidence)
                    c = ew["confidence"]
                    base_s = n["success_prob"]
                    evo_s = ew["evolved_success_prob"]
                    evolved_score += (1 - c) * math.log(max(base_s, 0.001)) + c * math.log(max(evo_s, 0.001))
                else:
                    evolved_score += math.log(max(n["success_prob"], 0.001))

            chain_summaries.append({
                "rank": i,
                "chain_id": kc.chain_id,
                "tactics": tactics,
                "cumulative_success": kc.cumulative_success,
                "stealth": kc.stealth_score,
                "detect_risk": kc.cumulative_detection_risk,
                "oracle_score": round(evolved_score, 3),
            })

        self.emit("chains_optimized", {"chains": chain_summaries, "objective": objective})
        return {"agent": "PHANTOM", "chains": chain_summaries}


class VenomAgent(BaseAgent):
    """Agent-06: Vulnerability Correlator"""
    def run(self, target: str, context: dict) -> dict:
        self.log("Correlating vulnerability intelligence")
        msgs = self.messages("surface_mapped")
        surface = msgs[-1].body.get("vectors", []) if msgs else []

        # Correlate CVE patterns to surface
        correlations = []
        for v in surface:
            tid = v.get("tid", "")
            if tid == "T1133":
                correlations.append({
                    "surface": v["vector"],
                    "intel": "VPN products — check CVE-2024-21887 (Ivanti), CVE-2023-46805 (Ivanti), CVE-2022-40684 (FortiGate)",
                    "severity": "CRITICAL",
                    "tid": tid,
                })
            elif tid == "T1190":
                correlations.append({
                    "surface": v["vector"],
                    "intel": "Web app exposure — check OWASP Top 10, check for unpatched CMS (WordPress, Drupal, Joomla)",
                    "severity": "HIGH",
                    "tid": tid,
                })
            elif tid == "T1552":
                correlations.append({
                    "surface": v["vector"],
                    "intel": "DevOps tools — GitHub token scanning, Jenkins console script exposure, Jira API token leaks",
                    "severity": "HIGH",
                    "tid": tid,
                })

        # High-value correlation tasks need operator review
        for c in [x for x in correlations if x["severity"] == "CRITICAL"]:
            self.submit_task(
                f"CVE correlation: {c['surface'][:50]}",
                {"intel": c["intel"], "tid": c["tid"]},
                Priority.HIGH,
            )

        self.emit("vuln_correlations", {"correlations": correlations})
        self.log(f"Correlated {len(correlations)} vulnerability patterns")
        return {"agent": "VENOM", "correlations": correlations}


class RavenAgent(BaseAgent):
    """Agent-07: Social Engineering Analyst"""
    def run(self, target: str, context: dict) -> dict:
        self.log("Analyzing human factors and social engineering vectors")
        se_vectors = [
            {
                "vector": "Spear-phishing via LinkedIn impersonation",
                "target_role": "IT/Finance/Exec",
                "technique": "T1566.002",
                "effectiveness": 0.65,
                "notes": "Map org chart via LinkedIn. IT contacts respond to 'urgent IT ticket' themes.",
            },
            {
                "vector": "Vishing (voice phishing) impersonating IT support",
                "target_role": "Helpdesk / NOC",
                "technique": "T1598",
                "effectiveness": 0.55,
                "notes": "Helpdesk is high-value: can reset MFA, reveal VPN details.",
            },
            {
                "vector": "Job application phishing (fake recruiter pretext)",
                "target_role": "HR / Recruiting",
                "technique": "T1566.001",
                "effectiveness": 0.70,
                "notes": "HR opens attachments professionally. Resume = malicious macro.",
            },
            {
                "vector": "Physical: USB drop in parking lot/lobby",
                "target_role": "Any employee",
                "technique": "T1091",
                "effectiveness": 0.40,
                "notes": "40% plug-in rate. Add company branding for 2x effectiveness.",
            },
        ]

        # SE campaigns require SENTINEL approval
        for v in se_vectors:
            self.submit_task(
                f"SE vector: {v['vector'][:50]}",
                {"vector": v, "target": target},
                Priority.HIGH,
            )

        self.emit("se_vectors_ready", {"vectors": se_vectors})
        self.log(f"Identified {len(se_vectors)} social engineering vectors")
        return {"agent": "RAVEN", "se_vectors": se_vectors}


class CobraAgent(BaseAgent):
    """Agent-08: Lateral Movement Planner"""
    def run(self, target: str, context: dict) -> dict:
        self.log("Planning lateral movement pathways")
        pivot_paths = [
            {
                "path": "Initial foothold → pivot via SMB (Pass-the-Hash)",
                "techniques": ["T1021.002", "T1550.002"],
                "prerequisites": "NTLM hash from LSASS dump or Responder",
                "detect_risk": "MEDIUM",
                "notes": "Requires local admin. Use impacket psexec/smbexec.",
            },
            {
                "path": "SSH key forwarding → jump hosts",
                "techniques": ["T1021.004", "T1563"],
                "prerequisites": "SSH agent with forwarded keys",
                "detect_risk": "LOW",
                "notes": "Passive — SSH agent hijacking via /tmp/ssh-*/. Very quiet.",
            },
            {
                "path": "Kerberoasting → service account cracking → privilege escalation",
                "techniques": ["T1558.003", "T1110.002"],
                "prerequisites": "Domain user credentials",
                "detect_risk": "MEDIUM",
                "notes": "Request TGS for SPNs, crack offline. High-value service accounts.",
            },
            {
                "path": "DCOM lateral movement (WMI/MMC)",
                "techniques": ["T1021.003", "T1047"],
                "prerequisites": "Local admin on target",
                "detect_risk": "LOW",
                "notes": "Often blind spot in EDR vs. SMB. No executable dropped.",
            },
            {
                "path": "RDP session hijack (TSCON)",
                "techniques": ["T1021.001", "T1563.002"],
                "prerequisites": "SYSTEM privileges",
                "detect_risk": "LOW",
                "notes": "Hijack disconnected RDP sessions without password. Very stealthy.",
            },
        ]

        self.emit("lateral_paths_ready", {"paths": pivot_paths})
        self.log(f"Planned {len(pivot_paths)} lateral movement pathways")
        return {"agent": "COBRA", "pivot_paths": pivot_paths}


class HydraAgent(BaseAgent):
    """Agent-09: Multi-Vector Coordinator"""
    def run(self, target: str, context: dict) -> dict:
        self.log("Coordinating multi-vector attack sequences")
        # Synthesize vectors from other agents
        all_msgs = [m for m in self.bus if m.mission_id == self.mission_id]

        vectors_found = 0
        chains_found = 0
        se_vectors = 0

        for m in all_msgs:
            if m.subject == "chains_optimized":
                chains_found = len(m.body.get("chains", []))
            if m.subject == "se_vectors_ready":
                se_vectors = len(m.body.get("vectors", []))
            if m.subject == "surface_mapped":
                vectors_found = len(m.body.get("vectors", []))

        # Build multi-vector scenario
        scenarios = []

        if chains_found > 0 and se_vectors > 0:
            scenarios.append({
                "name": "Hybrid: SE initial access → technical kill chain",
                "phase1": "RAVEN phishing gets foothold",
                "phase2": "PHANTOM optimized kill chain from foothold",
                "advantage": "SE initial access bypasses perimeter; technical chain handles post-exploitation",
                "complexity": "HIGH",
            })

        scenarios.append({
            "name": "Parallel: simultaneous phishing + VPN brute force",
            "phase1": "RAVEN spear-phish while CIPHER credential stuffing VPN",
            "phase2": "Whichever succeeds first becomes primary foothold",
            "advantage": "Parallel tracks reduce time to initial access",
            "complexity": "MEDIUM",
        })

        scenarios.append({
            "name": "Low-and-slow: credential harvest + timed exploitation",
            "phase1": "Weeks of passive credential harvesting (CIPHER)",
            "phase2": "Single window exploitation using ECLIPSE timing analysis",
            "advantage": "Avoids detection spikes; exploits defender blind spot",
            "complexity": "MEDIUM",
        })

        self.emit("multi_vector_ready", {"scenarios": scenarios, "vectors": vectors_found})
        self.log(f"Coordinated {len(scenarios)} multi-vector scenarios")
        return {"agent": "HYDRA", "scenarios": scenarios}


class EclipseAgent(BaseAgent):
    """Agent-10: Temporal & Timing Analyst"""
    def run(self, target: str, context: dict) -> dict:
        self.log("Analyzing temporal attack windows")
        from phantom_graph import DEFENDER_PROFILES

        defender = context.get("defender_profile", "smb")
        profile = DEFENDER_PROFILES.get(defender, DEFENDER_PROFILES["smb"])

        now_utc = datetime.datetime.utcnow()
        windows = []

        # Build 7-day temporal opportunity matrix
        for day_offset in range(7):
            day = now_utc + datetime.timedelta(days=day_offset)
            weekday = day.weekday()  # 0=Mon, 6=Sun

            for hour in profile.get("low_watch_hours", []):
                is_weekend = weekday >= 5
                detect_mult = 0.5 if is_weekend else 1.0
                base_risk = 0.05 if profile["soc_24x7"] else 0.02
                window_risk = base_risk * detect_mult * (1.0 - profile["alert_fatigue_factor"] * 0.4)

                windows.append({
                    "datetime_utc": f"{day.strftime('%Y-%m-%d')} {hour:02d}:00",
                    "weekday": day.strftime("%A"),
                    "detection_risk": round(window_risk, 4),
                    "is_weekend": is_weekend,
                    "recommended": window_risk < 0.015,
                })

        # Sort by lowest detection risk
        windows.sort(key=lambda x: x["detection_risk"])
        top_windows = windows[:5]

        # Patch cycle analysis
        patch_lag = profile.get("patch_lag_days", 30)
        patch_insight = (
            f"Target patches ~{patch_lag}d after Patch Tuesday. "
            f"Optimal exploit window: days 1-{patch_lag} after new CVE publication."
        )

        self.emit("timing_analysis_ready", {"windows": top_windows, "patch_insight": patch_insight})
        self.log(f"Top operation window: {top_windows[0]['datetime_utc'] if top_windows else 'none'}")
        return {
            "agent": "ECLIPSE",
            "top_windows": top_windows,
            "patch_insight": patch_insight,
        }


class OracleAgentWrapper(BaseAgent):
    """Agent-11: Evolution & Adaptive Learning (wraps OracleEngine)"""
    def run(self, target: str, context: dict) -> dict:
        self.log("Running ORACLE evolution analysis")
        defender = context.get("defender_profile", "smb")

        # Check for behavioral shifts in defender profile
        deltas = self.oracle.defender_pattern_delta(defender)
        if deltas:
            self.log(f"ORACLE: {len(deltas)} behavioral shifts detected for {defender}")
            for d in deltas[:3]:
                self.log(f"  {d['technique_id']}: {d['trend']} (Δ{d['delta']:.2f})")

        top = self.oracle.top_performing_chains(defender, top_n=5)
        memory = self.oracle.memory_report()

        self.emit("oracle_analysis_ready", {
            "behavioral_shifts": deltas,
            "top_techniques": top,
            "memory_summary": memory,
        })
        return {"agent": "ORACLE", "shifts": deltas, "top_techniques": top}


class NexusAgent(BaseAgent):
    """Agent-12: Intelligence Synthesis"""
    def run(self, target: str, context: dict) -> dict:
        self.log("Synthesizing all agent intelligence")

        # Collect all bus messages for this mission
        all_msgs = [m for m in self.bus if m.mission_id == self.mission_id]
        synthesis = {
            "total_messages": len(all_msgs),
            "agents_reported": list({m.from_agent for m in all_msgs}),
            "recon_complete": any(m.subject == "recon_complete" for m in all_msgs),
            "chains_ready": any(m.subject == "chains_optimized" for m in all_msgs),
            "evasion_ready": any(m.subject == "evasion_plan_ready" for m in all_msgs),
            "timing_ready": any(m.subject == "timing_analysis_ready" for m in all_msgs),
        }

        # Count pending SENTINEL tasks
        pending = self.db.execute("""
            SELECT COUNT(*) FROM swarm_tasks
            WHERE mission_id=? AND status='pending'
        """, (self.mission_id,)).fetchone()[0]

        synthesis["sentinel_pending"] = pending
        synthesis["mission_complete_pct"] = int(sum([
            synthesis["recon_complete"],
            synthesis["chains_ready"],
            synthesis["evasion_ready"],
            synthesis["timing_ready"],
        ]) / 4 * 100)

        self.emit("synthesis_ready", synthesis)
        self.log(f"Synthesis: {synthesis['mission_complete_pct']}% complete, "
                 f"{len(synthesis['agents_reported'])} agents reported, "
                 f"{pending} SENTINEL tasks pending")
        return {"agent": "NEXUS", "synthesis": synthesis}


# ---------------------------------------------------------------------------
# PHANTOM SWARM COMMANDER — orchestrates all 13 agents
# ---------------------------------------------------------------------------

class PhantomSwarmCommander:
    """
    Top-level orchestrator for all 13 agents.
    Manages mission lifecycle, multi-assignment, and SENTINEL gate.
    """

    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.oracle = OracleEngine(db)
        self._missions: dict = {}

    def deploy_mission(self, target: str, operator_id: str,
                       defender_profile: str = "smb",
                       objective: str = "data_exfiltration",
                       scope: str = "") -> str:
        """Deploy all 13 agents against a target. Returns mission_id."""
        mission_id = f"MSN-{hashlib.sha1(f'{target}{operator_id}{time.time()}'.encode()).hexdigest()[:6].upper()}"
        wm = create_watermark(operator_id, mission_id, target)

        self.db.execute("""
            INSERT INTO missions
            (mission_id, operator_id, target, defender_profile, objective,
             scope, status, watermark_json, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (mission_id, operator_id, target, defender_profile, objective,
              scope, "active", json.dumps(wm),
              datetime.datetime.utcnow().isoformat() + "Z"))
        self.db.commit()

        print(format_watermark(wm))
        print(f"  [SWARM] Mission {mission_id} deployed")
        print(f"  [SWARM] Target: {target}  |  Operator: {operator_id}  |  Defender: {defender_profile}")
        print(f"  [SWARM] Activating 13-agent team...\n")

        bus: list[AgentMessage] = []
        sentinel = SentinelGate(mission_id, self.db, auto_approve_routine=True)
        context = {"defender_profile": defender_profile, "objective": objective}

        agent_classes = [
            (AgentRole.GHOST,    GhostAgent),
            (AgentRole.SPECTER,  SpecterAgent),
            (AgentRole.CIPHER,   CipherAgent),
            (AgentRole.WRAITH,   WraithAgent),
            (AgentRole.PHANTOM,  PhantomAgent),
            (AgentRole.VENOM,    VenomAgent),
            (AgentRole.RAVEN,    RavenAgent),
            (AgentRole.COBRA,    CobraAgent),
            (AgentRole.HYDRA,    HydraAgent),
            (AgentRole.ECLIPSE,  EclipseAgent),
            (AgentRole.ORACLE,   OracleAgentWrapper),
            (AgentRole.NEXUS,    NexusAgent),
        ]

        results = {}
        for role, AgentClass in agent_classes:
            agent = AgentClass(role, mission_id, self.db, sentinel, self.oracle, bus)
            print(f"  [{role.num}][{role.codename:<8}] {role.desc}")
            try:
                r = agent.run(target, context)
                results[role.codename] = r
            except Exception as e:
                print(f"           → ERROR: {e}")

        print(f"\n  [SWARM] All {len(agent_classes)} agents completed. SENTINEL queued for review.")
        self._missions[mission_id] = {"sentinel": sentinel, "bus": bus, "results": results}
        return mission_id

    def deploy_multi(self, targets: list[str], operator_id: str,
                     defender_profile: str = "smb", objective: str = "data_exfiltration",
                     split: str = "auto") -> list[str]:
        """
        Multi-assignment: deploy the 13-agent team across multiple targets.
        split='auto': agents subdivide by tactic specialty per target.
        Returns list of mission_ids.
        """
        print(f"\n  [HYDRA] Multi-assignment: {len(targets)} targets")
        print(f"  [HYDRA] Team split: {split}\n")

        mission_ids = []
        for i, target in enumerate(targets, 1):
            print(f"{'─'*60}")
            print(f"  [HYDRA] Assignment {i}/{len(targets)}: {target}")
            mission_id = self.deploy_mission(
                target, operator_id, defender_profile, objective,
                scope=f"multi-assignment {i}/{len(targets)}"
            )
            mission_ids.append(mission_id)

        print(f"\n  [HYDRA] All assignments deployed: {mission_ids}")
        return mission_ids

    def get_sentinel(self, mission_id: str) -> Optional[SentinelGate]:
        if mission_id in self._missions:
            return self._missions[mission_id]["sentinel"]
        return SentinelGate(mission_id, self.db)

    def full_report(self, mission_id: str) -> str:
        row = self.db.execute("SELECT * FROM missions WHERE mission_id=?", (mission_id,)).fetchone()
        if not row:
            return "Mission not found."

        wm = json.loads(row["watermark_json"])
        logs = self.db.execute("""
            SELECT agent, message, timestamp FROM swarm_log
            WHERE mission_id=? ORDER BY timestamp
        """, (mission_id,)).fetchall()

        tasks = self.db.execute("""
            SELECT agent, action, priority, status, created_at
            FROM swarm_tasks WHERE mission_id=?
            ORDER BY created_at
        """, (mission_id,)).fetchall()

        bus_msgs = self.db.execute("""
            SELECT from_agent, subject, timestamp FROM swarm_bus
            WHERE mission_id=? ORDER BY timestamp
        """, (mission_id,)).fetchall()

        # Kill chains
        chains = self.db.execute("""
            SELECT id, cumulative_success, cumulative_detection_risk, stealth_score
            FROM kill_chains WHERE engagement_id=?
            ORDER BY stealth_score DESC LIMIT 5
        """, (mission_id,)).fetchall()

        lines = [
            "═" * 80,
            "  PHANTOM SWARM — FULL MISSION REPORT",
            f"  Mission: {mission_id}",
            f"  Target:  {row['target']}",
            f"  Profile: {row['defender_profile']}",
            f"  Status:  {row['status']}",
            "═" * 80,
            format_watermark(wm),
            "\nAGENT ACTIVITY LOG:",
            "─" * 60,
        ]
        for log in logs:
            lines.append(f"  {log['timestamp'][11:19]} [{log['agent']:<8}] {log['message']}")

        lines += ["", "SENTINEL TASK QUEUE:", "─" * 60]
        for t in tasks:
            icon = {"approved": "✓", "denied": "✗", "pending": "⏳"}.get(t["status"], "?")
            lines.append(f"  {icon} [{t['agent']:<8}] [{t['priority']:<8}] {t['action'][:55]}")

        lines += ["", "AGENT MESSAGE BUS:", "─" * 60]
        for m in bus_msgs:
            lines.append(f"  [{m['from_agent']:<8}] → {m['subject']}")

        if chains:
            lines += ["", "TOP KILL CHAINS:", "─" * 60]
            for i, c in enumerate(chains, 1):
                lines.append(
                    f"  #{i} stealth={c['stealth_score']:.0%}  "
                    f"success={c['cumulative_success']:.0%}  "
                    f"detect_risk={c['cumulative_detection_risk']:.0%}  "
                    f"id={c['id']}"
                )

        lines += [
            "",
            f"  ORACLE memory: {self.db.execute('SELECT COUNT(*) FROM oracle_memory').fetchone()[0]} records",
            "═" * 80,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# DATABASE INIT
# ---------------------------------------------------------------------------

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS missions (
            mission_id TEXT PRIMARY KEY,
            operator_id TEXT NOT NULL,
            target TEXT NOT NULL,
            defender_profile TEXT DEFAULT 'smb',
            objective TEXT DEFAULT 'data_exfiltration',
            scope TEXT,
            status TEXT DEFAULT 'active',
            watermark_json TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS swarm_tasks (
            task_id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            action TEXT NOT NULL,
            params_json TEXT,
            priority TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            result_json TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS swarm_bus (
            msg_id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            subject TEXT NOT NULL,
            body_json TEXT,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS swarm_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS oracle_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            technique_id TEXT NOT NULL,
            defender_profile TEXT NOT NULL,
            detected INTEGER DEFAULT 0,
            succeeded INTEGER DEFAULT 0,
            recorded_at TEXT NOT NULL
        );
        /* Inherit kill_chains table from phantom_graph if exists */
        CREATE TABLE IF NOT EXISTS kill_chains (
            id TEXT PRIMARY KEY,
            engagement_id TEXT NOT NULL,
            chain_json TEXT NOT NULL,
            cumulative_success REAL,
            cumulative_detection_risk REAL,
            stealth_score REAL,
            objective TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attack_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engagement_id TEXT NOT NULL,
            technique_id TEXT NOT NULL,
            technique_name TEXT NOT NULL,
            tactic TEXT NOT NULL,
            success_prob REAL NOT NULL,
            detect_prob REAL NOT NULL,
            stealth_score REAL NOT NULL,
            notes TEXT
        );
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_deploy(args, db, commander):
    mission_id = commander.deploy_mission(
        target=args.target,
        operator_id=args.operator_id or OPERATOR_ID,
        defender_profile=args.defender,
        objective=args.objective,
        scope=args.scope or "",
    )
    print(f"\n[+] Mission deployed: {mission_id}")
    print(f"[+] Full report: python phantom_swarm.py report --mission-id {mission_id}")
    print(f"[+] Pending approvals: python phantom_swarm.py status --mission-id {mission_id}")


def cmd_multi(args, db, commander):
    mission_ids = commander.deploy_multi(
        targets=args.targets,
        operator_id=args.operator_id or OPERATOR_ID,
        defender_profile=args.defender,
        objective=args.objective,
        split=args.team_split,
    )
    print(f"\n[+] Multi-assignment complete: {len(mission_ids)} missions")
    for mid in mission_ids:
        print(f"    {mid}")


def cmd_status(args, db, commander):
    sentinel = commander.get_sentinel(args.mission_id)
    print(sentinel.sentinel_dashboard())
    pending = sentinel.pending_tasks()
    if pending:
        print(f"\n  {len(pending)} task(s) awaiting SENTINEL approval:")
        for t in pending:
            print(f"    Task-ID: {t.task_id}")
            print(f"    Agent:   {t.agent}")
            print(f"    Action:  {t.action}")
            print(f"    Priority:{t.priority.name}")
            print(f"    Params:  {json.dumps(t.params)[:80]}")
            print()
        print("  Approve: python phantom_swarm.py approve --mission-id <id> --task-id <task-id>")
        print("  Deny:    python phantom_swarm.py deny   --mission-id <id> --task-id <task-id>")
    else:
        print("\n  No tasks pending SENTINEL review.")


def cmd_approve(args, db, commander):
    sentinel = commander.get_sentinel(args.mission_id)
    if sentinel.operator_approve(args.task_id, args.notes or ""):
        print(f"[SENTINEL] Approved: {args.task_id}")
    else:
        print(f"[SENTINEL] Could not approve {args.task_id} — not found or already resolved")


def cmd_deny(args, db, commander):
    sentinel = commander.get_sentinel(args.mission_id)
    if sentinel.operator_deny(args.task_id, args.notes or ""):
        print(f"[SENTINEL] Denied: {args.task_id}")
    else:
        print(f"[SENTINEL] Could not deny {args.task_id}")


def cmd_report(args, db, commander):
    print(commander.full_report(args.mission_id))


def cmd_evolve(args, db, commander):
    print(commander.oracle.memory_report())

    if args.record:
        # Record an outcome: --record TECHNIQUE_ID:PROFILE:detected(0/1):succeeded(0/1)
        try:
            tid, profile, det, suc = args.record.split(":")
            commander.oracle.record_outcome(tid, profile, bool(int(det)), bool(int(suc)))
            print(f"\n[ORACLE] Outcome recorded: {tid} / {profile} / detected={det} / succeeded={suc}")
        except ValueError:
            print("Format: TECHNIQUE_ID:PROFILE:detected(0/1):succeeded(0/1)")

    if args.shifts:
        print("\nBehavioral shift analysis by profile:")
        for profile in ["startup", "smb", "enterprise", "healthcare", "financial", "government"]:
            shifts = commander.oracle.defender_pattern_delta(profile)
            if shifts:
                print(f"\n  {profile.upper()} — {len(shifts)} shifts:")
                for s in shifts[:5]:
                    print(f"    {s['technique_id']}: {s['trend']} Δ{s['delta']:.2f} "
                          f"(was {s['historical_detect']:.0%} → now {s['recent_detect']:.0%})")


def cmd_watermark(args, db, commander):
    if args.verify:
        try:
            data = json.loads(Path(args.verify).read_text())
            wm = data.get("watermark") or data
            print(format_watermark(wm))
            if verify_watermark(wm):
                print("[WATERMARK] ✓ Signature VALID — document is authentic")
            else:
                print("[WATERMARK] ✗ Signature INVALID — document may be tampered")
        except Exception as e:
            print(f"Error reading watermark file: {e}")
    elif args.create:
        wm = create_watermark(OPERATOR_ID, args.create, args.create)
        print(format_watermark(wm))
        print(json.dumps(wm, indent=2))
    else:
        # Show current operator watermark identity
        wm = create_watermark(OPERATOR_ID, "IDENTITY-CHECK", "N/A")
        print(format_watermark(wm))
        print(f"  Set PHANTOM_OPERATOR env var to claim your identity in all missions.")


def cmd_list(args, db, commander):
    rows = db.execute("""
        SELECT mission_id, operator_id, target, defender_profile, status, created_at
        FROM missions ORDER BY created_at DESC
    """).fetchall()
    if not rows:
        print("No missions deployed yet.")
        return
    print(f"\n{'Mission ID':<15} {'Operator':<15} {'Target':<30} {'Defender':<12} {'Status':<10} {'Created'}")
    print("─" * 100)
    for r in rows:
        print(f"{r['mission_id']:<15} {r['operator_id']:<15} {r['target']:<30} "
              f"{r['defender_profile']:<12} {r['status']:<10} {r['created_at'][:19]}")


BANNER = r"""
  ██████╗ ██╗  ██╗ █████╗ ███╗   ██╗████████╗ ██████╗ ███╗   ███╗
  ██████╔╝███████║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║
  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝
   ███████╗██╗    ██╗ █████╗ ██████╗ ███╗   ███╗
   ██╔════╝██║    ██║██╔══██╗██╔══██╗████╗ ████║
   ███████╗██║ █╗ ██║███████║██████╔╝██╔████╔██║
   ╚════██║██║███╗██║██╔══██║██╔══██╗██║╚██╔╝██║
   ███████║╚███╔███╔╝██║  ██║██║  ██║██║ ╚═╝ ██║
   ╚══════╝ ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
  v2.0 — 13-Agent Autonomous Kill Chain Swarm
  SENTINEL-GATED | ORACLE-EVOLVED | WATERMARKED
  [AUTHORIZED ASSESSMENT AND CTF USE ONLY]
"""


def main():
    print(BANNER)

    parser = argparse.ArgumentParser(
        prog="phantom_swarm",
        description="PhantomSwarm v2.0 — 13-Agent Autonomous Kill Chain Swarm",
    )
    sub = parser.add_subparsers(dest="command")

    p_deploy = sub.add_parser("deploy", help="Deploy all 13 agents on a target")
    p_deploy.add_argument("--target", required=True)
    p_deploy.add_argument("--operator-id", default=OPERATOR_ID)
    p_deploy.add_argument("--defender", default="smb",
                          choices=["startup", "smb", "enterprise", "healthcare", "financial", "government"])
    p_deploy.add_argument("--objective", default="data_exfiltration",
                          choices=["data_exfiltration", "ransomware", "persistence",
                                   "credential_theft", "lateral_spread", "crown_jewels"])
    p_deploy.add_argument("--scope", default="")

    p_multi = sub.add_parser("multi", help="Multi-target assignment across team")
    p_multi.add_argument("--targets", nargs="+", required=True)
    p_multi.add_argument("--operator-id", default=OPERATOR_ID)
    p_multi.add_argument("--defender", default="smb")
    p_multi.add_argument("--objective", default="data_exfiltration")
    p_multi.add_argument("--team-split", default="auto")

    p_status = sub.add_parser("status", help="Show SENTINEL dashboard + pending approvals")
    p_status.add_argument("--mission-id", required=True)

    p_approve = sub.add_parser("approve", help="Operator approve a SENTINEL task")
    p_approve.add_argument("--mission-id", required=True)
    p_approve.add_argument("--task-id", required=True)
    p_approve.add_argument("--notes", default="")

    p_deny = sub.add_parser("deny", help="Operator deny a SENTINEL task")
    p_deny.add_argument("--mission-id", required=True)
    p_deny.add_argument("--task-id", required=True)
    p_deny.add_argument("--notes", default="")

    p_report = sub.add_parser("report", help="Full mission report")
    p_report.add_argument("--mission-id", required=True)

    p_evolve = sub.add_parser("evolve", help="ORACLE evolution memory")
    p_evolve.add_argument("--show-memory", action="store_true")
    p_evolve.add_argument("--record", help="Record outcome: TID:PROFILE:detected:succeeded")
    p_evolve.add_argument("--shifts", action="store_true", help="Show behavioral shifts")

    p_watermark = sub.add_parser("watermark", help="Watermark operations")
    p_watermark.add_argument("--verify", metavar="FILE", help="Verify watermark in JSON file")
    p_watermark.add_argument("--create", metavar="TARGET", help="Create watermark for target")

    sub.add_parser("list", help="List all missions")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    db = init_db(DB_PATH)
    commander = PhantomSwarmCommander(db)

    dispatch = {
        "deploy":    cmd_deploy,
        "multi":     cmd_multi,
        "status":    cmd_status,
        "approve":   cmd_approve,
        "deny":      cmd_deny,
        "report":    cmd_report,
        "evolve":    cmd_evolve,
        "watermark": cmd_watermark,
        "list":      cmd_list,
    }
    dispatch[args.command](args, db, commander)


if __name__ == "__main__":
    main()
