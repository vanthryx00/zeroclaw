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
  ██████╗ ██╗  ██╗ █████╗ ███╗   ██╗████████╗ ██████╗ ███╗   ███╗
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
# MITRE ATT&CK technique catalog (curated subset, TA + technique + subtechnique)
# ---------------------------------------------------------------------------
ATTACK_TECHNIQUES = {
    # Reconnaissance
    "T1590": {"name": "Gather Victim Network Information", "tactic": "recon", "detect_prob": 0.05, "success_base": 0.92},
    "T1589": {"name": "Gather Victim Identity Information", "tactic": "recon", "detect_prob": 0.04, "success_base": 0.90},
    "T1596": {"name": "Search Open Technical Databases", "tactic": "recon", "detect_prob": 0.02, "success_base": 0.95},
    "T1598": {"name": "Phishing for Information", "tactic": "recon", "detect_prob": 0.20, "success_base": 0.55},
    # Initial Access
    "T1566": {"name": "Phishing", "tactic": "initial_access", "detect_prob": 0.35, "success_base": 0.50},
    "T1190": {"name": "Exploit Public-Facing Application", "tactic": "initial_access", "detect_prob": 0.45, "success_base": 0.40},
    "T1133": {"name": "External Remote Services", "tactic": "initial_access", "detect_prob": 0.30, "success_base": 0.55},
    "T1078": {"name": "Valid Accounts", "tactic": "initial_access", "detect_prob": 0.25, "success_base": 0.70},
    "T1199": {"name": "Trusted Relationship", "tactic": "initial_access", "detect_prob": 0.15, "success_base": 0.60},
    # Execution
    "T1059": {"name": "Command and Scripting Interpreter", "tactic": "execution", "detect_prob": 0.40, "success_base": 0.80},
    "T1059.001": {"name": "PowerShell", "tactic": "execution", "detect_prob": 0.55, "success_base": 0.78},
    "T1059.003": {"name": "Windows Command Shell", "tactic": "execution", "detect_prob": 0.35, "success_base": 0.82},
    "T1059.004": {"name": "Unix Shell", "tactic": "execution", "detect_prob": 0.28, "success_base": 0.85},
    "T1059.007": {"name": "JavaScript", "tactic": "execution", "detect_prob": 0.45, "success_base": 0.72},
    # Persistence
    "T1053": {"name": "Scheduled Task/Job", "tactic": "persistence", "detect_prob": 0.30, "success_base": 0.75},
    "T1543": {"name": "Create or Modify System Process", "tactic": "persistence", "detect_prob": 0.40, "success_base": 0.65},
    "T1098": {"name": "Account Manipulation", "tactic": "persistence", "detect_prob": 0.35, "success_base": 0.70},
    "T1136": {"name": "Create Account", "tactic": "persistence", "detect_prob": 0.50, "success_base": 0.60},
    # Privilege Escalation
    "T1068": {"name": "Exploitation for Privilege Escalation", "tactic": "privesc", "detect_prob": 0.50, "success_base": 0.45},
    "T1055": {"name": "Process Injection", "tactic": "privesc", "detect_prob": 0.55, "success_base": 0.60},
    "T1548": {"name": "Abuse Elevation Control Mechanism", "tactic": "privesc", "detect_prob": 0.38, "success_base": 0.65},
    "T1134": {"name": "Access Token Manipulation", "tactic": "privesc", "detect_prob": 0.42, "success_base": 0.70},
    # Defense Evasion
    "T1027": {"name": "Obfuscated Files or Information", "tactic": "defense_evasion", "detect_prob": 0.35, "success_base": 0.72},
    "T1036": {"name": "Masquerading", "tactic": "defense_evasion", "detect_prob": 0.28, "success_base": 0.78},
    "T1070": {"name": "Indicator Removal", "tactic": "defense_evasion", "detect_prob": 0.22, "success_base": 0.80},
    "T1562": {"name": "Impair Defenses", "tactic": "defense_evasion", "detect_prob": 0.60, "success_base": 0.55},
    # Credential Access
    "T1003": {"name": "OS Credential Dumping", "tactic": "credential_access", "detect_prob": 0.65, "success_base": 0.70},
    "T1110": {"name": "Brute Force", "tactic": "credential_access", "detect_prob": 0.70, "success_base": 0.35},
    "T1555": {"name": "Credentials from Password Stores", "tactic": "credential_access", "detect_prob": 0.40, "success_base": 0.75},
    "T1552": {"name": "Unsecured Credentials", "tactic": "credential_access", "detect_prob": 0.20, "success_base": 0.85},
    # Discovery
    "T1087": {"name": "Account Discovery", "tactic": "discovery", "detect_prob": 0.30, "success_base": 0.85},
    "T1018": {"name": "Remote System Discovery", "tactic": "discovery", "detect_prob": 0.35, "success_base": 0.88},
    "T1046": {"name": "Network Service Discovery", "tactic": "discovery", "detect_prob": 0.40, "success_base": 0.82},
    "T1057": {"name": "Process Discovery", "tactic": "discovery", "detect_prob": 0.15, "success_base": 0.92},
    "T1083": {"name": "File and Directory Discovery", "tactic": "discovery", "detect_prob": 0.12, "success_base": 0.94},
    # Lateral Movement
    "T1021": {"name": "Remote Services", "tactic": "lateral_movement", "detect_prob": 0.45, "success_base": 0.65},
    "T1021.001": {"name": "RDP", "tactic": "lateral_movement", "detect_prob": 0.50, "success_base": 0.70},
    "T1021.002": {"name": "SMB/Windows Admin Shares", "tactic": "lateral_movement", "detect_prob": 0.55, "success_base": 0.65},
    "T1021.004": {"name": "SSH", "tactic": "lateral_movement", "detect_prob": 0.38, "success_base": 0.75},
    "T1550": {"name": "Use Alternate Authentication Material", "tactic": "lateral_movement", "detect_prob": 0.40, "success_base": 0.72},
    # Collection
    "T1005": {"name": "Data from Local System", "tactic": "collection", "detect_prob": 0.25, "success_base": 0.88},
    "T1039": {"name": "Data from Network Shared Drive", "tactic": "collection", "detect_prob": 0.30, "success_base": 0.82},
    "T1074": {"name": "Data Staged", "tactic": "collection", "detect_prob": 0.20, "success_base": 0.90},
    # Exfiltration
    "T1041": {"name": "Exfiltration Over C2 Channel", "tactic": "exfiltration", "detect_prob": 0.45, "success_base": 0.70},
    "T1048": {"name": "Exfiltration Over Alternative Protocol", "tactic": "exfiltration", "detect_prob": 0.35, "success_base": 0.75},
    "T1567": {"name": "Exfiltration Over Web Service", "tactic": "exfiltration", "detect_prob": 0.30, "success_base": 0.80},
    # Impact
    "T1486": {"name": "Data Encrypted for Impact", "tactic": "impact", "detect_prob": 0.75, "success_base": 0.85},
    "T1489": {"name": "Service Stop", "tactic": "impact", "detect_prob": 0.60, "success_base": 0.78},
    "T1485": {"name": "Data Destruction", "tactic": "impact", "detect_prob": 0.55, "success_base": 0.80},
}

