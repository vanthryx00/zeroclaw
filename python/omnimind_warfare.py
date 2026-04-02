#!/usr/bin/env python3
"""
OMNIMIND EMPIRE - REVENUE WARFARE ENGINE

Weaponizes your existing phantom_ultra_omega + bugreaperx codebase into a
managed security-as-a-service revenue platform. Voice-first, Termux-optimized.

Target: $8K in 60 days through automated B2B security service delivery.

Usage:
    python omnimind_warfare.py status
    python omnimind_warfare.py hunt "law firms" "Toronto"
    python omnimind_warfare.py attack
    python omnimind_warfare.py scan [client_id]
    python omnimind_warfare.py convert <client_id> [setup_fee]
"""

import os
import json
import subprocess
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


# =============================================================================
# VOICE-FIRST INTERFACE
# =============================================================================

class VoiceInterface:
    """Text-to-speech for hands-free operation in Termux."""

    @staticmethod
    def speak(text: str):
        try:
            subprocess.run(["termux-tts-speak", text], check=False)
        except FileNotFoundError:
            print(f"[VOICE] {text}")

    @staticmethod
    def notify(title: str, body: str):
        try:
            subprocess.run(
                ["termux-notification", "--title", title, "--content", body, "--priority", "high"],
                check=False,
            )
        except FileNotFoundError:
            print(f"[NOTIFY] {title}: {body}")


# =============================================================================
# WEAPON INTEGRATION — YOUR EXISTING TOOLS
# =============================================================================

