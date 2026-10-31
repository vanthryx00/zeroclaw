#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
log() { echo -e "${BLUE}[BugReaper]${NC} $1"; }
ok()  { echo -e "${GREEN}[✓]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

log "BugReaper X v4.0 — macOS Installer"
log "Kairyx Security Solutions"

INSTALL_DIR="$HOME/.bugreaper"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/io.kairyx.bugreaper.plist"

if ! command -v brew &>/dev/null; then
    log "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
ok "Homebrew available"

log "Installing dependencies via Homebrew..."
brew install python@3.11 git nmap openssl wget 2>/dev/null || true
ok "Homebrew dependencies installed"

log "Setting up installation directory..."
mkdir -p "$INSTALL_DIR"
cp -r . "$INSTALL_DIR/"

log "Creating Python virtual environment..."
python3.11 -m venv "$INSTALL_DIR/venv" 2>/dev/null || python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -e "$INSTALL_DIR" -q
ok "Python environment ready"

mkdir -p "$PLIST_DIR"
cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.kairyx.bugreaper</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/venv/bin/bugreaper</string>
        <string>serve</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>8900</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/logs/stderr.log</string>
</dict>
</plist>
EOF

mkdir -p "$INSTALL_DIR/logs"
launchctl load "$PLIST_FILE" 2>/dev/null || true
ok "launchd service installed"

for shell_rc in "$HOME/.zshrc" "$HOME/.bashrc"; do
    [[ -f "$shell_rc" ]] || continue
    grep -q "bugreaper" "$shell_rc" 2>/dev/null && continue
    cat >> "$shell_rc" << EOF

# BugReaper X
export PATH="\$PATH:$INSTALL_DIR/venv/bin"
alias br="bugreaper"
alias breaper="bugreaper"
EOF
done
ok "Shell aliases added"

log ""
ok "BugReaper X v4.0 installed on macOS!"
log ""
log "  CLI scan:   bugreaper scan https://target.com"
log "  API:        http://127.0.0.1:8900"
log "  Configure:  $INSTALL_DIR/.env"
log "  Restart:    launchctl unload $PLIST_FILE && launchctl load $PLIST_FILE"
log ""
log "  Set BUGREAPER_ANTHROPIC_API_KEY in $INSTALL_DIR/.env for REAPER AI"