# ---------------------------------------------------------------------------
# Living-off-the-land binary catalog
# ---------------------------------------------------------------------------
LOLBINS = {
    "windows": {
        "user": [
            {"bin": "certutil.exe", "use": "Download files, encode/decode base64", "tid": "T1105,T1027", "evade": "high"},
            {"bin": "bitsadmin.exe", "use": "Download/upload files via BITS jobs", "tid": "T1197", "evade": "medium"},
            {"bin": "mshta.exe", "use": "Execute HTA files / remote scripts", "tid": "T1218.005", "evade": "medium"},
            {"bin": "wscript.exe", "use": "Execute VBScript/JScript", "tid": "T1059.005", "evade": "medium"},
            {"bin": "rundll32.exe", "use": "Execute DLLs, proxy execution", "tid": "T1218.011", "evade": "high"},
            {"bin": "regsvr32.exe", "use": "COM scriptlet execution (squiblydoo)", "tid": "T1218.010", "evade": "high"},
            {"bin": "powershell.exe -enc", "use": "Base64-encoded commands, bypass logging", "tid": "T1059.001", "evade": "low"},
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
            {"bin": "dsquery.exe", "use": "Active Directory enumeration", "tid": "T1018,T1069", "evade": "high"},
            {"bin": "ntdsutil.exe", "use": "Extract NTDS.dit (AD credentials)", "tid": "T1003.003", "evade": "low"},
            {"bin": "vssadmin.exe", "use": "Shadow copy for NTDS extraction", "tid": "T1003.003", "evade": "medium"},
        ],
        "system": [
            {"bin": "lsass.exe (dump)", "use": "Dump credentials from LSASS memory", "tid": "T1003.001", "evade": "low"},
            {"bin": "schtasks.exe", "use": "Create scheduled tasks for persistence", "tid": "T1053.005", "evade": "medium"},
            {"bin": "at.exe", "use": "Legacy scheduler, sometimes less monitored", "tid": "T1053.002", "evade": "high"},
        ],
    },
    "linux": {
        "user": [
            {"bin": "curl/wget", "use": "File download, C2 communication", "tid": "T1105", "evade": "high"},
            {"bin": "python3 -c", "use": "Inline script execution, shell spawn", "tid": "T1059.006", "evade": "medium"},
            {"bin": "bash -i >& /dev/tcp/", "use": "Reverse shell via bash TCP redirect", "tid": "T1059.004", "evade": "medium"},
            {"bin": "nc/ncat", "use": "Bind/reverse shell, file transfer", "tid": "T1059.004", "evade": "medium"},
            {"bin": "find / -perm -4000", "use": "Discover SUID binaries for privesc", "tid": "T1548.001", "evade": "high"},
            {"bin": "env", "use": "Environment variable extraction", "tid": "T1552.007", "evade": "high"},
            {"bin": "crontab -l", "use": "Enumerate scheduled tasks", "tid": "T1053.003", "evade": "high"},
            {"bin": "history", "use": "Extract credentials from command history", "tid": "T1552", "evade": "high"},
        ],
        "root": [
            {"bin": "iptables", "use": "Firewall rule manipulation, persistence", "tid": "T1562.004", "evade": "medium"},
            {"bin": "ssh-keygen + authorized_keys", "use": "Backdoor SSH with attacker key", "tid": "T1098.004", "evade": "medium"},
            {"bin": "passwd/chpasswd", "use": "Modify user passwords", "tid": "T1098", "evade": "medium"},
            {"bin": "systemctl", "use": "Create persistent services", "tid": "T1543.002", "evade": "medium"},
            {"bin": "/proc/mem (ptrace)", "use": "Credential extraction from process memory", "tid": "T1003", "evade": "low"},
            {"bin": "chroot", "use": "Escape container if misconfigured", "tid": "T1611", "evade": "medium"},
            {"bin": "docker/kubectl (if present)", "use": "Container escape, lateral movement", "tid": "T1611", "evade": "medium"},
        ],
    },
    "macos": {
        "user": [
            {"bin": "osascript", "use": "AppleScript execution, phishing dialogs", "tid": "T1059.002", "evade": "medium"},
            {"bin": "curl", "use": "File download, C2 communication", "tid": "T1105", "evade": "high"},
            {"bin": "launchctl", "use": "LaunchAgent persistence", "tid": "T1543.001", "evade": "medium"},
            {"bin": "security", "use": "Keychain credential extraction", "tid": "T1555.001", "evade": "low"},
            {"bin": "plutil", "use": "Modify plist for persistence", "tid": "T1543.001", "evade": "high"},
            {"bin": "python3 -c", "use": "Inline script, shell spawn", "tid": "T1059.006", "evade": "medium"},
        ],
        "root": [
            {"bin": "dscl", "use": "Directory Service enumeration/user creation", "tid": "T1087,T1136", "evade": "high"},
            {"bin": "diskutil", "use": "Volume manipulation", "tid": "T1561", "evade": "medium"},
            {"bin": "systemextensionsctl", "use": "Load persistent kernel extension", "tid": "T1547.011", "evade": "low"},
        ],
    },
}

