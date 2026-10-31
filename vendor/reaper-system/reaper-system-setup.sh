#!/usr/bin/env bash
# ============================================================
# REAPER SYSTEM — hardened Debian build  v1.0.0
# PROJECT-STINGRAY edition. ONE installer for the whole stack
# built across our sessions, in locked order:
#   1 WIFI      scan + diagnose + REBUILD + harden
#               (components/wifi-fix-harden.sh — the latency fix)
#   2 BASE      apt essentials, Debian repos ONLY (never Kali)
#   3 DEFENSE   firewall (default-deny inbound), SSH lockdown,
#               fail2ban, security auto-updates, sysctl hardening
#   4 PRIVACY   Tor + obfs4 layer (components/privacy-stack-setup.sh)
#   5 BRAIN     Ollama + models (release tarball, no pipe-to-shell)
#   6 ASSISTANT the Ultron-style desktop assistant (JARVIS v3.1):
#               ~/jarvis.html + AEGIS OS shell, offline voice
#               (Whisper/Piper :8999), command bridge (:9000) —
#               the guardian that reads and writes your saved
#               code under $HOME, tiered + approval-gated,
#               every action audit-logged
#   7 VERIFY    full checklist -> ~/reaper-system-report.txt
#
# Run as the normal user (it uses sudo itself):
#   bash reaper-system-setup.sh            full build
#   bash reaper-system-setup.sh --verify   report only, change nothing
#   bash reaper-system-setup.sh --wifi     one layer at a time:
#   bash reaper-system-setup.sh --defense  --privacy --brain --assistant
#
# GATE ZERO: sudo must work. If preflight stops, reboot the
# drive and run:  sudo whoami
# If it still denies, log in as root and check /etc/sudoers for:
#   %sudo ALL=(ALL:ALL) ALL
#
# Idempotent — safe to re-run; replaced configs are backed up
# as *.pre-reaper. NOT installed, on purpose: Metasploit (not
# in Debian repos), Kali anything (breaks Debian — never).
# ============================================================

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
COMP="$HERE/components"
DO_WIFI=0; DO_BASE=0; DO_DEFENSE=0; DO_PRIVACY=0; DO_BRAIN=0; DO_ASSISTANT=0; VERIFY_ONLY=0
if [ $# -eq 0 ]; then DO_WIFI=1; DO_BASE=1; DO_DEFENSE=1; DO_PRIVACY=1; DO_BRAIN=1; DO_ASSISTANT=1; fi
for a in "$@"; do
  case "$a" in
    --all) DO_WIFI=1; DO_BASE=1; DO_DEFENSE=1; DO_PRIVACY=1; DO_BRAIN=1; DO_ASSISTANT=1 ;;
    --wifi) DO_WIFI=1 ;;
    --base) DO_BASE=1 ;;
    --defense) DO_DEFENSE=1 ;;
    --privacy) DO_PRIVACY=1 ;;
    --brain) DO_BRAIN=1 ;;
    --assistant) DO_ASSISTANT=1 ;;
    --verify) VERIFY_ONLY=1 ;;
    *) echo "unknown flag: $a (use --all, --wifi, --base, --defense, --privacy, --brain, --assistant, --verify)"; exit 2 ;;
  esac
done

C_OK="\033[1;32m"; C_STEP="\033[1;36m"; C_WARN="\033[1;33m"; C_ERR="\033[1;31m"; C_OFF="\033[0m"
say()  { printf "${C_STEP}== %s ==${C_OFF}\n" "$*"; }
ok()   { printf "${C_OK}  ok: %s${C_OFF}\n" "$*"; }
warn() { printf "${C_WARN}  warn: %s${C_OFF}\n" "$*"; }
die()  { printf "${C_ERR}  STOP: %s${C_OFF}\n" "$*"; exit 3; }
have() { command -v "$1" >/dev/null 2>&1; }

REPORT="$HOME/reaper-system-report.txt"
ARSENAL="$HOME/arsenal"
mkdir -p "$ARSENAL" "$HOME/reaper-code" "$HOME/bin"

# ------------------------------------------------------------
say "PREFLIGHT"
grep -qi debian /etc/os-release || die "this is not Debian — stopping"
if [ "$VERIFY_ONLY" = "0" ]; then
  sudo -v || die "sudo refused (GATE ZERO). Reboot the drive, retry 'sudo whoami'. If it still denies: as root, run  grep '^%sudo' /etc/sudoers  — the line must read: %sudo ALL=(ALL:ALL) ALL"
  ok "sudo works"
