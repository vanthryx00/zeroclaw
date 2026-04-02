# BugReaper X v4.0 — Tools & Capabilities Reference

> Comprehensive guide to built-in scanners, integrated Kali tooling, and
> Red/Blue/Purple team workflows.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [Built-in Scanner Modules](#built-in-scanner-modules)
3. [Kali Linux Tool Integrations](#kali-linux-tool-integrations)
4. [OWASP Top 10 Coverage](#owasp-top-10-coverage)
5. [Red Team Capabilities](#red-team-capabilities)
6. [Blue Team Capabilities](#blue-team-capabilities)
7. [Purple Team Workflows](#purple-team-workflows)
8. [CLI Reference](#cli-reference)
9. [REST API Endpoints](#rest-api-endpoints)
10. [WebSocket Events](#websocket-events)
11. [Report Formats](#report-formats)
12. [VR Bridge (Quest 3S)](#vr-bridge-quest-3s)

---

## Tech Stack

| Layer        | Technology                                |
|-------------|-------------------------------------------|
| API server   | FastAPI 0.111 + Uvicorn (async, ASGI)     |
| Database     | SQLite (dev) / PostgreSQL (prod) via AsyncSQLAlchemy 2.0 |
| Auth         | JWT (HS256) + bcrypt password hashing     |
| Billing      | Stripe SDK v9 — subscriptions + webhooks  |
| AI assistant | Anthropic Claude API (claude-sonnet-4-6) or local heuristic fallback |
| Scheduler    | APScheduler 3.x — cron + interval jobs   |
| Reports      | ReportLab (PDF) + Jinja2 (HTML) + JSON   |
| VR bridge    | Unity WebSocket relay → Quest 3S overlay  |
| Audio        | SoX — scan event tones                   |
| CLI          | Click 8.x                                 |

---

## Built-in Scanner Modules

BugReaper X ships **8 scanner modules**, each callable independently or
composed into a full-scan pipeline.

### 1. `port_scanner`

Fast TCP/UDP port discovery.

- Wraps `nmap` (SYN scan when root, connect scan otherwise)
- Falls back to Python `asyncio` socket probe when nmap unavailable
- Returns open ports, service banners, OS fingerprint hints
- Options: `ports` (range/list), `timeout`, `udp` (bool)

```json
{ "module": "port_scanner", "target": "192.168.1.1", "options": { "ports": "1-1024", "udp": false } }
```

### 2. `web_crawler`

Recursive web asset discovery.

- Follows `<a href>`, `<form action>`, JS `fetch`/`XMLHttpRequest` patterns
- Respects `robots.txt` by default; `ignore_robots: true` to override
- Extracts parameters, cookies, headers, JS endpoints
- Max depth: configurable (default 3)

### 3. `vuln_matcher`

CVE and signature matching engine.

- Matches banner/version strings against embedded CVE database (NVD JSON feed)
- Offline-capable with bundled snapshot (updated weekly in hosted mode)
- Outputs CVE IDs, CVSS scores, patch availability

### 4. `header_inspector`

HTTP security header auditor.

Checks for presence and correct configuration of:

| Header                          | Risk if missing  |
|---------------------------------|-----------------|
| `Strict-Transport-Security`     | MITM, downgrade  |
| `Content-Security-Policy`       | XSS             |
| `X-Frame-Options`               | Clickjacking     |
| `X-Content-Type-Options`        | MIME sniffing    |
| `Referrer-Policy`               | Info leakage     |
| `Permissions-Policy`            | Feature abuse    |
| `Cache-Control` (API responses) | Token leakage    |

### 5. `ssl_auditor`

TLS/SSL configuration analyser.

- Protocol versions (SSLv2/3, TLS 1.0/1.1 flagged critical)
- Cipher suite strength (RC4, DES, 3DES flagged)
- Certificate validity, SANs, expiry countdown
- HSTS preload status
- Certificate transparency log check

### 6. `dns_recon`

DNS enumeration and subdomain discovery.

- A / AAAA / MX / NS / TXT / SOA / CNAME record collection
- Zone transfer attempt (AXFR) — flags misconfigured DNS
- Subdomain brute-force with bundled wordlist (5 000 entries)
- Reverse DNS lookup for IP ranges
- SPF / DMARC / DKIM policy extraction

### 7. `sql_probe`

SQL injection detection.

- Error-based, time-based blind, boolean-based blind techniques
- Targets: GET/POST parameters, cookies, JSON body fields, HTTP headers
- DB fingerprinting: MySQL, PostgreSQL, MSSQL, SQLite, Oracle
- Safe payload set by default; aggressive mode available for authorised tests

> **Authorization required**: `sql_probe` aggressive mode requires explicit
> `--authorized` flag. Never test targets without written permission.

### 8. `xss_probe`

Cross-site scripting detection.

- Reflected XSS — parameter reflection with HTML/JS context detection
- DOM-based XSS — static JS analysis for `innerHTML`, `document.write`, `eval`
- Stored XSS — submits payloads and re-fetches to detect persistence
- WAF evasion payloads (encoding variants) for authorized red-team engagements

---

## Kali Linux Tool Integrations

BugReaper X wraps **30+ Kali tools** via subprocess when available on PATH.
All integrations are passive wrappers — no tool is invoked without an explicit
scan request.

### Network & Discovery

| Tool         | Usage in BugReaper X                         |
|-------------|----------------------------------------------|
| `nmap`       | Port scan, service detection, NSE scripts    |
| `masscan`    | High-speed port discovery (large IP ranges)  |
| `netdiscover`| ARP scan for local network host discovery    |
| `arp-scan`   | Layer-2 host enumeration                     |
| `tcpdump`    | Packet capture for traffic analysis mode     |
| `wireshark` (tshark) | Offline pcap parsing                |
| `whois`      | Domain registration / ASN lookup             |
| `dnsx`       | Fast DNS resolver for subdomain enumeration  |
| `amass`      | In-depth subdomain enumeration (OSINT)       |
| `subfinder`  | Passive subdomain discovery                  |

### Web Application

| Tool           | Usage in BugReaper X                       |
|---------------|---------------------------------------------|
| `nikto`        | Web server misconfiguration scanning       |
| `gobuster`     | Directory/file/DNS brute-force             |
| `ffuf`         | Web fuzzer for parameter and path discovery|
| `sqlmap`       | Automated SQL injection (authorized only)  |
| `wfuzz`        | Web fuzzer — headers, cookies, params      |
| `dalfox`       | XSS scanner                               |
| `nuclei`       | Template-based vulnerability scanner       |
| `whatweb`      | Web technology fingerprinting              |
| `wafw00f`      | WAF detection and fingerprinting           |
| `wpscan`       | WordPress security scanner                 |

### Credential & Auth Testing

| Tool          | Usage in BugReaper X                        |
|--------------|----------------------------------------------|
| `hydra`       | Online password brute-force (authorized)    |
| `medusa`      | Multi-protocol credential testing           |
| `john`        | Offline hash cracking (captured hashes)     |
| `hashcat`     | GPU-accelerated hash cracking               |
| `crackmapexec`| Windows/AD lateral movement simulation      |

### SSL / PKI

| Tool         | Usage in BugReaper X                         |
|-------------|----------------------------------------------|
| `sslscan`    | TLS protocol and cipher enumeration          |
| `testssl.sh` | Comprehensive TLS health check               |
| `openssl`    | Certificate parsing and verification         |

### OSINT & Recon

| Tool         | Usage in BugReaper X                         |
|-------------|----------------------------------------------|
| `theHarvester` | Email, subdomain, and host OSINT           |
| `recon-ng`   | Modular OSINT framework integration          |
| `shodan` CLI | Shodan query integration (API key required)  |
| `maltego`    | Graph-based OSINT (CE edition hooks)         |
| `exiftool`   | Metadata extraction from uploaded files      |

---

## OWASP Top 10 Coverage

| OWASP ID | Category                                | Scanner Modules        | Status   |
|---------|------------------------------------------|------------------------|---------|
| A01     | Broken Access Control                   | `web_crawler`, manual  | Partial |
| A02     | Cryptographic Failures                  | `ssl_auditor`, `header_inspector` | Full |
| A03     | Injection (SQL, LDAP, OS, etc.)         | `sql_probe`, `xss_probe` | Full  |
| A04     | Insecure Design                         | Report recommendations | Advisory|
| A05     | Security Misconfiguration               | `header_inspector`, `port_scanner`, `nikto` | Full |
| A06     | Vulnerable & Outdated Components        | `vuln_matcher`         | Full    |
| A07     | Identification & Authentication Failures| `ssl_auditor`, `hydra` | Full    |
| A08     | Software & Data Integrity Failures      | `vuln_matcher`         | Partial |
| A09     | Security Logging & Monitoring Failures  | `header_inspector`     | Advisory|
| A10     | Server-Side Request Forgery (SSRF)      | `web_crawler`          | Partial |

---

## Red Team Capabilities

> **All red team modules require explicit written authorization from the target
> system owner. Unauthorized use is illegal.**

### Reconnaissance Phase

- Passive OSINT via `theHarvester`, `amass`, `subfinder`
- Active host/service discovery (`nmap`, `masscan`)
- Technology fingerprinting (`whatweb`, `wappalyzer` heuristics)
- DNS zone transfer attempts
- SSL certificate transparency enumeration

### Exploitation Phase (Authorized Only)

- SQL injection exploitation via `sqlmap` (authorized flag required)
- XSS payload delivery chains
- Credential brute-force with lockout detection (`hydra`, `medusa`)
- WordPress plugin/theme CVE exploitation via `wpscan`
- Template injection detection

### Post-Exploitation Simulation

- Generates detailed attack-path narrative in PDF report
- Maps lateral movement vectors (flagged, not executed)
- Documents privilege escalation paths for patching guidance

---

## Blue Team Capabilities

### Continuous Monitoring

- Scheduled scans via APScheduler (hourly, daily, weekly)
- Baseline drift detection — alerts when new ports/services appear
- Certificate expiry countdown notifications

### Defensive Hardening Checks

- HTTP security header completeness score (0–100)
- TLS configuration grade (A–F, matching SSL Labs methodology)
- Open port delta report (new vs. last baseline)
- SPF/DMARC/DKIM policy validation

### Alerting

- In-app WebSocket push for live scan events
- Email notification stubs (SMTP configurable)
- VR overlay alerts for Quest 3S operators

---

## Purple Team Workflows

Purple team mode runs paired Red+Blue scan pipelines and produces a unified
remediation map.

### Workflow Steps

1. **Red scan** — active discovery, injection probing, credential testing
2. **Blue baseline** — capture current defensive posture snapshot
3. **Gap analysis** — diff attacker findings against defensive controls
4. **Remediation report** — prioritised fix list with CVSS + business impact

### Running Purple Mode

```bash
brx purple --target example.com --output purple_report.pdf
```

Or via API:

```bash
curl -X POST /api/scans \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"target":"example.com","scan_type":"purple"}'
```

---

## CLI Reference

```
brx [OPTIONS] COMMAND [ARGS]

Commands:
  scan      Run a vulnerability scan
  report    Generate or export a report
  status    Show scan queue and system status
  config    Manage configuration
  user      User account management

Options:
  --host TEXT    API host (default: localhost)
  --port INT     API port (default: 8080)
  --token TEXT   JWT token (or set BRX_TOKEN env var)
  --format TEXT  Output format: table|json|csv (default: table)
  -v, --verbose  Verbose output

Examples:
  brx scan --target example.com --type full
  brx scan --target 192.168.1.0/24 --type ports
  brx report --id 42 --format pdf --out ./report.pdf
  brx status
```

### `brx scan` Options

| Flag           | Type    | Default  | Description                         |
|---------------|---------|----------|-------------------------------------|
| `--target`     | string  | required | Domain, IP, or CIDR range           |
| `--type`       | string  | `full`   | `full`, `ports`, `web`, `ssl`, `dns`, `purple` |
| `--depth`      | int     | `3`      | Web crawler depth                   |
| `--authorized` | flag    | false    | Enable aggressive/exploit modules   |
| `--schedule`   | string  | —        | Cron expression for recurring scans |
| `--workers`    | int     | `4`      | Concurrent scanner workers          |

---

## REST API Endpoints

Base URL: `http://localhost:8080`

Interactive docs: `http://localhost:8080/api/docs`

### Authentication

| Method | Path               | Description              |
|--------|--------------------|--------------------------|
| POST   | `/api/auth/register` | Create account          |
| POST   | `/api/auth/login`    | Get JWT token           |
| POST   | `/api/auth/refresh`  | Refresh token           |

### Scans

| Method | Path                    | Description                    |
|--------|-------------------------|--------------------------------|
| POST   | `/api/scans`            | Start a new scan               |
| GET    | `/api/scans`            | List scans (paginated)         |
| GET    | `/api/scans/{id}`       | Get scan details + findings    |
| DELETE | `/api/scans/{id}`       | Cancel / delete scan           |
| GET    | `/api/scans/{id}/findings` | List findings with filters  |

### Reports

| Method | Path                         | Description             |
|--------|------------------------------|-------------------------|
| GET    | `/api/reports/{scan_id}`     | Get report metadata     |
| GET    | `/api/reports/{scan_id}/pdf` | Download PDF report     |
| GET    | `/api/reports/{scan_id}/html`| Download HTML report    |
| GET    | `/api/reports/{scan_id}/json`| Download JSON report    |

### Billing

| Method | Path                         | Description                  |
|--------|------------------------------|------------------------------|
| GET    | `/api/billing/plans`         | List available plans         |
| POST   | `/api/billing/subscribe`     | Create Stripe subscription   |
| POST   | `/api/billing/webhook`       | Stripe webhook receiver      |
| GET    | `/api/billing/usage`         | Current scan usage vs. quota |

### Health

| Method | Path       | Description         |
|--------|-----------|---------------------|
| GET    | `/health`  | Liveness probe      |
| GET    | `/ready`   | Readiness probe     |

---

## WebSocket Events

Connect: `ws://localhost:8080/ws/scans/{scan_id}`

### Server → Client Events

```json
{ "event": "scan_started",    "scan_id": 42, "target": "example.com" }
{ "event": "module_progress", "module": "port_scanner", "pct": 45 }
{ "event": "finding",         "severity": "CRITICAL", "type": "SQL Injection", "location": "/login" }
{ "event": "scan_complete",   "scan_id": 42, "vuln_count": 7, "score": 8.2 }
{ "event": "scan_error",      "scan_id": 42, "message": "Target unreachable" }
```

### Client → Server Events

```json
{ "action": "cancel" }
{ "action": "pause"  }
{ "action": "resume" }
```

---

## Report Formats

### PDF Report Sections

1. Executive Summary — risk score, critical count, remediation urgency
2. Scope and Methodology
3. Finding Summary Table (sorted by CVSS)
4. Detailed Findings — each with: description, impact, evidence, fix guidance
5. OWASP Top 10 Coverage Matrix
6. Attack Path Narrative (purple team only)
7. Remediation Roadmap — prioritised by CVSS × exploitability
8. Appendix — raw tool output, scan metadata

### JSON Report Schema

```json
{
  "scan_id": 42,
  "target": "example.com",
  "started_at": "2026-04-02T10:00:00Z",
  "finished_at": "2026-04-02T10:14:22Z",
  "score": 8.2,
  "findings": [
    {
      "id": 1,
      "severity": "CRITICAL",
      "vuln_type": "SQL Injection",
      "location": "/api/login",
      "detail": "Parameter 'username' is vulnerable to time-based blind SQLi",
      "cvss": 9.1,
      "cve": "CWE-89",
      "remediation": "Use parameterized queries / prepared statements"
    }
  ]
}
```

---

## VR Bridge (Quest 3S)

BugReaper X includes an optional VR dashboard for Meta Quest 3S via a Unity
WebSocket relay.

### Architecture

```
BugReaper X API  ──WS──►  VR Bridge (port 9000)  ──WS──►  Unity App (Quest 3S)
```

### Enabling

1. Set `VR_BRIDGE_ENABLED=true` in `/etc/bugreaperx/bugreaperx.env`
2. Restart service: `systemctl restart bugreaperx`
3. Open the BugReaper X Unity app on Quest 3S
4. Connect to: `ws://<server-ip>:9000/vr`

> **Note:** VR bridge port 9000 should only be accessible on your local network.
> The installer blocks port 9000 externally via UFW.

### VR Dashboard Features

- 3D network topology visualization — nodes glow red for critical findings
- Real-time scan progress overlaid on target topology
- Spatial audio alerts for critical vulnerabilities
- Hand-tracking gesture controls (pinch to expand finding detail)
- Export to report via air-tap gesture

---

*BugReaper X v4.0 — integrated into ZeroClaw agent runtime.*
*For ZeroClaw core docs see `docs/README.md`.*
