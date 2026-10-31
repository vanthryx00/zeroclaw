#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'; BLUE='\033[0;34m'; RED='\033[0;31m'; NC='\033[0m'
log() { echo -e "${BLUE}[BugReaper]${NC} $1"; }
ok()  { echo -e "${GREEN}[✓]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

log "BugReaper X v4.0 — Linux Installer"
log "Kairyx Security Solutions, Fort Saskatchewan, Alberta"

[[ $EUID -ne 0 ]] && err "Run as root: sudo bash install-linux.sh"

INSTALL_DIR="/opt/bugreaper"
SERVICE_USER="bugreaper"
PYTHON_MIN="3.11"

detect_distro() {
    if command -v apt-get &>/dev/null; then echo "debian"
    elif command -v dnf &>/dev/null; then echo "fedora"
    elif command -v pacman &>/dev/null; then echo "arch"
    else err "Unsupported Linux distribution"; fi
}

DISTRO=$(detect_distro)
log "Detected: $DISTRO"

install_deps() {
    case $DISTRO in
    debian)
        apt-get update -qq
        apt-get install -y -qq python3 python3-pip python3-venv git curl wget nmap nikto dirb \
            wireshark-common tcpdump netcat-openbsd dnsutils openssl libssl-dev build-essential
        ;;
    fedora)
        dnf install -y python3 python3-pip git curl wget nmap nikto tcpdump bind-utils openssl \
            openssl-devel gcc python3-devel
        ;;
    arch)
        pacman -Sy --noconfirm python python-pip git curl wget nmap nikto tcpdump bind-tools openssl
        ;;
    esac
}

log "Installing system dependencies..."
install_deps
ok "System dependencies installed"

if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
    ok "Created service user: $SERVICE_USER"
fi

log "Setting up installation directory..."
mkdir -p "$INSTALL_DIR"
cp -r . "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

log "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -e "$INSTALL_DIR" -q
ok "Python environment ready"

log "Installing systemd service..."
cat > /etc/systemd/system/bugreaper.service << EOF
[Unit]
Description=BugReaper X REAPER API Service
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/bugreaper serve --host 0.0.0.0 --port 8900
Restart=on-failure
RestartSec=5
Environment=BUGREAPER_DEBUG=false
EnvironmentFile=-$INSTALL_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable bugreaper
ok "Systemd service installed"

if command -v ufw &>/dev/null; then
    ufw allow 8900/tcp comment "BugReaper X API" 2>/dev/null || true
    ufw allow 8901/tcp comment "BugReaper X VR Bridge" 2>/dev/null || true
elif command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port=8900/tcp 2>/dev/null || true
    firewall-cmd --permanent --add-port=8901/tcp 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi
ok "Firewall rules configured"

for shell_rc in /root/.bashrc /root/.zshrc /home/*/.bashrc /home/*/.zshrc; do
    [[ -f "$shell_rc" ]] && grep -q "bugreaper" "$shell_rc" 2>/dev/null && continue
    [[ -f "$shell_rc" ]] && cat >> "$shell_rc" << 'EOF'
alias br="bugreaper"
alias breaper="bugreaper"
EOF
done

ln -sf "$INSTALL_DIR/venv/bin/bugreaper" /usr/local/bin/bugreaper
ln -sf "$INSTALL_DIR/venv/bin/bugreaper" /usr/local/bin/br
ok "CLI commands installed: bugreaper, br"

log ""
log "═══════════════════════════════════════════════"
ok "BugReaper X v4.0 installed successfully!"
log ""
log "  Start service:  systemctl start bugreaper"
log "  API server:     http://localhost:8900"
log "  CLI scan:       bugreaper scan https://target.com"
log "  Quick scan:     br quick https://target.com"
log ""
log "  Configure:      $INSTALL_DIR/.env"
log "  Set BUGREAPER_ANTHROPIC_API_KEY for REAPER AI"
log "═══════════════════════════════════════════════"