# Defender fatigue model: organizations often have predictable monitoring patterns
DEFENDER_PROFILES = {
    "startup": {
        "soc_24x7": False,
        "edr_coverage": 0.50,
        "log_retention_days": 14,
        "patch_lag_days": 45,
        "alert_fatigue_factor": 0.80,
        "low_watch_hours": [22, 23, 0, 1, 2, 3, 4, 5, 6],
        "high_watch_hours": [9, 10, 11, 14, 15, 16],
        "incident_response_hours": 8,
        "notes": "Lean security team, likely reactive. EDR partial. Patch lag high.",
    },
    "smb": {
        "soc_24x7": False,
        "edr_coverage": 0.65,
        "log_retention_days": 30,
        "patch_lag_days": 30,
        "alert_fatigue_factor": 0.65,
        "low_watch_hours": [22, 23, 0, 1, 2, 3, 4, 5, 6, 7, 8],
        "high_watch_hours": [9, 10, 11, 14, 15, 16],
        "incident_response_hours": 4,
        "notes": "Typical SMB: MSP-managed, partial EDR, weekday daytime monitoring.",
    },
    "enterprise": {
        "soc_24x7": True,
        "edr_coverage": 0.90,
        "log_retention_days": 365,
        "patch_lag_days": 14,
        "alert_fatigue_factor": 0.40,
        "low_watch_hours": [3, 4, 5],
        "high_watch_hours": list(range(7, 22)),
        "incident_response_hours": 1,
        "notes": "24x7 SOC, high EDR coverage, short patch lag. Harder target.",
    },
    "healthcare": {
        "soc_24x7": False,
        "edr_coverage": 0.60,
        "log_retention_days": 90,
        "patch_lag_days": 60,
        "alert_fatigue_factor": 0.75,
        "low_watch_hours": [22, 23, 0, 1, 2, 3, 4, 5, 6],
        "high_watch_hours": [8, 9, 10, 14, 15, 16],
        "incident_response_hours": 6,
        "notes": "Compliance-heavy but resource-constrained. Patch lag extreme for medical devices.",
    },
    "financial": {
        "soc_24x7": True,
        "edr_coverage": 0.95,
        "log_retention_days": 730,
        "patch_lag_days": 7,
        "alert_fatigue_factor": 0.30,
        "low_watch_hours": [2, 3, 4],
        "high_watch_hours": list(range(6, 23)),
        "incident_response_hours": 0.5,
        "notes": "Highest maturity: near-real-time monitoring, minimal blind spots, regulatory oversight.",
    },
    "government": {
        "soc_24x7": True,
        "edr_coverage": 0.80,
        "log_retention_days": 180,
        "patch_lag_days": 21,
        "alert_fatigue_factor": 0.50,
        "low_watch_hours": [23, 0, 1, 2, 3, 4],
        "high_watch_hours": list(range(8, 19)),
        "incident_response_hours": 2,
        "notes": "24x7 but bureaucratic response. CISA compliance drives partial hardening.",
    },
}

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

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
    stealth_score: float  # 1 - detect_prob
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

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS engagements (
            id TEXT PRIMARY KEY,
            target TEXT NOT NULL,
            org TEXT,
            scope TEXT,
            defender_profile TEXT DEFAULT 'smb',
            created_at TEXT NOT NULL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS osint_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engagement_id TEXT NOT NULL,
            source TEXT NOT NULL,
            finding_type TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (engagement_id) REFERENCES engagements(id)
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
            notes TEXT,
            FOREIGN KEY (engagement_id) REFERENCES engagements(id)
        );
        CREATE TABLE IF NOT EXISTS kill_chains (
            id TEXT PRIMARY KEY,
            engagement_id TEXT NOT NULL,
            chain_json TEXT NOT NULL,
            cumulative_success REAL,
            cumulative_detection_risk REAL,
            stealth_score REAL,
            objective TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (engagement_id) REFERENCES engagements(id)
        );
        CREATE TABLE IF NOT EXISTS narratives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            engagement_id TEXT NOT NULL,
            narrative_text TEXT NOT NULL,
            generated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn


def now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"

# ---------------------------------------------------------------------------
# Passive OSINT engine
# ---------------------------------------------------------------------------