class PhantomIntegration:
    """Wrapper for phantom_ultra_omega_v10.py."""

    def __init__(self, phantom_path: str = "./phantom_ultra_omega_v10.py"):
        self.path = Path(phantom_path)
        self.available = self.path.exists()

    def run_defensive_scan(self, target: str) -> Dict:
        if not self.available:
            return {
                "status": "mock",
                "vulnerabilities": 3,
                "critical": 1,
                "report": f"[MOCK] Phantom scan of {target} complete",
            }
        try:
            result = subprocess.run(
                ["python", str(self.path), "--target", target, "--mode", "scan"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return {"status": "success", "output": result.stdout, "report": result.stdout}
        except Exception as e:
            return {"status": "error", "message": str(e)}


class BugReaperIntegration:
    """Wrapper for bugreaperx_surpreme.py."""

    def __init__(self, reaper_path: str = "./bugreaperx_surpreme.py"):
        self.path = Path(reaper_path)
        self.available = self.path.exists()

    def run_vulnerability_scan(self, target: str) -> Dict:
        if not self.available:
            return {
                "status": "mock",
                "vulnerabilities": [
                    {"severity": "HIGH", "type": "SQL Injection", "location": "/login"},
                    {"severity": "MEDIUM", "type": "XSS", "location": "/search"},
                    {"severity": "LOW", "type": "Missing Headers", "location": "/*"},
                ],
                "score": 6.5,
            }
        try:
            result = subprocess.run(
                ["python", str(self.path), "--url", target, "--full-scan"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            return {
                "status": "success",
                "output": result.stdout,
                "vulnerabilities": self._parse_output(result.stdout),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _parse_output(self, output: str) -> List[Dict]:
        # Customize based on your actual bugreaperx output format.
        return [{"raw": output}]


# =============================================================================
# DATABASE
# =============================================================================

class Database:
    """Lightweight SQLite client tracker."""

    def __init__(self, path: str = "./omnimind_warfare.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                domain TEXT UNIQUE NOT NULL,
                email TEXT,
                phone TEXT,
                status TEXT DEFAULT 'prospect',
                package TEXT,
                setup_paid REAL DEFAULT 0,
                monthly_paid REAL DEFAULT 0,
                last_scan DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY,
                client_id INTEGER,
                scan_type TEXT,
                vulnerabilities INTEGER,
                critical_count INTEGER,
                report_path TEXT,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            )
        """)
        self.conn.commit()

    def add_client(self, name: str, domain: str, **kwargs) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO clients (name, domain, email, phone, status) VALUES (?, ?, ?, ?, 'prospect')",
            (name, domain, kwargs.get("email"), kwargs.get("phone")),
        )
        self.conn.commit()
        return cur.lastrowid

    def upgrade_to_paid(self, client_id: int, package: str, setup_fee: float):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE clients SET status = 'active', package = ?, setup_paid = ? WHERE id = ?",
            (package, setup_fee, client_id),
        )
        self.conn.commit()

    def log_scan(self, client_id: int, scan_type: str, vulns: int, critical: int):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO scans (client_id, scan_type, vulnerabilities, critical_count) VALUES (?, ?, ?, ?)",
            (client_id, scan_type, vulns, critical),
        )
        cur.execute("UPDATE clients SET last_scan = DATE('now') WHERE id = ?", (client_id,))
        self.conn.commit()

    def get_clients(self, status: Optional[str] = None) -> List[Dict]:
        cur = self.conn.cursor()
        if status:
            cur.execute("SELECT * FROM clients WHERE status = ?", (status,))
        else:
            cur.execute("SELECT * FROM clients")
        return [dict(row) for row in cur.fetchall()]

    def get_revenue(self) -> Dict:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                COUNT(*) as clients,
                SUM(setup_paid) as setup,
                SUM(monthly_paid) as monthly,
                SUM(setup_paid + monthly_paid) as total
            FROM clients
            WHERE status = 'active'
        """)
        row = cur.fetchone()
        return dict(row) if row else {"clients": 0, "setup": 0, "monthly": 0, "total": 0}


# =============================================================================
# SERVICE DELIVERY ENGINE
# =============================================================================

class ServiceEngine:
    """Automated service delivery using your security tools."""

    def __init__(self, db: Database):
        self.db = db
        self.phantom = PhantomIntegration()
        self.reaper = BugReaperIntegration()
        self.voice = VoiceInterface()

    def deliver_weekly_scan(self, client_id: int) -> Dict:
        clients = self.db.get_clients()
        client = next((c for c in clients if c["id"] == client_id), None)
        if not client:
            return {"error": "Client not found"}

        self.voice.speak(f"Starting scan for {client['name']}")

        phantom_result = self.phantom.run_defensive_scan(client["domain"])
        reaper_result = self.reaper.run_vulnerability_scan(client["domain"])

        total_vulns = phantom_result.get("vulnerabilities", 0) + len(
            reaper_result.get("vulnerabilities", [])
        )
        critical = phantom_result.get("critical", 0)

        self.db.log_scan(client_id, "weekly", total_vulns, critical)
        report = self._generate_report(client, phantom_result, reaper_result)

        self.voice.speak(f"Scan complete. Found {total_vulns} vulnerabilities, {critical} critical")
        self.voice.notify("OmniMind Scan Complete", f"{client['name']}: {total_vulns} issues")

        return {"client": client["name"], "vulnerabilities": total_vulns, "critical": critical, "report": report}

    def _generate_report(self, client: Dict, phantom: Dict, reaper: Dict) -> str:
        report_dir = Path("./reports")
        report_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = report_dir / f"{client['domain']}_{timestamp}.txt"

        filepath.write_text(
            f"""OMNIMIND SECURITY REPORT
Client: {client['name']}
Domain: {client['domain']}
Scan Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{'='*60}
DEFENSIVE SCAN (Phantom Ultra Omega)
{'='*60}
{phantom.get('report', 'Scan in progress')}

{'='*60}
VULNERABILITY ASSESSMENT (BugReaperX)
{'='*60}
{json.dumps(reaper.get('vulnerabilities', []), indent=2)}

{'='*60}
RECOMMENDATIONS
{'='*60}
- Patch critical vulnerabilities within 24 hours
- Implement security headers
- Schedule penetration test for Q2
- Enable WAF rules for detected attack vectors

Next scan: {(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')}
"""
        )
        return str(filepath)

    def run_all_weekly_scans(self):
        active = self.db.get_clients(status="active")
        self.voice.speak(f"Starting weekly scans for {len(active)} clients")
        return [self.deliver_weekly_scan(c["id"]) for c in active]


# =============================================================================
# LEAD ACQUISITION
# =============================================================================

class LeadWarfare:
    """Targeted B2B lead acquisition."""

    def __init__(self, db: Database):
        self.db = db
        self.voice = VoiceInterface()

    def scrape_google_maps(self, query: str, city: str = "Toronto") -> List[Dict]:
        """
        Stub: replace with Instant Data Scraper, Apify, or Google Places API.
        Returns structured mock data until real scraper is wired in.
        """
        return [
            {"name": "Smith & Associates Law", "domain": "smithlaw.ca", "email": "contact@smithlaw.ca", "phone": "+1-416-555-0101"},
            {"name": "Toronto Medical Center", "domain": "torontomedical.ca", "email": "info@torontomedical.ca", "phone": "+1-416-555-0202"},
            {"name": "Peak Consulting Group", "domain": "peakconsulting.ca", "email": "hello@peakconsulting.ca", "phone": "+1-416-555-0303"},
        ]

    def import_leads(self, leads: List[Dict]) -> int:
        imported = 0
        for lead in leads:
            try:
                self.db.add_client(lead["name"], lead["domain"], email=lead.get("email"), phone=lead.get("phone"))
                imported += 1
            except sqlite3.IntegrityError:
                continue
        self.voice.speak(f"Imported {imported} new leads")
        return imported

    def run_free_scan_campaign(self):
        prospects = self.db.get_clients(status="prospect")
        self.voice.speak(f"Running free scan campaign for {len(prospects)} prospects")
        batch = prospects[:5]
        for prospect in batch:
            self._send_free_scan_offer(prospect)
        return len(batch)

    def _send_free_scan_offer(self, prospect: Dict):
        print(f"\n[EMAIL → {prospect['email']}]")
        print(f"Subject: Free security scan for {prospect['name']}")
        print(f"""
Hi there,

We're offering free security scans to {prospect['name'].split()[0]} businesses this week.

We'll scan {prospect['domain']} and send you a PDF report covering:
• Vulnerabilities ranked by severity
• Specific attack vectors identified
• Remediation recommendations

No cost, no obligation.

Reply "YES" to claim your scan.

Thanks,
OmniMind Security
""")


# =============================================================================
# COMMAND CENTER
# =============================================================================

class CommandCenter:
    """Voice-first command interface for daily operations."""

    def __init__(self):
        self.db = Database()
        self.service = ServiceEngine(self.db)
        self.leads = LeadWarfare(self.db)
        self.voice = VoiceInterface()

    def status(self):
        revenue = self.db.get_revenue()
        prospects = len(self.db.get_clients(status="prospect"))
        active = revenue["clients"]

        self.voice.speak(
            f"Status report. {active} active clients. {prospects} prospects. "
            f"Total revenue {revenue['total']} dollars."
        )

        print(f"\n{'='*60}")
        print("OMNIMIND WARFARE — STATUS REPORT")
        print(f"{'='*60}")
        print(f"Active Clients : {active}")
        print(f"Prospects      : {prospects}")
        print(f"Setup Revenue  : ${revenue['setup'] or 0:.2f}")
        print(f"Monthly MRR    : ${revenue['monthly'] or 0:.2f}")
        print(f"Total Revenue  : ${revenue['total'] or 0:.2f}")
        print(f"{'='*60}\n")

    def hunt(self, query: str = "law firms", city: str = "Toronto"):
        self.voice.speak(f"Hunting {query} in {city}")
        leads = self.leads.scrape_google_maps(query, city)
        imported = self.leads.import_leads(leads)
        self.voice.speak(f"Hunt complete. {imported} new targets acquired")

    def attack(self):
        self.voice.speak("Launching free scan campaign")
        sent = self.leads.run_free_scan_campaign()
        self.voice.speak(f"Campaign deployed. {sent} offers sent")

    def scan(self, client_id: Optional[int] = None):
        if client_id:
            result = self.service.deliver_weekly_scan(client_id)
            print(f"\n{result.get('report', result)}")
        else:
            self.service.run_all_weekly_scans()

    def convert(self, client_id: int, package: str = "security", setup_fee: float = 600.0):
        self.db.upgrade_to_paid(client_id, package, setup_fee)
        self.voice.speak(f"Client {client_id} upgraded. {setup_fee} dollars collected")
        self.voice.notify("Revenue Event", f"${setup_fee:.0f} setup fee collected")


# =============================================================================
# CLI
# =============================================================================

def main():
    import sys

    cmd = CommandCenter()

    if len(sys.argv) < 2:
        print("""
OMNIMIND WARFARE — COMMAND CENTER

Commands:
  status                        Show revenue and client count
  hunt [query] [city]           Scrape new leads (default: law firms, Toronto)
  attack                        Send free scan offers to prospects
  scan [id]                     Run scan for client ID (or all active)
  convert <id> [fee]            Mark prospect as paid client ($600 default)

Examples:
  python omnimind_warfare.py status
  python omnimind_warfare.py hunt "medical clinics" "Vancouver"
  python omnimind_warfare.py attack
  python omnimind_warfare.py scan 1
  python omnimind_warfare.py convert 3 800
""")
        sys.exit(0)

    command = sys.argv[1].lower()

    if command == "status":
        cmd.status()
    elif command == "hunt":
        query = sys.argv[2] if len(sys.argv) > 2 else "law firms"
        city = sys.argv[3] if len(sys.argv) > 3 else "Toronto"
        cmd.hunt(query, city)
    elif command == "attack":
        cmd.attack()
    elif command == "scan":
        client_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
        cmd.scan(client_id)
    elif command == "convert":
        if len(sys.argv) < 3:
            print("Usage: convert <client_id> [setup_fee]")
            sys.exit(1)
        client_id = int(sys.argv[2])
        fee = float(sys.argv[3]) if len(sys.argv) > 3 else 600.0
        cmd.convert(client_id, "security", fee)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
