#!/usr/bin/env python3
"""
PhantomGraph — Probabilistic Kill Chain Reasoning Engine
For authorized red team assessments and CTF engagements only.

Novel design: combines passive OSINT → probabilistic attack graph →
defender fatigue modeling → LotL advisor → operator narrative.
Unlike scanners (find vulns) or frameworks (exploit them), PhantomGraph
reasons about the OPTIMAL PATH through a target environment.

Usage:
    python phantom_graph.py scope --target example.com --org "Acme Corp"
    python phantom_graph.py graph --engagement-id ENG-001
    python phantom_graph.py paths --engagement-id ENG-001 --top 5
    python phantom_graph.py narrative --engagement-id ENG-001
    python phantom_graph.py defender --engagement-id ENG-001
    python phantom_graph.py lotl --os windows --priv user
"""

import sys
import os
import json
import sqlite3
import hashlib
import math
import random
import socket
import ssl
import urllib.request
import urllib.error
import re
import argparse
import datetime
import textwrap
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DB_PATH = os.environ.get("PHANTOM_DB", "./phantom_graph.db")

BANNER = r"""
  ██████╗ ██╗  ██╗ █████╗ ███╗   ██╗███████╗██████╗ ███╗   ███╗
  ██╔══██╗██║  ██║██╔══██╗████╗  ██║╚══██╔══╝██╔═══██╗████╗ ████║
  ██████╔╝███████║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║
  ██╔═══╝ ██╔══██║██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║
  ██║     ██║  ██║██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║
  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝
   ██████╗ ██████╗  █████╗ ██████╗ ██╗  ██╗
  ██╔════╝ ██╔══██╗██╔══██╗██╔══██╗██║  ██║
  ██║  ███╗██████╔╝███████║██████╔╝███████║
  ██║   ██║██╔══██╗██╔══██║██╔═══╝ ██╔══██║
  ╚██████╔╝██║  ██║██║  ██║██║     ██║  ██║
   ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝
  Probabilistic Kill Chain Reasoning Engine
  [AUTHORIZED ASSESSMENT USE ONLY]
"""