fi
FREE_GB=$(df -BG "$HOME" | tail -1 | awk '{print $4}' | tr -d 'G')
[ "${FREE_GB:-0}" -ge 25 ] || warn "only ${FREE_GB}G free — models alone want ~11G; the brain layer self-skips pulls under 15G"
ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && ok "network up" || warn "no network ping — wifi layer runs first to fix exactly this; downloads will fail until it does"

# ------------------------------------------------------------
if [ "$DO_WIFI" = "1" ]; then
  say "WIFI: scan, diagnose, rebuild, harden"
  if [ -f "$COMP/wifi-fix-harden.sh" ]; then
    sudo bash "$COMP/wifi-fix-harden.sh" || warn "wifi layer returned non-zero — its report above says what it found"
  else warn "wifi-fix-harden.sh missing from components/ — skipped"; fi
fi

# ------------------------------------------------------------
if [ "$DO_BASE" = "1" ]; then
  say "BASE: apt essentials (Debian repos only)"
  sudo apt-get update || warn "apt update failed — check sources/network"
  sudo apt-get install -y git curl wget jq ripgrep fd-find tree htop unzip zip \
    build-essential python3 python3-pip python3-venv \
    nmap dnsutils net-tools iproute2 socat tshark \
    iw rfkill wireless-regdb can-utils ca-certificates gnupg \
    ufw fail2ban unattended-upgrades \
    || warn "some packages failed — re-run to retry the gaps"
  for t in git python3 pip3 nmap tshark cansend ufw; do have "$t" && ok "$t" || warn "missing: $t"; done
fi

# ------------------------------------------------------------
if [ "$DO_DEFENSE" = "1" ]; then
  say "DEFENSE: firewall — default-deny inbound, allow outbound"
  if have ufw; then
    sudo ufw --force reset >/dev/null 2>&1 || true
    sudo ufw default deny incoming >/dev/null
    sudo ufw default allow outgoing >/dev/null
    if [ -f /etc/ssh/sshd_config ] || systemctl list-unit-files 2>/dev/null | grep -q '^ssh\.service'; then
      for net in 192.168.0.0/16 10.0.0.0/8 172.16.0.0/12; do
        sudo ufw allow from "$net" to any port 22 proto tcp >/dev/null && ok "ssh allowed from LAN range $net only"
      done
    else
      ok "no sshd present — no inbound rules opened at all"
    fi
    sudo ufw --force enable >/dev/null && ok "firewall ON"
  else warn "ufw not installed — run the --base layer first"; fi

  say "DEFENSE: SSH lockdown (password auth KEPT — no lockout trap)"
  if [ -f /etc/ssh/sshd_config ]; then
    sudo cp -n /etc/ssh/sshd_config /etc/ssh/sshd_config.pre-reaper 2>/dev/null || true
    sudo sed -i -E 's/^#?PermitRootLogin.*/PermitRootLogin no/; s/^#?X11Forwarding.*/X11Forwarding no/; s/^#?MaxAuthTries.*/MaxAuthTries 3/' /etc/ssh/sshd_config
    grep -q '^PermitRootLogin' /etc/ssh/sshd_config || echo "PermitRootLogin no" | sudo tee -a /etc/ssh/sshd_config >/dev/null
    sudo systemctl restart ssh 2>/dev/null || sudo systemctl restart sshd 2>/dev/null || warn "ssh restart skipped — applies on next start"
    ok "root login off, X11 forwarding off, auth tries capped at 3"
    if have fail2ban-client; then
      printf '[sshd]\nenabled = true\nmaxretry = 4\nbantime = 1h\n' | sudo tee /etc/fail2ban/jail.d/reaper-sshd.conf >/dev/null
      sudo systemctl enable --now fail2ban >/dev/null 2>&1 && ok "fail2ban guarding sshd (4 strikes, 1h ban)" || warn "fail2ban did not start"
    fi
  else ok "no sshd_config — nothing to lock down"; fi

  say "DEFENSE: security auto-updates + kernel network hardening"
  if [ -d /etc/apt/apt.conf.d ]; then
    printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' | sudo tee /etc/apt/apt.conf.d/20auto-upgrades.reaper >/dev/null
    ok "unattended security upgrades enabled"
  fi
  sudo tee /etc/sysctl.d/99-reaper-hardening.conf >/dev/null <<'EOF'
