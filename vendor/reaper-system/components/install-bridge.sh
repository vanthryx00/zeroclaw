#!/usr/bin/env bash
# ============================================================
# INSTALL: JARVIS COMMAND BRIDGE on Debian (PROJECT-STINGRAY)
# Stdlib-only server — no venv, no downloads. Copies the server
# into ~/arsenal/jarvis-bridge, installs the systemd service,
# health-checks it, and runs a safe self-test (df + a deny case).
# Run as the normal user (uses sudo itself):
#   bash install-bridge.sh
# GATE: sudo must work (same gate as the main Debian setup).
# ============================================================
set -u
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/arsenal/jarvis-bridge"
say()  { printf "== %s ==\n" "$*"; }
ok()   { printf "  ok: %s\n" "$*"; }
warn() { printf "  warn: %s\n" "$*"; }
die()  { printf "  STOP: %s\n" "$*"; exit 3; }

say "PREFLIGHT"
[ -f "$SRC_DIR/jarvis-bridge-server.py" ] || die "jarvis-bridge-server.py not beside this script"
[ -f "$SRC_DIR/jarvis-bridge.service" ] || die "jarvis-bridge.service not beside this script"
sudo -v || die "sudo refused — reboot, run 'sudo whoami', fix /etc/sudoers if needed"

say "LAYOUT: $DEST"
mkdir -p "$DEST"
cp "$SRC_DIR/jarvis-bridge-server.py" "$DEST/"
cp "$SRC_DIR/jarvis-bridge.service" "$DEST/"
ok "server + unit copied"

say "SERVICE: install + start"
sudo cp "$SRC_DIR/jarvis-bridge.service" /etc/systemd/system/jarvis-bridge.service
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-bridge || warn "service didn't start — check: systemctl status jarvis-bridge"

say "VERIFY"
sleep 2
curl -s http://127.0.0.1:9000/health && echo && ok "bridge answering on 127.0.0.1:9000" || warn "no answer on /health yet"
echo "self-test (read tier — must succeed):"
curl -s -X POST http://127.0.0.1:9000/run -H 'Content-Type: application/json' -d '{"command":"df -h /"}' | head -c 300; echo
echo "self-test (deny tier — must be denied):"
curl -s -X POST http://127.0.0.1:9000/run -H 'Content-Type: application/json' -d '{"command":"rm -rf /"}'; echo
echo "self-test (write tier — must ask for approval, NOT run):"
curl -s -X POST http://127.0.0.1:9000/run -H 'Content-Type: application/json' -d '{"command":"systemctl restart ollama"}'; echo
echo ""
echo "POINT JARVIS AT IT: bridge endpoint http://127.0.0.1:9000 (pre-set in JARVIS v3.1)."
echo "Audit log: $DEST/audit.log"
