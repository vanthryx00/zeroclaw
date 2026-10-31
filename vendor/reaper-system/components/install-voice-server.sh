#!/usr/bin/env bash
# ============================================================
# INSTALL: JARVIS VOICE SERVER on Debian (PROJECT-STINGRAY)
# Creates ~/arsenal/jarvis-voice with a venv (faster-whisper +
# piper-tts), downloads the Piper voice, installs the systemd
# service, and health-checks it. Needs network ONCE (packages +
# models, ~500 MB total). After that: fully offline.
#
# Run as the normal user (uses sudo itself):
#   bash install-voice-server.sh
# Files expected beside this script (or pass their folder):
#   jarvis-voice-server.py, jarvis-voice.service
# GATE: sudo must work (same gate as the main Debian setup).
# ============================================================
set -u
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/arsenal/jarvis-voice"
VOICE_URL_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"

C_OK="\033[1;32m"; C_STEP="\033[1;36m"; C_WARN="\033[1;33m"; C_ERR="\033[1;31m"; C_OFF="\033[0m"
say()  { printf "${C_STEP}== %s ==${C_OFF}\n" "$*"; }
ok()   { printf "${C_OK}  ok: %s${C_OFF}\n" "$*"; }
warn() { printf "${C_WARN}  warn: %s${C_OFF}\n" "$*"; }
die()  { printf "${C_ERR}  STOP: %s${C_OFF}\n" "$*"; exit 3; }

say "PREFLIGHT"
[ -f "$SRC_DIR/jarvis-voice-server.py" ] || die "jarvis-voice-server.py not beside this script"
[ -f "$SRC_DIR/jarvis-voice.service" ] || die "jarvis-voice.service not beside this script"
sudo -v || die "sudo refused — reboot, run 'sudo whoami', fix /etc/sudoers if needed (see main setup)"
command -v python3 >/dev/null || die "python3 missing — run debian-ultimate-setup.sh first"
python3 -c "import venv" 2>/dev/null || sudo apt-get install -y python3-venv || die "python3-venv unavailable"

say "LAYOUT: $DEST"
mkdir -p "$DEST/voices"
cp "$SRC_DIR/jarvis-voice-server.py" "$DEST/"
cp "$SRC_DIR/jarvis-voice.service" "$DEST/"
ok "server + unit copied"

say "VENV + PACKAGES (the slow part — faster-whisper pulls a few hundred MB)"
[ -d "$DEST/venv" ] || python3 -m venv "$DEST/venv" || die "venv creation failed"
"$DEST/venv/bin/pip" install --upgrade pip >/dev/null 2>&1
"$DEST/venv/bin/pip" install faster-whisper piper-tts || die "pip install failed — check network, re-run"
ok "packages in"

say "PIPER VOICE: en_US-lessac-medium (~65 MB, downloads once)"
V="$DEST/voices/en_US-lessac-medium"
[ -f "$V.onnx" ] || curl -fL -o "$V.onnx" "$VOICE_URL_BASE/en_US-lessac-medium.onnx" || die "voice .onnx download failed"
[ -f "$V.onnx.json" ] || curl -fL -o "$V.onnx.json" "$VOICE_URL_BASE/en_US-lessac-medium.onnx.json" || die "voice .json download failed"
ok "voice present: $(du -h "$V.onnx" | cut -f1)"

say "SERVICE: install + start"
sudo cp "$SRC_DIR/jarvis-voice.service" /etc/systemd/system/jarvis-voice.service
sudo systemctl daemon-reload
sudo systemctl enable --now jarvis-voice || warn "service didn't start — check: systemctl status jarvis-voice"

say "VERIFY"
sleep 3
if curl -s http://127.0.0.1:8999/health; then echo; ok "voice server answering on 127.0.0.1:8999"
else warn "no answer yet on /health — first Whisper use also downloads its model (~40-75 MB), give it a minute and retry: curl http://127.0.0.1:8999/health"; fi
echo ""
echo "POINT JARVIS AT IT (Voice Lab panel):"
echo "  Whisper STT endpoint: http://127.0.0.1:8999/inference"
echo "  Piper TTS endpoint:   http://127.0.0.1:8999/tts"
echo "Whisper model is 'tiny' (fast on CPU). For 'base': sudo systemctl edit jarvis-voice,"
echo "set JARVIS_WHISPER_MODEL=base, then sudo systemctl restart jarvis-voice."