# ---------------------------------------------------------------------------
# MITRE ATT&CK technique catalog
# ---------------------------------------------------------------------------
ATTACK_TECHNIQUES = {
    "T1590": {"name": "Gather Victim Network Information", "tactic": "recon", "detect_prob": 0.05, "success_base": 0.92},
    "T1589": {"name": "Gather Victim Identity Information", "tactic": "recon", "detect_prob": 0.04, "success_base": 0.90},
    "T1596": {"name": "Search Open Technical Databases", "tactic": "recon", "detect_prob": 0.02, "success_base": 0.95},
    "T1598": {"name": "Phishing for Information", "tactic": "recon", "detect_prob": 0.20, "success_base": 0.55},
    "T1566": {"name": "Phishing", "tactic": "initial_access", "detect_prob": 0.35, "success_base": 0.50},
    "T1190": {"name": "Exploit Public-Facing Application", "tactic": "initial_access", "detect_prob": 0.45, "success_base": 0.40},
    "T1133": {"name": "External Remote Services", "tactic": "initial_access", "detect_prob": 0.30, "success_base": 0.55},
    "T1078": {"name": "Valid Accounts", "tactic": "initial_access", "detect_prob": 0.25, "success_base": 0.70},
    "T1199": {"name": "Trusted Relationship", "tactic": "initial_access", "detect_prob": 0.15, "success_base": 0.60},
    "T1059": {"name": "Command and Scripting Interpreter", "tactic": "execution", "detect_prob": 0.40, "success_base": 0.80},
    "T1059.001": {"name": "PowerShell", "tactic": "execution", "detect_prob": 0.55, "success_base": 0.78},
    "T1059.003": {"name": "Windows Command Shell", "tactic": "execution", "detect_prob": 0.35, "success_base": 0.82},
    "T1059.004": {"name": "Unix Shell", "tactic": "execution", "detect_prob": 0.28, "success_base": 0.85},
    "T1059.007": {"name": "JavaScript", "tactic": "execution", "detect_prob": 0.45, "success_base": 0.72},
    "T1053": {"name": "Scheduled Task/Job", "tactic": "persistence", "detect_prob": 0.30, "success_base": 0.75},
    "T1543": {"name": "Create or Modify System Process", "tactic": "persistence", "detect_prob": 0.40, "success_base": 0.65},
    "T1098": {"name": "Account Manipulation", "tactic": "persistence", "detect_prob": 0.35, "success_base": 0.70},
    "T1136": {"name": "Create Account", "tactic": "persistence", "detect_prob": 0.50, "success_base": 0.60},
    "T1068": {"name": "Exploitation for Privilege Escalation", "tactic": "privesc", "detect_prob": 0.50, "success_base": 0.45},
    "T1055": {"name": "Process Injection", "tactic": "privesc", "detect_prob": 0.55, "success_base": 0.60},
    "T1548": {"name": "Abuse Elevation Control Mechanism", "tactic": "privesc", "detect_prob": 0.38, "success_base": 0.65},
    "T1134": {"name": "Access Token Manipulation", "tactic": "privesc", "detect_prob": 0.42, "success_base": 0.70},
    "T1027": {"name": "Obfuscated Files or Information", "tactic": "defense_evasion", "detect_prob": 0.35, "success_base": 0.72},
    "T1036": {"name": "Masquerading", "tactic": "defense_evasion", "detect_prob": 0.28, "success_base": 0.78},
    "T1070": {"name": "Indicator Removal", "tactic": "defense_evasion", "detect_prob": 0.22, "success_base": 0.80},
    "T1562": {"name": "Impair Defenses", "tactic": "defense_evasion", "detect_prob": 0.60, "success_base": 0.55},
    "T1003": {"name": "OS Credential Dumping", "tactic": "credential_access", "detect_prob": 0.65, "success_base": 0.70},
    "T1110": {"name": "Brute Force", "tactic": "credential_access", "detect_prob": 0.70, "success_base": 0.35},
    "T1555": {"name": "Credentials from Password Stores", "tactic": "credential_access", "detect_prob": 0.40, "success_base": 0.75},
    "T1552": {"name": "Unsecured Credentials", "tactic": "credential_access", "detect_prob": 0.20, "success_base": 0.85},
    "T1087": {"name": "Account Discovery", "tactic": "discovery", "detect_prob": 0.30, "success_base": 0.85},
    "T1018": {"name": "Remote System Discovery", "tactic": "discovery", "detect_prob": 0.35, "success_base": 0.88},
    "T1046": {"name": "Network Service Discovery", "tactic": "discovery", "detect_prob": 0.40, "success_base": 0.82},
    "T1057": {"name": "Process Discovery", "tactic": "discovery", "detect_prob": 0.15, "success_base": 0.92},
    "T1083": {"name": "File and Directory Discovery", "tactic": "discovery", "detect_prob": 0.12, "success_base": 0.94},
    "T1021": {"name": "Remote Services", "tactic": "lateral_movement", "detect_prob": 0.45, "success_base": 0.65},
    "T1021.001": {"name": "RDP", "tactic": "lateral_movement", "detect_prob": 0.50, "success_base": 0.70},
    "T1021.002": {"name": "SMB/Windows Admin Shares", "tactic": "lateral_movement", "detect_prob": 0.55, "success_base": 0.65},
    "T1021.004": {"name": "SSH", "tactic": "lateral_movement", "detect_prob": 0.38, "success_base": 0.75},
    "T1550": {"name": "Use Alternate Authentication Material", "tactic": "lateral_movement", "detect_prob": 0.40, "success_base": 0.72},
    "T1005": {"name": "Data from Local System", "tactic": "collection", "detect_prob": 0.25, "success_base": 0.88},
    "T1039": {"name": "Data from Network Shared Drive", "tactic": "collection", "detect_prob": 0.30, "success_base": 0.82},
    "T1074": {"name": "Data Staged", "tactic": "collection", "detect_prob": 0.20, "success_base": 0.90},
    "T1041": {"name": "Exfiltration Over C2 Channel", "tactic": "exfiltration", "detect_prob": 0.45, "success_base": 0.70},
    "T1048": {"name": "Exfiltration Over Alternative Protocol", "tactic": "exfiltration", "detect_prob": 0.35, "success_base": 0.75},
    "T1567": {"name": "Exfiltration Over Web Service", "tactic": "exfiltration", "detect_prob": 0.30, "success_base": 0.80},
    "T1486": {"name": "Data Encrypted for Impact", "tactic": "impact", "detect_prob": 0.75, "success_base": 0.85},
    "T1489": {"name": "Service Stop", "tactic": "impact", "detect_prob": 0.60, "success_base": 0.78},
    "T1485": {"name": "Data Destruction", "tactic": "impact", "detect_prob": 0.55, "success_base": 0.80},
}