class PassiveOSINT:
    """Passive-only reconnaissance: no active scanning, no packets to target."""

    def __init__(self, engagement_id: str, target: str, db: sqlite3.Connection):
        self.engagement_id = engagement_id
        self.target = target
        self.db = db
        self.findings: list[OSINTFinding] = []

    def _save(self, f: OSINTFinding):
        self.findings.append(f)
        self.db.execute(
            "INSERT INTO osint_findings (engagement_id, source, finding_type, value, confidence, notes, created_at) VALUES (?,?,?,?,?,?,?)",
            (self.engagement_id, f.source, f.finding_type, f.value, f.confidence, f.notes, now_iso()),
        )
        self.db.commit()

    def cert_transparency(self):
        """Query crt.sh for certificate transparency logs — fully passive."""
        print(f"  [OSINT] Certificate transparency: {self.target}")
        try:
            url = f"https://crt.sh/?q=%.{self.target}&output=json"
            req = urllib.request.Request(url, headers={"User-Agent": "PhantomGraph/1.0 (authorized assessment)"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            subdomains = set()
            for entry in data[:200]:
                name = entry.get("name_value", "")
                for sub in name.split("\n"):
                    sub = sub.strip().lstrip("*.")
                    if sub.endswith(self.target) and sub != self.target:
                        subdomains.add(sub)
            for sub in subdomains:
                self._save(OSINTFinding(
                    source="crt.sh",
                    finding_type="subdomain",
                    value=sub,
                    confidence=0.95,
                    notes="Certificate transparency log entry",
                ))
            print(f"    → {len(subdomains)} unique subdomains discovered")
        except Exception as e:
            print(f"    → crt.sh unavailable ({e})")

    def dns_enumeration(self):
        """Basic DNS lookups against target — low-noise, no port scanning."""
        print(f"  [OSINT] DNS enumeration: {self.target}")
        common_prefixes = ["www", "mail", "smtp", "vpn", "remote", "api", "dev", "staging",
                           "admin", "portal", "owa", "autodiscover", "ftp", "ssh", "git",
                           "jira", "confluence", "jenkins", "gitlab", "helpdesk", "support"]
        for prefix in common_prefixes:
            fqdn = f"{prefix}.{self.target}"
            try:
                result = socket.getaddrinfo(fqdn, None, timeout=2)
                ips = list({r[4][0] for r in result})
                for ip in ips:
                    self._save(OSINTFinding(
                        source="dns",
                        finding_type="dns_record",
                        value=f"{fqdn} → {ip}",
                        confidence=0.99,
                        notes=f"A/AAAA record resolved",
                    ))
                print(f"    → {fqdn}: {ips}")
            except Exception:
                pass

    def infer_tech_stack(self):
        """Infer likely tech stack from job postings pattern and domain signals."""
        print(f"  [OSINT] Tech stack inference (passive)")
        # In a real engagement, you'd query LinkedIn/Indeed job postings.
        # Here we model the inference engine with pattern-based heuristics.
        inferences = []

        if "." in self.target:
            tld = self.target.rsplit(".", 1)[-1]
            if tld == "io":
                inferences.append(("tech_stack", "Cloud-native likely (k8s, AWS/GCP)", 0.70))
            elif tld == "com":
                inferences.append(("tech_stack", "Mixed stack; check job postings for specifics", 0.40))

        # Domain age and cert issuer hints
        inferences.append(("recon_note", "Query LinkedIn jobs for SIEM/EDR tech stack clues", 0.90))
        inferences.append(("recon_note", "Check Shodan for banner info on org IPs (passive)", 0.85))
        inferences.append(("recon_note", "GitHub org search for credential leaks in public repos", 0.80))

        for finding_type, value, conf in inferences:
            self._save(OSINTFinding(
                source="inference",
                finding_type=finding_type,
                value=value,
                confidence=conf,
                notes="Inferred from domain signals and industry patterns",
            ))

    def check_known_breaches(self):
        """Note HIBP-style breach indicators — informational only."""
        print(f"  [OSINT] Known breach indicators")
        self._save(OSINTFinding(
            source="breach_intel",
            finding_type="recommendation",
            value=f"Query HaveIBeenPwned API for {self.target} domain email breaches",
            confidence=0.95,
            notes="Breached credentials dramatically lower phishing difficulty",
        ))
        self._save(OSINTFinding(
            source="breach_intel",
            finding_type="recommendation",
            value="Search Dehashed/IntelX for credential pairs linked to target domain",
            confidence=0.85,
            notes="Pre-breach cred stuffing accelerates initial access",
        ))

    def run_all(self):
        self.cert_transparency()
        self.dns_enumeration()
        self.infer_tech_stack()
        self.check_known_breaches()
        print(f"\n  [OSINT] Total findings: {len(self.findings)}")
        return self.findings


# ---------------------------------------------------------------------------
# Attack graph builder
# ---------------------------------------------------------------------------

class AttackGraphBuilder:
    """
    Builds a probabilistic directed attack graph over MITRE ATT&CK techniques.
    Edge weights: combined success probability and stealth score.
    Defender profile modulates detection probabilities.
    """

    # Tactic ordering (kill chain sequence)
    TACTIC_ORDER = [
        "recon", "initial_access", "execution", "persistence",
        "privesc", "defense_evasion", "credential_access",
        "discovery", "lateral_movement", "collection", "exfiltration", "impact"
    ]

    # Valid tactic transitions
    TRANSITIONS = {
        "recon": ["initial_access"],
        "initial_access": ["execution", "persistence"],
        "execution": ["persistence", "privesc", "defense_evasion", "discovery"],
        "persistence": ["privesc", "defense_evasion"],
        "privesc": ["defense_evasion", "credential_access", "discovery"],
        "defense_evasion": ["credential_access", "discovery", "lateral_movement"],
        "credential_access": ["lateral_movement", "collection"],
        "discovery": ["lateral_movement", "collection", "credential_access"],
        "lateral_movement": ["discovery", "collection", "exfiltration", "impact"],
        "collection": ["exfiltration"],
        "exfiltration": ["impact"],
        "impact": [],
    }

    def __init__(self, engagement_id: str, defender_profile: str, db: sqlite3.Connection):
        self.engagement_id = engagement_id
        self.profile = DEFENDER_PROFILES.get(defender_profile, DEFENDER_PROFILES["smb"])
        self.db = db
        self.nodes: dict[str, AttackNode] = {}

    def _adjusted_detect(self, base_detect: float) -> float:
        """Defender profile adjusts raw detection probability."""
        edr = self.profile["edr_coverage"]
        fatigue = self.profile["alert_fatigue_factor"]
        # Higher EDR coverage increases detection; alert fatigue reduces effective detection
        adjusted = base_detect * edr * (1.0 - fatigue * 0.3)
        return min(adjusted, 0.99)

    def build(self) -> dict[str, AttackNode]:
        """Build nodes for all applicable techniques, adjusted by defender profile."""
        for tid, tech in ATTACK_TECHNIQUES.items():
            adj_detect = self._adjusted_detect(tech["detect_prob"])
            stealth = 1.0 - adj_detect
            node = AttackNode(
                technique_id=tid,
                technique_name=tech["name"],
                tactic=tech["tactic"],
                success_prob=tech["success_base"],
                detect_prob=adj_detect,
                stealth_score=stealth,
            )
            self.nodes[tid] = node
            self.db.execute(
                "INSERT OR REPLACE INTO attack_nodes "
                "(engagement_id, technique_id, technique_name, tactic, success_prob, detect_prob, stealth_score, notes) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (self.engagement_id, tid, tech["name"], tech["tactic"],
                 node.success_prob, node.detect_prob, node.stealth_score, ""),
            )
        self.db.commit()
        return self.nodes

    def edges(self, from_node: AttackNode) -> list[AttackNode]:
        """Return reachable next nodes from a given node."""
        next_tactics = self.TRANSITIONS.get(from_node.tactic, [])
        return [n for n in self.nodes.values() if n.tactic in next_tactics]


# ---------------------------------------------------------------------------
# Kill chain optimizer (probabilistic path search)
# ---------------------------------------------------------------------------

class KillChainOptimizer:
    """
    Finds top-N kill chains through the attack graph using a weighted path search.

    Scoring function: log(success_prob) - penalty*log(1-stealth_score)
    Maximizing score = maximizing success while minimizing detection risk.
    """

    def __init__(self, engagement_id: str, graph: AttackGraphBuilder,
                 objective: str = "data_exfiltration", db: sqlite3.Connection = None):
        self.engagement_id = engagement_id
        self.graph = graph
        self.objective = objective
        self.db = db

    def _score_node(self, node: AttackNode, penalty: float = 1.5) -> float:
        """Single-node utility: reward success, penalize detection risk."""
        s = max(node.success_prob, 1e-6)
        d = max(1.0 - node.stealth_score, 1e-6)
        return math.log(s) - penalty * math.log(d)

    def _chain_score(self, chain: list[AttackNode]) -> tuple[float, float, float]:
        """Returns (cumulative_success, cumulative_detect_risk, stealth_score)."""
        cum_success = 1.0
        cum_detect = 0.0
        for node in chain:
            cum_success *= node.success_prob
            cum_detect = 1.0 - (1.0 - cum_detect) * (1.0 - node.detect_prob)
        stealth = 1.0 - cum_detect
        return cum_success, cum_detect, stealth

    def find_chains(self, top_n: int = 5, max_depth: int = 7) -> list[KillChain]:
        """
        Beam search over the attack graph; returns top_n kill chains
        ordered by (success * stealth) composite score.
        """
        tactic_order = AttackGraphBuilder.TACTIC_ORDER
        objective_tactic = {
            "data_exfiltration": "exfiltration",
            "ransomware": "impact",
            "persistence": "persistence",
            "credential_theft": "credential_access",
            "lateral_spread": "lateral_movement",
            "crown_jewels": "impact",
        }.get(self.objective, "exfiltration")

        # Start from all recon nodes
        recon_nodes = [n for n in self.graph.nodes.values() if n.tactic == "recon"]
        # Beam: list of (score, path_so_far)
        beam = [(self._score_node(n), [n]) for n in recon_nodes]
        beam.sort(key=lambda x: -x[0])
        beam = beam[:top_n * 3]

        completed = []
        iterations = 0
        max_iters = 500

        while beam and iterations < max_iters:
            iterations += 1
            next_beam = []
            for score, path in beam:
                last = path[-1]
                if last.tactic == objective_tactic or len(path) >= max_depth:
                    completed.append((score, path))
                    continue
                nexts = self.graph.edges(last)
                if not nexts:
                    completed.append((score, path))
                    continue
                for nxt in nexts:
                    # Avoid tactic cycles
                    if nxt.tactic in {n.tactic for n in path}:
                        continue
                    new_score = score + self._score_node(nxt)
                    next_beam.append((new_score, path + [nxt]))
            next_beam.sort(key=lambda x: -x[0])
            beam = next_beam[:top_n * 4]

        # Deduplicate by tactic sequence
        seen_seqs = set()
        kill_chains = []
        for _, path in sorted(completed, key=lambda x: -x[0]):
            seq = tuple(n.tactic for n in path)
            if seq in seen_seqs:
                continue
            seen_seqs.add(seq)
            cum_success, cum_detect, stealth = self._chain_score(path)
            chain_id = hashlib.sha1(":".join(n.technique_id for n in path).encode()).hexdigest()[:12]
            kc = KillChain(
                chain_id=chain_id,
                engagement_id=self.engagement_id,
                nodes=[asdict(n) for n in path],
                cumulative_success=round(cum_success, 4),
                cumulative_detection_risk=round(cum_detect, 4),
                stealth_score=round(stealth, 4),
                objective=self.objective,
            )
            kill_chains.append(kc)
            if len(kill_chains) >= top_n:
                break

        # Persist
        if self.db:
            for kc in kill_chains:
                self.db.execute(
                    "INSERT OR REPLACE INTO kill_chains "
                    "(id, engagement_id, chain_json, cumulative_success, cumulative_detection_risk, stealth_score, objective, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (kc.chain_id, kc.engagement_id, json.dumps(kc.nodes),
                     kc.cumulative_success, kc.cumulative_detection_risk,
                     kc.stealth_score, kc.objective, now_iso()),
                )
            self.db.commit()
        return kill_chains