# REAPER hardening — network + kernel
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv4.tcp_syncookies = 1
net.ipv4.icmp_echo_ignore_broadcasts = 1
net.ipv4.conf.all.log_martians = 1
kernel.ptrace_scope = 1
kernel.dmesg_restrict = 1
EOF
  sudo sysctl --system >/dev/null 2>&1 && ok "sysctl hardening applied" || warn "sysctl apply partial — see report"
  echo "  listening ports after hardening:"
  ss -tulnp 2>/dev/null | sed 's/^/    /' | head -20
fi

# ------------------------------------------------------------
if [ "$DO_PRIVACY" = "1" ]; then
  say "PRIVACY: Tor + obfs4 guardian layer"
  if [ -f "$COMP/privacy-stack-setup.sh" ]; then
    sudo bash "$COMP/privacy-stack-setup.sh" || warn "privacy layer returned non-zero — its output above says why"
  else warn "privacy-stack-setup.sh missing from components/ — skipped"; fi
fi

# ------------------------------------------------------------
if [ "$DO_BRAIN" = "1" ]; then
  say "BRAIN: Ollama local models"
  if have ollama; then
    ok "ollama already installed: $(ollama --version 2>/dev/null | head -1)"
  else
    TMPD=$(mktemp -d)
    curl -fL -o "$TMPD/ollama.tgz" "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tgz" \
      || die "ollama download failed — check network, re-run"
    sudo tar -C /usr/local -xzf "$TMPD/ollama.tgz" || die "ollama extract failed"
    rm -rf "$TMPD"
    id ollama >/dev/null 2>&1 || sudo useradd -r -s /usr/sbin/nologin -m -d /usr/share/ollama ollama
    sudo usermod -aG ollama "$USER" || true
    if [ ! -f /etc/systemd/system/ollama.service ]; then
      sudo tee /etc/systemd/system/ollama.service >/dev/null <<'EOF'