LOLBINS = {
    "windows": {
        "user": [
            {"bin": "certutil.exe", "use": "Download files, encode/decode base64", "tid": "T1105,T1027", "evade": "high"},
            {"bin": "bitsadmin.exe", "use": "Download/upload files via BITS jobs", "tid": "T1197", "evade": "medium"},
            {"bin": "mshta.exe", "use": "Execute HTA files / remote scripts", "tid": "T1218.005", "evade": "medium"},
            {"bin": "rundll32.exe", "use": "Execute DLLs, proxy execution", "tid": "T1218.011", "evade": "high"},
            {"bin": "regsvr32.exe", "use": "COM scriptlet execution (squiblydoo)", "tid": "T1218.010", "evade": "high"},
            {"bin": "curl.exe", "use": "File download (Windows 10+ built-in)", "tid": "T1105", "evade": "medium"},
            {"bin": "wmic.exe", "use": "Remote execution, lateral movement", "tid": "T1047", "evade": "medium"},
            {"bin": "findstr.exe", "use": "Extract credentials from files/memory", "tid": "T1552", "evade": "high"},
        ],
        "admin": [
            {"bin": "psexec.exe", "use": "Remote command execution over SMB", "tid": "T1021.002,T1570", "evade": "low"},
            {"bin": "sc.exe", "use": "Create/start services for persistence", "tid": "T1543.003", "evade": "medium"},
            {"bin": "reg.exe", "use": "Query/modify registry for creds/persistence", "tid": "T1112,T1552.002", "evade": "medium"},
            {"bin": "net.exe", "use": "User/group enumeration and manipulation", "tid": "T1087,T1136", "evade": "medium"},
            {"bin": "nltest.exe", "use": "Domain trust enumeration", "tid": "T1482", "evade": "high"},
            {"bin": "ntdsutil.exe", "use": "Extract NTDS.dit (AD credentials)", "tid": "T1003.003", "evade": "low"},
            {"bin": "vssadmin.exe", "use": "Shadow copy for NTDS extraction", "tid": "T1003.003", "evade": "medium"},
        ],
        "system": [
            {"bin": "lsass.exe (dump)", "use": "Dump credentials from LSASS memory", "tid": "T1003.001", "evade": "low"},
            {"bin": "schtasks.exe", "use": "Create scheduled tasks for persistence", "tid": "T1053.005", "evade": "medium"},
        ],
    },
    "linux": {
        "user": [
            {"bin": "curl/wget", "use": "File download, C2 communication", "tid": "T1105", "evade": "high"},
            {"bin": "python3 -c", "use": "Inline script execution, shell spawn", "tid": "T1059.006", "evade": "medium"},
            {"bin": "bash -i >& /dev/tcp/", "use": "Reverse shell via bash TCP redirect", "tid": "T1059.004", "evade": "medium"},
            {"bin": "find / -perm -4000", "use": "Discover SUID binaries for privesc", "tid": "T1548.001", "evade": "high"},
            {"bin": "history", "use": "Extract credentials from command history", "tid": "T1552", "evade": "high"},
        ],
        "root": [
            {"bin": "ssh-keygen + authorized_keys", "use": "Backdoor SSH with attacker key", "tid": "T1098.004", "evade": "medium"},
            {"bin": "systemctl", "use": "Create persistent services", "tid": "T1543.002", "evade": "medium"},
            {"bin": "docker/kubectl (if present)", "use": "Container escape, lateral movement", "tid": "T1611", "evade": "medium"},
        ],
    },
    "macos": {
        "user": [
            {"bin": "osascript", "use": "AppleScript execution, phishing dialogs", "tid": "T1059.002", "evade": "medium"},
            {"bin": "curl", "use": "File download, C2 communication", "tid": "T1105", "evade": "high"},
            {"bin": "launchctl", "use": "LaunchAgent persistence", "tid": "T1543.001", "evade": "medium"},
            {"bin": "security", "use": "Keychain credential extraction", "tid": "T1555.001", "evade": "low"},
        ],
        "root": [
            {"bin": "dscl", "use": "Directory Service enumeration/user creation", "tid": "T1087,T1136", "evade": "high"},
        ],
    },
}

