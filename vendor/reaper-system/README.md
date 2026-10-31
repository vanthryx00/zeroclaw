# REAPER SYSTEM — hardened Debian build v1.0.0
### PROJECT-STINGRAY · for Dubbz's HP / Debian drive · built 2026-10-25

One pack, one command, the whole stack from our sessions — installed in
locked order, verified at the end, safe to re-run.

## What's inside

```
reaper-system/
  reaper-system-setup.sh        THE installer (run this)
  components/
    wifi-fix-harden.sh          WiFi scan -> diagnose -> REBUILD -> harden
    privacy-stack-setup.sh      Tor + obfs4 privacy layer
    jarvis-v3.1.html            the assistant face (21 tools, bridge-ready)
    aegis-os-shell.html         OS launcher shell (living core, real state)
    jarvis-voice-server.py      offline voice: Whisper STT + Piper TTS (:8999)
    jarvis-voice.service
    install-voice-server.sh
    jarvis-bridge-server.py     command bridge (:9000) — reads/writes saved
                                code under $HOME, tiered, approval-gated,
                                every action written to an audit log
    jarvis-bridge.service
    install-bridge.sh
    aegis-offline-ai-copilot-v2+jarvis.zip   the Aegis copilot
```

## The build order (what the installer does)

1. **WIFI** — scans, diagnoses, rebuilds the connection (power-save off —
   the prime suspect in the ~5.7s latency), MAC randomization, NM
   phone-home off, WPS off, open/WEP audit.
2. **BASE** — apt essentials, Debian repos ONLY. Never Kali repos.
3. **DEFENSE** (new in this pack) — ufw firewall default-deny inbound
   (SSH reachable from LAN ranges only, if sshd exists), root login off,
   fail2ban on sshd, unattended security updates, sysctl kernel/network
   hardening. Password auth is KEPT — no lockout trap.
4. **PRIVACY** — Tor + obfs4 layer from the privacy stack.
5. **BRAIN** — Ollama from the official release tarball (no
   pipe-to-shell) + systemd service + models (disk-guarded):
   qwen2.5-coder:1.5b / qwen2.5-coder:7b / dolphin-llama3:8b.
6. **ASSISTANT** — JARVIS v3.1 to `~/jarvis.html`, OS shell to
   `~/aegis-os.html`, desktop launcher, voice service, bridge service,
   Aegis deployed to `~/arsenal/aegis`, compile check on all deployed
   Python, and a `~/bin/reaper-status` one-command health check.
7. **VERIFY** — full checklist written to `~/reaper-system-report.txt`.

## Run it

Transfer the folder to the Debian drive (phone USB), then on the drive:

```
cd ~/reaper-system
bash reaper-system-setup.sh
```

**GATE ZERO — read this first:** the installer stops cold if sudo is
broken. That's deliberate. Boot the drive, run `sudo whoami`. If it
denies: reboot once and try again (stale session is the usual cause).
If it still denies, log in as root and confirm `/etc/sudoers` contains
`%sudo ALL=(ALL:ALL) ALL`.

Needs network ONCE (apt, Ollama tarball, models ~11G, voice packages
~500MB). After that the whole system runs offline.

## Layer flags (re-run one piece anytime)

```
bash reaper-system-setup.sh --wifi       # rebuild WiFi only
bash reaper-system-setup.sh --defense    # firewall/hardening only
bash reaper-system-setup.sh --privacy
bash reaper-system-setup.sh --brain
bash reaper-system-setup.sh --assistant
bash reaper-system-setup.sh --verify     # report only, changes nothing
```

## After install

- Launch: **Reaper Assistant** desktop icon (or open `~/aegis-os.html`)
  → JARVIS button → `~/jarvis.html`.
- Endpoints (pre-set in JARVIS v3.1): brain `http://127.0.0.1:11434`,
  voice Whisper `http://127.0.0.1:8999/inference`, Piper
  `http://127.0.0.1:8999/tts`, bridge `http://127.0.0.1:9000`.
- Health anytime: `~/bin/reaper-status`
- Bridge audit log: `~/arsenal/jarvis-bridge/audit.log`
- Stop a service: `sudo systemctl stop jarvis-bridge` (or jarvis-voice,
  ollama, tor). Disable at boot: same command with `disable`.

## Honesty notes

- Every component in this pack is the exact code built and tested in
  our sessions (bridge: 17-case suite green; voice: stdlib server;
  wifi/privacy scripts: syntax-verified). The DEFENSE module and this
  orchestration are new in v1.0.0 and are verified by the end-of-run
  report on YOUR machine — read `~/reaper-system-report.txt` after the
  run and send it to Vigil if anything shows down.
- Nothing here phones home. Ollama, voice, and bridge bind to
  127.0.0.1 only.
- No client/sensitive data through any cloud model — the brain is
  local Ollama; dolphin-llama3:8b remains the private-work model.