[Unit]
Description=Ollama Service
After=network-online.target
[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
[Install]
WantedBy=default.target
EOF
      sudo systemctl daemon-reload
    fi
    sudo systemctl enable --now ollama || warn "ollama service did not start — try: ollama serve (manual)"
    ok "ollama installed"
  fi
  sleep 2
  curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && ok "ollama API live on 127.0.0.1:11434" || warn "ollama API not answering yet — check: systemctl status ollama"
  say "BRAIN: models (~11G total — pulls self-skip under 15G free)"
  if [ "${FREE_GB:-0}" -ge 15 ]; then
    for m in qwen2.5-coder:1.5b qwen2.5-coder:7b dolphin-llama3:8b; do
      ollama pull "$m" && ok "model: $m" || warn "model pull failed: $m"
    done
  else
    warn "not enough free space — pull later with: ollama pull qwen2.5-coder:7b"
  fi
fi

# ------------------------------------------------------------
if [ "$DO_ASSISTANT" = "1" ]; then
  say "ASSISTANT: the desktop guardian (JARVIS v3.1 — Ultron-style build)"
  [ -f "$COMP/jarvis-v3.1.html" ] && cp "$COMP/jarvis-v3.1.html" "$HOME/jarvis.html" && ok "assistant face at ~/jarvis.html (v3.1, 21 tools, bridge-ready)" || warn "jarvis-v3.1.html missing — skipped"
  [ -f "$COMP/aegis-os-shell.html" ] && cp "$COMP/aegis-os-shell.html" "$HOME/aegis-os.html" && ok "OS shell at ~/aegis-os.html" || warn "aegis-os-shell.html missing — skipped"
  mkdir -p "$HOME/Desktop"
  cat > "$HOME/Desktop/Reaper-Assistant.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Reaper Assistant
Exec=xdg-open $HOME/aegis-os.html
Icon=utilities-terminal
Terminal=false
Categories=Utility;
EOF
  chmod +x "$HOME/Desktop/Reaper-Assistant.desktop" && ok "desktop launcher: Reaper Assistant"

  say "ASSISTANT: offline voice (Whisper hears, Piper speaks — :8999)"
  if [ -f "$COMP/install-voice-server.sh" ]; then
    ( cd "$COMP" && bash install-voice-server.sh ) || warn "voice layer returned non-zero — bridge + face still work; voice retries on re-run"
  else warn "install-voice-server.sh missing — skipped"; fi

  say "ASSISTANT: command bridge — reads/writes your saved code (:9000)"
  if [ -f "$COMP/install-bridge.sh" ]; then
    ( cd "$COMP" && bash install-bridge.sh ) || warn "bridge layer returned non-zero — see its output above"
  else warn "install-bridge.sh missing — skipped"; fi

  say "ASSISTANT: code vault — Aegis + saved-code workspace"
  if [ -f "$COMP/aegis-offline-ai-copilot-v2+jarvis.zip" ]; then
    mkdir -p "$ARSENAL/aegis"
    unzip -o -q "$COMP/aegis-offline-ai-copilot-v2+jarvis.zip" -d "$ARSENAL/aegis" && ok "Aegis deployed to ~/arsenal/aegis" || warn "aegis unzip failed"
  fi
  FAIL=0
  while IFS= read -r f; do
    python3 -m py_compile "$f" 2>/dev/null || { warn "compile FAIL: $f"; FAIL=1; }
  done < <(find "$ARSENAL" -name "*.py" -not -path "*/venv/*" 2>/dev/null | head -80)
  [ "$FAIL" = "0" ] && ok "all deployed python compiles" || warn "some files failed compile check — see above"

  cat > "$HOME/bin/reaper-status" <<'EOF'
#!/usr/bin/env bash
# REAPER STATUS — one command, whole guard post
echo "--- services ---"
for s in ollama jarvis-voice jarvis-bridge NetworkManager ufw fail2ban tor; do
  printf "  %-16s %s\n" "$s" "$(systemctl is-active $s 2>/dev/null || echo n/a)"
done
echo "--- endpoints ---"
curl -s http://127.0.0.1:11434/api/tags >/dev/null && echo "  brain   :11434 OK" || echo "  brain   :11434 DOWN"
curl -s http://127.0.0.1:8999/health >/dev/null && echo "  voice   :8999  OK" || echo "  voice   :8999  DOWN"
curl -s http://127.0.0.1:9000/health >/dev/null && echo "  bridge  :9000  OK" || echo "  bridge  :9000  DOWN"
echo "--- models ---"; ollama list 2>/dev/null | tail -n +2 | sed 's/^/  /'
echo "--- wifi ---"; iw dev 2>/dev/null | grep -E 'Interface|ssid' | sed 's/^/  /'
ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && echo "  net: up" || echo "  net: DOWN"
EOF
  chmod +x "$HOME/bin/reaper-status" && ok "one-command status: reaper-status (in ~/bin)"
fi

# ------------------------------------------------------------
say "VERIFY — the whole guard post"
{
  echo "REAPER SYSTEM REPORT — $(date) — $(hostname)"
  echo "os:      $(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"')"
  echo "python:  $(python3 --version 2>&1)"
  echo "disk:    $(df -h "$HOME" | tail -1 | awk '{print $4}') free"
  echo ""
  echo "[wifi]"
  iw dev 2>/dev/null | grep -E 'Interface|ssid' || echo "  no wireless interface seen"
  ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && echo "  net: UP" || echo "  net: DOWN"
  echo "[defense]"
  sudo ufw status 2>/dev/null | head -3 || echo "  ufw: not readable without sudo"
  systemctl is-active fail2ban >/dev/null 2>&1 && echo "  fail2ban: active" || echo "  fail2ban: inactive/absent"
  [ -f /etc/sysctl.d/99-reaper-hardening.conf ] && echo "  sysctl hardening: present" || echo "  sysctl hardening: absent"
  echo "[privacy]"
  systemctl is-active tor >/dev/null 2>&1 && echo "  tor: active" || echo "  tor: inactive/absent"
  echo "[brain]"
  curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && echo "  ollama API: LIVE" || echo "  ollama API: down"
  ollama list 2>/dev/null | tail -n +2 | sed 's/^/  model: /'
  echo "[assistant]"
  [ -f "$HOME/jarvis.html" ] && echo "  face: ~/jarvis.html present" || echo "  face: MISSING"
  curl -s http://127.0.0.1:8999/health >/dev/null 2>&1 && echo "  voice :8999 LIVE" || echo "  voice :8999 down"
  curl -s http://127.0.0.1:9000/health >/dev/null 2>&1 && echo "  bridge :9000 LIVE" || echo "  bridge :9000 down"
  echo "  bridge audit log: $ARSENAL/jarvis-bridge/audit.log"
  echo "[arsenal]"
  ls "$ARSENAL" 2>/dev/null | sed 's/^/  /'
} | tee "$REPORT"
echo ""
echo "DONE. Report saved: $REPORT"
echo "LAUNCH: open ~/aegis-os.html (or the Reaper Assistant desktop icon) -> JARVIS button"
echo "        brain http://127.0.0.1:11434 - voice http://127.0.0.1:8999 - bridge http://127.0.0.1:9000"
echo "STATUS ANYTIME: ~/bin/reaper-status"