DEFENDER_PROFILES = {
    "startup": {"soc_24x7": False, "edr_coverage": 0.50, "log_retention_days": 14, "patch_lag_days": 45, "alert_fatigue_factor": 0.80, "low_watch_hours": [22,23,0,1,2,3,4,5,6], "high_watch_hours": [9,10,11,14,15,16], "incident_response_hours": 8, "notes": "Lean security team, likely reactive."},
    "smb": {"soc_24x7": False, "edr_coverage": 0.65, "log_retention_days": 30, "patch_lag_days": 30, "alert_fatigue_factor": 0.65, "low_watch_hours": [22,23,0,1,2,3,4,5,6,7,8], "high_watch_hours": [9,10,11,14,15,16], "incident_response_hours": 4, "notes": "MSP-managed, partial EDR."},
    "enterprise": {"soc_24x7": True, "edr_coverage": 0.90, "log_retention_days": 365, "patch_lag_days": 14, "alert_fatigue_factor": 0.40, "low_watch_hours": [3,4,5], "high_watch_hours": list(range(7,22)), "incident_response_hours": 1, "notes": "24x7 SOC, high EDR coverage."},
    "healthcare": {"soc_24x7": False, "edr_coverage": 0.60, "log_retention_days": 90, "patch_lag_days": 60, "alert_fatigue_factor": 0.75, "low_watch_hours": [22,23,0,1,2,3,4,5,6], "high_watch_hours": [8,9,10,14,15,16], "incident_response_hours": 6, "notes": "Compliance-heavy, resource-constrained."},
    "financial": {"soc_24x7": True, "edr_coverage": 0.95, "log_retention_days": 730, "patch_lag_days": 7, "alert_fatigue_factor": 0.30, "low_watch_hours": [2,3,4], "high_watch_hours": list(range(6,23)), "incident_response_hours": 0.5, "notes": "Highest maturity, regulatory oversight."},
    "government": {"soc_24x7": True, "edr_coverage": 0.80, "log_retention_days": 180, "patch_lag_days": 21, "alert_fatigue_factor": 0.50, "low_watch_hours": [23,0,1,2,3,4], "high_watch_hours": list(range(8,19)), "incident_response_hours": 2, "notes": "24x7 but bureaucratic response."},
}

@dataclass
class OSINTFinding:
    source: str
    finding_type: str
    value: str
    confidence: float
    notes: str = ""

@dataclass
class AttackNode:
    technique_id: str
    technique_name: str
    tactic: str
    success_prob: float
    detect_prob: float
    stealth_score: float
    notes: str = ""

