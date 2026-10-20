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

```bash
cd /opt
git clone https://github.com/vanthryx00/zeroclaw.git
cd zeroclaw/python
```

Or unzip the bundle:
```bash
unzip phantom_swarm_bundle.zip -d /opt/phantom
cd /opt/phantom
```

---

## 3. Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Environment Configuration

```bash
cp .env.example .env
nano .env
```

```ini
# Your operator identity — watermarked on every mission
PHANTOM_OPERATOR=VANTHRYX

# HMAC key for watermark signing
PHANTOM_SECRET=change-this-to-a-long-random-secret-string

# Database path
PHANTOM_DB=./phantom_swarm.db
```

Generate a strong secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 5. PhantomGraph (core engine)

```bash
source .venv/bin/activate

# Create an engagement
python phantom_graph.py scope --target example.com --org "Test Corp" --defender smb

# Build attack graph + kill chains
python phantom_graph.py graph --engagement-id ENG-XXXXXX
python phantom_graph.py paths --engagement-id ENG-XXXXXX --top 5

# Operator briefing
python phantom_graph.py narrative --engagement-id ENG-XXXXXX

# LotL advisor
python phantom_graph.py lotl --os windows --priv user
```

---

## 6. PhantomSwarm (13-agent system)

```bash
# Deploy 13-agent team
python phantom_swarm.py deploy \
    --target example.com \
    --operator-id VANTHRYX \
    --defender enterprise \
    --objective data_exfiltration

# Check SENTINEL queue
python phantom_swarm.py status --mission-id MSN-XXXXXX

# Approve a task
python phantom_swarm.py approve --mission-id MSN-XXXXXX --task-id <task-id>

# Full report
python phantom_swarm.py report --mission-id MSN-XXXXXX

# Verify watermark
python phantom_swarm.py watermark
```

---

## 7. HUD (Interactive Heads-Up Display)

```bash
# Live view, auto-refresh every 5s
python phantom_hud.py

# Pin to a specific mission
python phantom_hud.py --mission MSN-XXXXXX

# Single snapshot
python phantom_hud.py --once
```

---

## 8. HackerOne Bounty Module

```bash
# Save program scope/rules to a text file
nano scope.txt

# Start new bounty — 3 agents analyze the scope
python phantom_bounty.py new --program "Acme Corp" --paste scope.txt

# Read agent-written scope document
python phantom_bounty.py read --bounty-id BNT-XXXXXX

# Approve checklist (must check all 8 items)
python phantom_bounty.py approve --bounty-id BNT-XXXXXX --check-all

# Record a finding
python phantom_bounty.py finding \
    --bounty-id BNT-XXXXXX \
    --title "Reflected XSS in search parameter" \
    --severity HIGH \
    --target "https://app.example.com/search" \
    --description "The q= parameter reflects unsanitized input."

# Full report
python phantom_bounty.py report --bounty-id BNT-XXXXXX

# Export timestamped proof-of-work log
python phantom_bounty.py proof --bounty-id BNT-XXXXXX --output proof.txt
```

---

## 9. Multi-Target (HYDRA)

```bash
python phantom_swarm.py multi \
    --targets target-a.com target-b.com target-c.com \
    --operator-id VANTHRYX \
    --defender smb
```

---

## 10. ORACLE Evolution

```bash
# Record outcomes after each engagement
# Format: TECHNIQUE_ID:DEFENDER_PROFILE:DETECTED(0|1):SUCCEEDED(0|1)
python phantom_swarm.py evolve --record T1059:enterprise:0:1

# View evolution memory and defender pattern shifts
python phantom_swarm.py evolve --shifts
```

---

## 11. File Reference

| File | Purpose |
|------|--------|
| `phantom_graph.py` | Probabilistic kill chain reasoning engine |
| `phantom_swarm.py` | 13-agent autonomous swarm |
| `phantom_hud.py`   | Interactive terminal HUD |
| `phantom_bounty.py`| HackerOne scope + proof-of-work recorder |
| `.env`             | Operator identity + secrets (never commit) |
| `requirements.txt` | Python dependencies |

---

**All capabilities are for authorized assessments and CTF engagements only.**  
Unauthorized access to computer systems is illegal. Know your scope.