# ---------------------------------------------------------------------------
# Defender model
# ---------------------------------------------------------------------------

class DefenderModel:
    """
    Models defender attention, alert fatigue, and temporal blind spots.
    Novel insight: most orgs have predictable monitoring patterns that
    create exploitable windows.
    """

    def __init__(self, profile_name: str):
        self.name = profile_name
        self.profile = DEFENDER_PROFILES.get(profile_name, DEFENDER_PROFILES["smb"])

    def optimal_operation_windows(self) -> list[dict]:
        """Returns ranked time windows for operation with detection probability."""
        low_hours = self.profile["low_watch_hours"]
        windows = []
        for h in low_hours:
            base_risk = 0.05 if self.profile["soc_24x7"] else 0.02
            window_risk = base_risk * (1.0 - self.profile["alert_fatigue_factor"] * 0.5)
            windows.append({
                "hour_utc": h,
                "detection_risk_modifier": round(window_risk, 3),
                "label": f"{h:02d}:00 UTC — low-watch window",
            })
        return windows

    def incident_response_estimate(self) -> str:
        h = self.profile["incident_response_hours"]
        if h < 1:
            return f"~{int(h*60)} minutes (high-maturity SOC)"
        return f"~{h} hours (typical for {self.name} profile)"

    def patch_window_estimate(self) -> str:
        days = self.profile["patch_lag_days"]
        return f"~{days} days average patch lag (exploit window)"

    def evasion_recommendations(self, kill_chain: KillChain) -> list[str]:
        """Given a kill chain, recommend evasion adjustments per defender profile."""
        recs = []
        edr = self.profile["edr_coverage"]
        if edr > 0.85:
            recs.append("Avoid LOLBins that are commonly logged; prefer memory-resident techniques")
            recs.append("Use process hollowing or DLL hijacking over direct execution")
        if self.profile["soc_24x7"]:
            recs.append("Operate in small bursts; avoid sustained activity patterns")
            recs.append("Space actions across multiple sessions to avoid behavioral correlation")
        if self.profile["log_retention_days"] > 90:
            recs.append("Focus on timestamp manipulation and log indicator removal (T1070)")
        recs.append(f"Optimal operation window: {self.profile['low_watch_hours'][:3]} UTC hours")
        return recs

    def report(self) -> str:
        lines = [
            f"\n=== Defender Model: {self.name.upper()} ===",
            f"24x7 SOC:              {'YES' if self.profile['soc_24x7'] else 'NO'}",
            f"EDR Coverage:          {int(self.profile['edr_coverage']*100)}%",
            f"Log Retention:         {self.profile['log_retention_days']} days",
            f"Avg Patch Lag:         {self.patch_window_estimate()}",
            f"Alert Fatigue Factor:  {self.profile['alert_fatigue_factor']} (1.0 = total fatigue)",
            f"IR Response Estimate:  {self.incident_response_estimate()}",
            f"Notes:                 {self.profile['notes']}",
            "",
            "Optimal Operation Windows (UTC hours, lowest detection risk):",
        ]
        for w in self.optimal_operation_windows()[:5]:
            lines.append(f"  {w['label']} — detection modifier {w['detection_risk_modifier']}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Living-off-the-land advisor
# ---------------------------------------------------------------------------

def lotl_advisor(os_type: str, priv_level: str) -> str:
    os_type = os_type.lower()
    priv_level = priv_level.lower()

    if os_type not in LOLBINS:
        return f"No LotL data for OS: {os_type}. Supported: {list(LOLBINS.keys())}"

    bins = LOLBINS[os_type].get(priv_level, [])
    if not bins:
        return f"No LotL data for {os_type}/{priv_level}. Available levels: {list(LOLBINS[os_type].keys())}"

    lines = [f"\n=== LotL Advisor: {os_type.upper()} / {priv_level.upper()} ===",
             f"{'Binary':<35} {'Evasion':<10} {'ATT&CK':<20} Use",
             "─" * 100]
    for b in bins:
        lines.append(f"{b['bin']:<35} {b['evade']:<10} {b['tid']:<20} {b['use']}")

    lines += [
        "",
        "Evasion ratings: high=less detected, low=commonly flagged",
        "Cross-reference with detected EDR solution for bypass techniques.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Narrative generator
# ---------------------------------------------------------------------------

class NarrativeEngine:
    """
    Generates an operator briefing narrative from the attack graph analysis.
    Combines OSINT findings, top kill chain, and defender model into
    a structured red team planning document.
    """

    def __init__(self, engagement_id: str, db: sqlite3.Connection):
        self.engagement_id = engagement_id
        self.db = db

    def generate(self) -> str:
        eng = self.db.execute(
            "SELECT * FROM engagements WHERE id=?", (self.engagement_id,)
        ).fetchone()
        if not eng:
            return "Engagement not found."

        findings = self.db.execute(
            "SELECT * FROM osint_findings WHERE engagement_id=? ORDER BY confidence DESC",
            (self.engagement_id,)
        ).fetchall()

        chains = self.db.execute(
            "SELECT * FROM kill_chains WHERE engagement_id=? ORDER BY stealth_score DESC LIMIT 3",
            (self.engagement_id,)
        ).fetchall()

        profile_name = eng["defender_profile"] or "smb"
        defender = DefenderModel(profile_name)

        lines = [
            "=" * 80,
            "PHANTOM GRAPH — RED TEAM OPERATOR BRIEFING",
            f"Engagement:  {self.engagement_id}",
            f"Target:      {eng['target']}",
            f"Org:         {eng['org'] or 'N/A'}",
            f"Scope:       {eng['scope'] or 'N/A'}",
            f"Generated:   {now_iso()}",
            "=" * 80,
            "",
            "SECTION 1: RECON SUMMARY",
            "─" * 40,
        ]

        subdomain_findings = [f for f in findings if f["finding_type"] == "subdomain"]
        dns_findings = [f for f in findings if f["finding_type"] == "dns_record"]
        rec_findings = [f for f in findings if f["finding_type"] == "recommendation"]

        lines.append(f"Subdomains discovered: {len(subdomain_findings)}")
        for f in subdomain_findings[:10]:
            lines.append(f"  • {f['value']}")
        if len(subdomain_findings) > 10:
            lines.append(f"  ... and {len(subdomain_findings)-10} more")

        lines += ["", f"DNS records resolved: {len(dns_findings)}"]
        for f in dns_findings[:8]:
            lines.append(f"  • {f['value']}")

        if rec_findings:
            lines += ["", "Intel recommendations:"]
            for f in rec_findings:
                lines.append(f"  → {f['value']}")

        lines += [
            "",
            "SECTION 2: TOP KILL CHAINS",
            "─" * 40,
            f"Objective: {chains[0]['objective'] if chains else 'N/A'}",
            "",
        ]

        for i, chain_row in enumerate(chains, 1):
            nodes = json.loads(chain_row["chain_json"])
            lines.append(f"CHAIN #{i} (stealth={chain_row['stealth_score']:.0%}, "
                         f"success={chain_row['cumulative_success']:.0%}, "
                         f"detect_risk={chain_row['cumulative_detection_risk']:.0%})")
            for j, node in enumerate(nodes):
                arrow = "→" if j > 0 else "★"
                lines.append(f"  {arrow} [{node['tactic'].upper():20}] {node['technique_id']} — {node['technique_name']}")
            lines.append("")

        lines += [
            "SECTION 3: DEFENDER ANALYSIS",
            "─" * 40,
            defender.report(),
        ]

        if chains:
            best_chain = KillChain(
                chain_id=chains[0]["id"],
                engagement_id=self.engagement_id,
                nodes=json.loads(chains[0]["chain_json"]),
            )
            evasion = defender.evasion_recommendations(best_chain)
            lines += [
                "",
                "Evasion Recommendations for Top Chain:",
            ]
            for rec in evasion:
                lines.append(f"  • {rec}")

        lines += [
            "",
            "SECTION 4: OPERATOR NOTES",
            "─" * 40,
            "1. Validate all recon findings before active exploitation.",
            "2. Confirm written authorization covers all target systems.",
            "3. Log all actions with timestamps for deconfliction.",
            "4. Brief IR team before executing high-noise techniques.",
            "5. Use defender blind spot windows for high-risk operations.",
            "",
            "[END OF BRIEFING]",
            "=" * 80,
        ]

        narrative = "\n".join(lines)

        self.db.execute(
            "INSERT INTO narratives (engagement_id, narrative_text, generated_at) VALUES (?,?,?)",
            (self.engagement_id, narrative, now_iso()),
        )
        self.db.commit()
        return narrative


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_scope(args, db):
    eng_id = f"ENG-{hashlib.sha1(f'{args.target}{now_iso()}'.encode()).hexdigest()[:6].upper()}"
    if args.id:
        eng_id = args.id
    db.execute(
        "INSERT OR REPLACE INTO engagements (id, target, org, scope, defender_profile, created_at, notes) VALUES (?,?,?,?,?,?,?)",
        (eng_id, args.target, args.org or "", args.scope or "full", args.defender, now_iso(), args.notes or ""),
    )
    db.commit()
    print(f"\n[+] Engagement created: {eng_id}")
    print(f"    Target: {args.target}  |  Org: {args.org}  |  Defender: {args.defender}")

    if not args.no_osint:
        print("\n[*] Running passive OSINT...")
        osint = PassiveOSINT(eng_id, args.target, db)
        osint.run_all()

    print(f"\n[+] Next step: python phantom_graph.py graph --engagement-id {eng_id}")
    return eng_id


def cmd_graph(args, db):
    eng = db.execute("SELECT * FROM engagements WHERE id=?", (args.engagement_id,)).fetchone()
    if not eng:
        print(f"[-] Engagement {args.engagement_id} not found. Run `scope` first.")
        return

    print(f"\n[*] Building attack graph for {eng['target']} ({args.engagement_id})")
    print(f"    Defender profile: {eng['defender_profile']}")

    builder = AttackGraphBuilder(args.engagement_id, eng["defender_profile"], db)
    nodes = builder.build()
    print(f"    → {len(nodes)} attack technique nodes loaded")

    tactic_counts = {}
    for n in nodes.values():
        tactic_counts[n.tactic] = tactic_counts.get(n.tactic, 0) + 1
    for tactic, count in sorted(tactic_counts.items()):
        print(f"    [{tactic:25}] {count} techniques")

    print(f"\n[+] Graph built. Next: python phantom_graph.py paths --engagement-id {args.engagement_id}")


def cmd_paths(args, db):
    eng = db.execute("SELECT * FROM engagements WHERE id=?", (args.engagement_id,)).fetchone()
    if not eng:
        print(f"[-] Engagement not found.")
        return

    print(f"\n[*] Finding top {args.top} kill chains — objective: {args.objective}")

    builder = AttackGraphBuilder(args.engagement_id, eng["defender_profile"], db)
    builder.build()

    optimizer = KillChainOptimizer(args.engagement_id, builder, args.objective, db)
    chains = optimizer.find_chains(top_n=args.top)

    print(f"\n{'─'*80}")
    print(f"TOP KILL CHAINS — {args.objective.upper()}")
    print(f"{'─'*80}")

    for i, kc in enumerate(chains, 1):
        risk_label = "LOW" if kc.cumulative_detection_risk < 0.4 else "MEDIUM" if kc.cumulative_detection_risk < 0.7 else "HIGH"
        print(f"\nChain #{i} [stealth={kc.stealth_score:.0%}  success={kc.cumulative_success:.0%}  detect={kc.cumulative_detection_risk:.0%}  risk={risk_label}]")
        for j, node in enumerate(kc.nodes):
            arrow = "▶" if j == 0 else "→"
            print(f"  {arrow} {node['tactic']:20} | {node['technique_id']:12} | {node['technique_name']}")

    print(f"\n[+] Chains saved. Next: python phantom_graph.py narrative --engagement-id {args.engagement_id}")


def cmd_narrative(args, db):
    print(f"\n[*] Generating operator narrative for {args.engagement_id}...")
    # Rebuild graph if needed
    eng = db.execute("SELECT * FROM engagements WHERE id=?", (args.engagement_id,)).fetchone()
    if not eng:
        print("[-] Engagement not found.")
        return
    # Ensure chains exist
    chains = db.execute("SELECT COUNT(*) FROM kill_chains WHERE engagement_id=?", (args.engagement_id,)).fetchone()[0]
    if chains == 0:
        print("[*] No chains found, building graph and paths first...")
        builder = AttackGraphBuilder(args.engagement_id, eng["defender_profile"], db)
        builder.build()
        optimizer = KillChainOptimizer(args.engagement_id, builder, "data_exfiltration", db)
        optimizer.find_chains(top_n=5)

    engine = NarrativeEngine(args.engagement_id, db)
    narrative = engine.generate()
    print(narrative)

    if args.output:
        Path(args.output).write_text(narrative)
        print(f"\n[+] Narrative saved to {args.output}")


def cmd_defender(args, db):
    profile = args.profile or "smb"
    model = DefenderModel(profile)
    print(model.report())

    print("\n\nAll Defender Profiles (summary):")
    print(f"{'Profile':<15} {'24x7':>6} {'EDR%':>6} {'Patch':>7} {'IR':>8}")
    print("─" * 50)
    for name, p in DEFENDER_PROFILES.items():
        print(f"{name:<15} {'YES' if p['soc_24x7'] else 'NO':>6} {int(p['edr_coverage']*100):>5}% {p['patch_lag_days']:>6}d {p['incident_response_hours']:>7}h")


def cmd_lotl(args, db):
    result = lotl_advisor(args.os, args.priv)
    print(result)


def cmd_list(args, db):
    rows = db.execute("SELECT id, target, org, defender_profile, created_at FROM engagements ORDER BY created_at DESC").fetchall()
    if not rows:
        print("No engagements found.")
        return
    print(f"\n{'ID':<15} {'Target':<30} {'Org':<20} {'Defender':<12} {'Created'}")
    print("─" * 95)
    for r in rows:
        print(f"{r['id']:<15} {r['target']:<30} {(r['org'] or ''):<20} {r['defender_profile']:<12} {r['created_at'][:19]}")


def main():
    print(BANNER)

    parser = argparse.ArgumentParser(
        prog="phantom_graph",
        description="PhantomGraph — Probabilistic Kill Chain Reasoning Engine [AUTHORIZED USE ONLY]",
    )
    sub = parser.add_subparsers(dest="command")

    # scope
    p_scope = sub.add_parser("scope", help="Define engagement scope and run passive OSINT")
    p_scope.add_argument("--target", required=True, help="Target domain (e.g. example.com)")
    p_scope.add_argument("--org", help="Organization name")
    p_scope.add_argument("--scope", help="Engagement scope description")
    p_scope.add_argument("--id", help="Custom engagement ID")
    p_scope.add_argument("--defender", default="smb",
                         choices=list(DEFENDER_PROFILES.keys()), help="Defender profile")
    p_scope.add_argument("--notes", help="Additional notes")
    p_scope.add_argument("--no-osint", action="store_true", help="Skip passive OSINT")

    # graph
    p_graph = sub.add_parser("graph", help="Build probabilistic attack graph")
    p_graph.add_argument("--engagement-id", required=True)

    # paths
    p_paths = sub.add_parser("paths", help="Find top kill chain paths")
    p_paths.add_argument("--engagement-id", required=True)
    p_paths.add_argument("--top", type=int, default=5)
    p_paths.add_argument("--objective", default="data_exfiltration",
                         choices=["data_exfiltration", "ransomware", "persistence",
                                  "credential_theft", "lateral_spread", "crown_jewels"])

    # narrative
    p_narrative = sub.add_parser("narrative", help="Generate operator briefing narrative")
    p_narrative.add_argument("--engagement-id", required=True)
    p_narrative.add_argument("--output", help="Save narrative to file")

    # defender
    p_defender = sub.add_parser("defender", help="Show defender model profiles")
    p_defender.add_argument("--profile", choices=list(DEFENDER_PROFILES.keys()))
    p_defender.add_argument("--engagement-id")

    # lotl
    p_lotl = sub.add_parser("lotl", help="Living-off-the-land binary advisor")
    p_lotl.add_argument("--os", required=True, choices=list(LOLBINS.keys()))
    p_lotl.add_argument("--priv", required=True, help="Privilege level (user/admin/root/system)")

    # list
    sub.add_parser("list", help="List all engagements")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    db = init_db(DB_PATH)

    dispatch = {
        "scope": cmd_scope,
        "graph": cmd_graph,
        "paths": cmd_paths,
        "narrative": cmd_narrative,
        "defender": cmd_defender,
        "lotl": cmd_lotl,
        "list": cmd_list,
    }
    dispatch[args.command](args, db)


if __name__ == "__main__":
    main()