@dataclass
class KillChain:
    chain_id: str
    engagement_id: str
    nodes: list = field(default_factory=list)
    cumulative_success: float = 0.0
    cumulative_detection_risk: float = 0.0
    stealth_score: float = 0.0
    objective: str = "crown_jewels"

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS engagements (
            id TEXT PRIMARY KEY, target TEXT NOT NULL, org TEXT,
            scope TEXT, defender_profile TEXT DEFAULT 'smb',
            created_at TEXT NOT NULL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS osint_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engagement_id TEXT NOT NULL, source TEXT NOT NULL,
            finding_type TEXT NOT NULL, value TEXT NOT NULL,
            confidence REAL DEFAULT 0.5, notes TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attack_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engagement_id TEXT NOT NULL, technique_id TEXT NOT NULL,
            technique_name TEXT NOT NULL, tactic TEXT NOT NULL,
            success_prob REAL NOT NULL, detect_prob REAL NOT NULL,
            stealth_score REAL NOT NULL, notes TEXT
        );
        CREATE TABLE IF NOT EXISTS kill_chains (
            id TEXT PRIMARY KEY, engagement_id TEXT NOT NULL,
            chain_json TEXT NOT NULL, cumulative_success REAL,
            cumulative_detection_risk REAL, stealth_score REAL,
            objective TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS narratives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engagement_id TEXT NOT NULL, narrative_text TEXT NOT NULL,
            generated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn

def now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

class PassiveOSINT:
    def __init__(self, engagement_id, target, db):
        self.engagement_id = engagement_id
        self.target = target
        self.db = db
        self.findings = []

    def _save(self, f):
        self.findings.append(f)
        self.db.execute(
            "INSERT INTO osint_findings (engagement_id,source,finding_type,value,confidence,notes,created_at) VALUES (?,?,?,?,?,?,?)",
            (self.engagement_id, f.source, f.finding_type, f.value, f.confidence, f.notes, now_iso()))
        self.db.commit()

    def cert_transparency(self):
        print(f"  [OSINT] Certificate transparency: {self.target}")
        try:
            url = f"https://crt.sh/?q=%.{self.target}&output=json"
            req = urllib.request.Request(url, headers={"User-Agent": "PhantomGraph/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            subs = set()
            for e in data[:200]:
                for s in e.get("name_value","").split("\n"):
                    s = s.strip().lstrip("*.")
                    if s.endswith(self.target) and s != self.target:
                        subs.add(s)
            for s in subs:
                self._save(OSINTFinding("crt.sh","subdomain",s,0.95,"cert transparency"))
            print(f"    -> {len(subs)} subdomains")
        except Exception as e:
            print(f"    -> crt.sh unavailable: {e}")

    def dns_enumeration(self):
        print(f"  [OSINT] DNS: {self.target}")
        for prefix in ["www","mail","smtp","vpn","remote","api","dev","staging","admin","portal","git","jenkins","jira"]:
            fqdn = f"{prefix}.{self.target}"
            try:
                ips = list({r[4][0] for r in socket.getaddrinfo(fqdn, None)})
                self._save(OSINTFinding("dns","dns_record",f"{fqdn} -> {ips[0]}",0.99,""))
            except Exception:
                pass

    def infer_tech_stack(self):
        self._save(OSINTFinding("inference","recon_note","Query LinkedIn jobs for SIEM/EDR tech stack clues",0.90,""))
        self._save(OSINTFinding("inference","recon_note","Check GitHub org for credential leaks",0.80,""))
        self._save(OSINTFinding("breach_intel","recommendation",f"Query HaveIBeenPwned for {self.target} domain",0.95,""))

    def run_all(self):
        self.cert_transparency()
        self.dns_enumeration()
        self.infer_tech_stack()
        print(f"\n  [OSINT] Total findings: {len(self.findings)}")
        return self.findings

class AttackGraphBuilder:
    TACTIC_ORDER = ["recon","initial_access","execution","persistence","privesc","defense_evasion","credential_access","discovery","lateral_movement","collection","exfiltration","impact"]
    TRANSITIONS = {
        "recon": ["initial_access"],
        "initial_access": ["execution","persistence"],
        "execution": ["persistence","privesc","defense_evasion","discovery"],
        "persistence": ["privesc","defense_evasion"],
        "privesc": ["defense_evasion","credential_access","discovery"],
        "defense_evasion": ["credential_access","discovery","lateral_movement"],
        "credential_access": ["lateral_movement","collection"],
        "discovery": ["lateral_movement","collection","credential_access"],
        "lateral_movement": ["discovery","collection","exfiltration","impact"],
        "collection": ["exfiltration"],
        "exfiltration": ["impact"],
        "impact": [],
    }

    def __init__(self, engagement_id, defender_profile, db):
        self.engagement_id = engagement_id
        self.profile = DEFENDER_PROFILES.get(defender_profile, DEFENDER_PROFILES["smb"])
        self.db = db
        self.nodes = {}

    def _adjusted_detect(self, base):
        edr = self.profile["edr_coverage"]
        fatigue = self.profile["alert_fatigue_factor"]
        return min(base * edr * (1.0 - fatigue * 0.3), 0.99)

    def build(self):
        for tid, tech in ATTACK_TECHNIQUES.items():
            adj = self._adjusted_detect(tech["detect_prob"])
            node = AttackNode(tid, tech["name"], tech["tactic"], tech["success_base"], adj, 1.0 - adj)
            self.nodes[tid] = node
            self.db.execute(
                "INSERT OR REPLACE INTO attack_nodes (engagement_id,technique_id,technique_name,tactic,success_prob,detect_prob,stealth_score,notes) VALUES (?,?,?,?,?,?,?,?)",
                (self.engagement_id, tid, tech["name"], tech["tactic"], node.success_prob, node.detect_prob, node.stealth_score, ""))
        self.db.commit()
        return self.nodes

    def edges(self, node):
        return [n for n in self.nodes.values() if n.tactic in self.TRANSITIONS.get(node.tactic, [])]

class KillChainOptimizer:
    def __init__(self, engagement_id, graph, objective="data_exfiltration", db=None):
        self.engagement_id = engagement_id
        self.graph = graph
        self.objective = objective
        self.db = db

    def _score(self, node, penalty=1.5):
        return math.log(max(node.success_prob,1e-6)) - penalty * math.log(max(1-node.stealth_score,1e-6))

    def _chain_score(self, chain):
        cs, cd = 1.0, 0.0
        for n in chain:
            cs *= n.success_prob
            cd = 1.0 - (1.0 - cd) * (1.0 - n.detect_prob)
        return cs, cd, 1.0 - cd

    def find_chains(self, top_n=5, max_depth=7):
        obj_tactic = {"data_exfiltration":"exfiltration","ransomware":"impact","persistence":"persistence","credential_theft":"credential_access","lateral_spread":"lateral_movement","crown_jewels":"impact"}.get(self.objective,"exfiltration")
        beam = [(self._score(n), [n]) for n in self.graph.nodes.values() if n.tactic == "recon"]
        beam.sort(key=lambda x: -x[0])
        beam = beam[:top_n*3]
        completed, iters = [], 0
        while beam and iters < 500:
            iters += 1
            nb = []
            for score, path in beam:
                last = path[-1]
                if last.tactic == obj_tactic or len(path) >= max_depth:
                    completed.append((score, path)); continue
                nexts = self.graph.edges(last)
                if not nexts:
                    completed.append((score, path)); continue
                for nxt in nexts:
                    if nxt.tactic in {n.tactic for n in path}: continue
                    nb.append((score + self._score(nxt), path + [nxt]))
            nb.sort(key=lambda x: -x[0])
            beam = nb[:top_n*4]
        seen, chains = set(), []
        for _, path in sorted(completed, key=lambda x: -x[0]):
            seq = tuple(n.tactic for n in path)
            if seq in seen: continue
            seen.add(seq)
            cs, cd, st = self._chain_score(path)
            cid = hashlib.sha1(":".join(n.technique_id for n in path).encode()).hexdigest()[:12]
            kc = KillChain(cid, self.engagement_id, [asdict(n) for n in path], round(cs,4), round(cd,4), round(st,4), self.objective)
            chains.append(kc)
            if len(chains) >= top_n: break
        if self.db:
            for kc in chains:
                self.db.execute("INSERT OR REPLACE INTO kill_chains (id,engagement_id,chain_json,cumulative_success,cumulative_detection_risk,stealth_score,objective,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (kc.chain_id, kc.engagement_id, json.dumps(kc.nodes), kc.cumulative_success, kc.cumulative_detection_risk, kc.stealth_score, kc.objective, now_iso()))
            self.db.commit()
        return chains

class DefenderModel:
    def __init__(self, name):
        self.name = name
        self.profile = DEFENDER_PROFILES.get(name, DEFENDER_PROFILES["smb"])

    def optimal_operation_windows(self):
        out = []
        for h in self.profile["low_watch_hours"]:
            base = 0.05 if self.profile["soc_24x7"] else 0.02
            risk = base * (1.0 - self.profile["alert_fatigue_factor"] * 0.5)
            out.append({"hour_utc": h, "detection_risk_modifier": round(risk,3), "label": f"{h:02d}:00 UTC"})
        return out

    def evasion_recommendations(self, kc):
        recs = []
        if self.profile["edr_coverage"] > 0.85:
            recs += ["Avoid LOLBins commonly logged; prefer memory-resident techniques", "Use process hollowing or DLL hijacking"]
        if self.profile["soc_24x7"]:
            recs += ["Operate in small bursts", "Space actions across sessions"]
        recs.append(f"Optimal UTC hours: {self.profile['low_watch_hours'][:3]}")
        return recs

    def report(self):
        p = self.profile
        return "\n".join([
            f"\n=== Defender Model: {self.name.upper()} ===",
            f"24x7 SOC: {'YES' if p['soc_24x7'] else 'NO'}  EDR: {int(p['edr_coverage']*100)}%  Patch lag: {p['patch_lag_days']}d  IR: {p['incident_response_hours']}h",
            f"Notes: {p['notes']}",
        ])

def lotl_advisor(os_type, priv_level):
    os_type, priv_level = os_type.lower(), priv_level.lower()
    if os_type not in LOLBINS: return f"No LotL data for {os_type}"
    bins = LOLBINS[os_type].get(priv_level, [])
    if not bins: return f"No LotL for {os_type}/{priv_level}"
    lines = [f"\n=== LotL: {os_type.upper()}/{priv_level.upper()} ==="]
    for b in bins:
        lines.append(f"  [{b['evade']:>6}] {b['bin']:<35} {b['tid']:<20} {b['use']}")
    return "\n".join(lines)

class NarrativeEngine:
    def __init__(self, engagement_id, db):
        self.engagement_id = engagement_id
        self.db = db

    def generate(self):
        eng = self.db.execute("SELECT * FROM engagements WHERE id=?", (self.engagement_id,)).fetchone()
        if not eng: return "Engagement not found."
        findings = self.db.execute("SELECT * FROM osint_findings WHERE engagement_id=? ORDER BY confidence DESC", (self.engagement_id,)).fetchall()
        chains = self.db.execute("SELECT * FROM kill_chains WHERE engagement_id=? ORDER BY stealth_score DESC LIMIT 3", (self.engagement_id,)).fetchall()
        defender = DefenderModel(eng["defender_profile"] or "smb")
        lines = ["="*70, "PHANTOM GRAPH — RED TEAM OPERATOR BRIEFING",
                 f"Target: {eng['target']}  Org: {eng['org']}  Generated: {now_iso()}",
                 "="*70, "", "RECON SUMMARY", "-"*40]
        subs = [f for f in findings if f["finding_type"]=="subdomain"]
        dns = [f for f in findings if f["finding_type"]=="dns_record"]
        lines.append(f"Subdomains: {len(subs)}  DNS records: {len(dns)}")
        for f in subs[:5]: lines.append(f"  * {f['value']}")
        lines += ["", "TOP KILL CHAINS", "-"*40]
        for i, c in enumerate(chains, 1):
            nodes = json.loads(c["chain_json"])
            lines.append(f"Chain #{i}: stealth={c['stealth_score']:.0%} success={c['cumulative_success']:.0%}")
            for j, n in enumerate(nodes):
                lines.append(f"  {'*' if j==0 else '->'} [{n['tactic']:20}] {n['technique_id']} {n['technique_name']}")
        lines += ["", defender.report()]
        narrative = "\n".join(lines)
        self.db.execute("INSERT INTO narratives (engagement_id,narrative_text,generated_at) VALUES (?,?,?)", (self.engagement_id, narrative, now_iso()))
        self.db.commit()
        return narrative

def cmd_scope(args, db):
    eid = args.id or f"ENG-{hashlib.sha1(f'{args.target}{now_iso()}'.encode()).hexdigest()[:6].upper()}"
    db.execute("INSERT OR REPLACE INTO engagements (id,target,org,scope,defender_profile,created_at,notes) VALUES (?,?,?,?,?,?,?)",
               (eid, args.target, args.org or "", args.scope or "full", args.defender, now_iso(), args.notes or ""))
    db.commit()
    print(f"\n[+] Engagement: {eid}")
    if not args.no_osint:
        PassiveOSINT(eid, args.target, db).run_all()

def cmd_graph(args, db):
    eng = db.execute("SELECT * FROM engagements WHERE id=?", (args.engagement_id,)).fetchone()
    if not eng: print("[-] Not found"); return
    b = AttackGraphBuilder(args.engagement_id, eng["defender_profile"], db)
    nodes = b.build()
    print(f"[+] {len(nodes)} nodes built")

def cmd_paths(args, db):
    eng = db.execute("SELECT * FROM engagements WHERE id=?", (args.engagement_id,)).fetchone()
    if not eng: print("[-] Not found"); return
    b = AttackGraphBuilder(args.engagement_id, eng["defender_profile"], db)
    b.build()
    chains = KillChainOptimizer(args.engagement_id, b, args.objective, db).find_chains(args.top)
    for i, kc in enumerate(chains, 1):
        print(f"\nChain #{i} stealth={kc.stealth_score:.0%} success={kc.cumulative_success:.0%}")
        for j, n in enumerate(kc.nodes):
            print(f"  {'>' if j else '*'} {n['tactic']:20} {n['technique_id']} {n['technique_name']}")

def cmd_narrative(args, db):
    eng = db.execute("SELECT * FROM engagements WHERE id=?", (args.engagement_id,)).fetchone()
    if not eng: print("[-] Not found"); return
    if not db.execute("SELECT COUNT(*) FROM kill_chains WHERE engagement_id=?", (args.engagement_id,)).fetchone()[0]:
        b = AttackGraphBuilder(args.engagement_id, eng["defender_profile"], db)
        b.build()
        KillChainOptimizer(args.engagement_id, b, "data_exfiltration", db).find_chains(5)
    n = NarrativeEngine(args.engagement_id, db).generate()
    print(n)
    if args.output: Path(args.output).write_text(n); print(f"[+] Saved: {args.output}")

def cmd_defender(args, db):
    print(DefenderModel(args.profile or "smb").report())

def cmd_lotl(args, db):
    print(lotl_advisor(args.os, args.priv))

def cmd_list(args, db):
    for r in db.execute("SELECT id,target,org,defender_profile,created_at FROM engagements ORDER BY created_at DESC").fetchall():
        print(f"{r['id']:<15} {r['target']:<30} {r['defender_profile']:<12} {r['created_at'][:19]}")

def main():
    print(BANNER)
    p = argparse.ArgumentParser(prog="phantom_graph")
    sub = p.add_subparsers(dest="command")
    s = sub.add_parser("scope"); s.add_argument("--target",required=True); s.add_argument("--org"); s.add_argument("--scope"); s.add_argument("--id"); s.add_argument("--defender",default="smb",choices=list(DEFENDER_PROFILES.keys())); s.add_argument("--notes"); s.add_argument("--no-osint",action="store_true")
    g = sub.add_parser("graph"); g.add_argument("--engagement-id",required=True)
    pa = sub.add_parser("paths"); pa.add_argument("--engagement-id",required=True); pa.add_argument("--top",type=int,default=5); pa.add_argument("--objective",default="data_exfiltration",choices=["data_exfiltration","ransomware","persistence","credential_theft","lateral_spread","crown_jewels"])
    n = sub.add_parser("narrative"); n.add_argument("--engagement-id",required=True); n.add_argument("--output")
    d = sub.add_parser("defender"); d.add_argument("--profile",choices=list(DEFENDER_PROFILES.keys())); d.add_argument("--engagement-id")
    l = sub.add_parser("lotl"); l.add_argument("--os",required=True,choices=list(LOLBINS.keys())); l.add_argument("--priv",required=True)
    sub.add_parser("list")
    args = p.parse_args()
    if not args.command: p.print_help(); return
    db = init_db(DB_PATH)
    {"scope":cmd_scope,"graph":cmd_graph,"paths":cmd_paths,"narrative":cmd_narrative,"defender":cmd_defender,"lotl":cmd_lotl,"list":cmd_list}[args.command](args, db)

if __name__ == "__main__":
    main()
