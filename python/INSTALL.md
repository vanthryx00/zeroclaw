# PhantomSwarm — Debian Installation Guide

**For authorized red team assessments and CTF engagements only.**

---

## 1. Prerequisites

Tested on: Debian 12 (Bookworm), Ubuntu 22.04+

```bash
sudo apt update && sudo apt install -y \
    python3 python3-pip python3-venv \
    git sqlite3 curl
```

---

## 2. Clone / Copy the Files

If you cloned the zeroclaw repo:
```bash
cd /opt
git clone https://github.com/vanthryx00/zeroclaw.git
cd zeroclaw/python
```

Or unzip the bundle if you have the ZIP:
```bash
unzip phantom_swarm_bundle.zip -d /opt/phantom
cd /opt/phantom
```

---

## 3. Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install python-dotenv
```

Optional — richer terminal output:
```bash
pip install rich
```

---

## 4. Environment Configuration

Create `.env` in the `python/` directory:

```bash
cp .env.example .env
nano .env
```

Edit these values:

```ini
# Your operator identity — watermarked on every mission
PHANTOM_OPERATOR=VANTHRYX

# HMAC key for watermark signing — CHANGE THIS to a long random string
PHANTOM_SECRET=change-this-to-a-long-random-secret-string

# Database paths (can be the same file or separate)
PHANTOM_DB=./phantom_swarm.db
```

Generate a strong secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 5. First Run — PhantomGraph (core engine)

```bash
source .venv/bin/activate

# Create an engagement
python phantom_graph.py scope --target example.com --org "Test Corp" --defender smb

# Build attack graph
python phantom_graph.py graph --engagement-id ENG-XXXXXX

# Find kill chains
python phantom_graph.py paths --engagement-id ENG-XXXXXX --top 5

# Generate operator briefing
python phantom_graph.py narrative --engagement-id ENG-XXXXXX
```

---

## 6. First Run — PhantomSwarm (13-agent system)

```bash
# Deploy 13-agent team against a target
python phantom_swarm.py deploy \
    --target example.com \
    --operator-id VANTHRYX \
    --defender enterprise \
    --objective data_exfiltration

# Check SENTINEL queue (tasks needing your approval)
python phantom_swarm.py status --mission-id MSN-XXXXXX

# Approve a HIGH-priority task
python phantom_swarm.py approve --mission-id MSN-XXXXXX --task-id <task-id>

# Full mission report
python phantom_swarm.py report --mission-id MSN-XXXXXX

# Verify your watermark / identity
python phantom_swarm.py watermark
```

---

## 7. HUD (Interactive Heads-Up Display)

```bash
# Live view, auto-refreshes every 5 seconds
python phantom_hud.py

# Pin to a specific mission
python phantom_hud.py --mission MSN-XXXXXX

# Single snapshot (no loop)
python phantom_hud.py --once
```

---

## 8. HackerOne Bounty Module

```bash
# Paste a program's scope page into a text file
nano scope.txt   # paste the program scope/rules from HackerOne

# Start new bounty (agents read, write, and proof the scope)
python phantom_bounty.py new --program "Acme Corp" --paste scope.txt

# Read the agent-written scope document
python phantom_bounty.py read --bounty-id BNT-XXXXXX

# Review and approve the checklist (you must check all 8 items)
python phantom_bounty.py approve --bounty-id BNT-XXXXXX
# Check one item at a time:
python phantom_bounty.py approve --bounty-id BNT-XXXXXX --check-item 1
# Or approve all at once:
python phantom_bounty.py approve --bounty-id BNT-XXXXXX --check-all

# Record a finding (once approved)
python phantom_bounty.py finding \
    --bounty-id BNT-XXXXXX \
    --title "Reflected XSS in search parameter" \
    --severity HIGH \
    --target "https://app.example.com/search" \
    --description "The q= parameter reflects unsanitized input into the DOM."

# Full report
python phantom_bounty.py report --bounty-id BNT-XXXXXX

# Export timestamped proof-of-work log (for submission evidence)
python phantom_bounty.py proof --bounty-id BNT-XXXXXX --output proof.txt
```

---

## 9. Multi-Target (HYDRA Deployment)

```bash
python phantom_swarm.py multi \
    --targets target-a.com target-b.com target-c.com \
    --operator-id VANTHRYX \
    --defender smb
```

---

## 10. ORACLE Evolution (self-learning)

After each engagement, record outcomes to improve future path scoring:

```bash
# Format: TECHNIQUE_ID:DEFENDER_PROFILE:DETECTED(0|1):SUCCEEDED(0|1)
python phantom_swarm.py evolve --record T1059:enterprise:0:1
python phantom_swarm.py evolve --record T1003:enterprise:1:0

# View evolution memory and defender pattern shifts
python phantom_swarm.py evolve --shifts
```

---

## 11. Systemd Service (optional — run HUD on boot)

```bash
sudo tee /etc/systemd/system/phantom-hud.service << 'EOF'
[Unit]
Description=PhantomSwarm HUD
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/opt/zeroclaw/python
ExecStart=/opt/zeroclaw/python/.venv/bin/python phantom_hud.py --once
Restart=no
EnvironmentFile=/opt/zeroclaw/python/.env

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable phantom-hud
```

---

## 12. File Reference

| File | Purpose |
|------|---------|
| `phantom_graph.py` | Probabilistic kill chain reasoning engine (core library) |
| `phantom_swarm.py` | 13-agent autonomous swarm (imports phantom_graph) |
| `phantom_hud.py`   | Interactive terminal HUD for live agent monitoring |
| `phantom_bounty.py`| HackerOne scope coordination + proof-of-work recorder |
| `.env`             | Operator identity + secrets (never commit this) |
| `phantom_swarm.db` | All missions, tasks, oracle memory, kill chains |
| `phantom_bounty.db`| All bounties, scope docs, findings, proof logs |

---

## 13. Security Notes

- Set `PHANTOM_SECRET` to a long random string; it signs every mission watermark.
- Never commit `.env` to git.
- The `PHANTOM_OPERATOR` value is embedded in every watermark — set it to your handle.
- All databases are SQLite files in the local directory; back them up.
- For additional isolation, run inside a Docker container or VM.

---

**All capabilities are for authorized assessments and CTF engagements only.**
Unauthorized access to computer systems is illegal. Know your scope.
