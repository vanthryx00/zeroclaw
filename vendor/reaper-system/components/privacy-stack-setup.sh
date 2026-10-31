#!/usr/bin/env bash
# ============================================================================
#  privacy-stack-setup.sh — one-run Debian privacy stack
# ============================================================================
#  Sets up, in one run:
#    1. Mullvad VPN      (OPTIONAL — skipped cleanly without an account number)
#    2. Tor + obfs4      (Tor with a bridge transport, harder to fingerprint)
#    3. Proxychains      (push any app's traffic through Tor)
#    4. MAC spoofing     (your network card shows a random address each boot)
#    5. Amnesic boot     (extra boot menu entry: nothing is saved to disk)
#
#  WHAT EACH LAYER DOES — AND DOES NOT — DO
#    VPN:      hides your traffic from your internet provider and your IP
#              from sites. The VPN company can still see you use it. It does
#              NOT make you anonymous on its own.
#    Tor:      routes traffic through three relays so no single point knows
#              both you and where you're going. Slow. Sites may block it.
#    obfs4:    disguises Tor traffic so a network watching the wire can't
#              easily tell it's Tor. Needs bridge lines (see step 2 notes).
#    Proxychains: forces individual apps through Tor even if they have no
#              proxy settings. Leaks are still possible if an app ignores it.
#    MAC spoof: hides your hardware address from the local network (cafe
#              wifi, etc). Does nothing beyond that local network.
#    Amnesic:  boots with changes kept in memory only — power off and the
#              session is gone. It does NOT encrypt your disk, and files you
#              deliberately save to a mounted drive still exist there.
#
#  NO LAYER HERE = TOTAL ANONYMITY. Browsing habits, logins, and what you
#  type into sites can still identify you. This stack reduces exposure;
#  it does not erase you.
#
#  Rules this script follows:
#    - Installs only from Debian's official repositories and Mullvad's
#      official client. Nothing cracked, nothing patched.
#    - The VPN layer is optional and never blocks the other layers.
#    - No accounts, logins, or telemetry are baked in. Your Mullvad number
#      is typed at run time and never written into this script.
#    - Every file it replaces is backed up first (*.pre-privacy-stack).
#
#  RUN IT (on the Debian drive, as root):
#    su -            (or: sudo -i)
#    bash privacy-stack-setup.sh
#
#  OPTIONAL: real obfs4 bridge lines. Tor works without them; bridges help
#  on networks that block Tor. Get lines free from bridges.torproject.org
#  or by emailing bridges@torproject.org from a Gmail or Riseup address.
#  Paste them, one per line, into a file named  obfs4-bridges.txt  next to
#  this script BEFORE running it, and they are wired in automatically.
#  You can also add them later — the script prints how at the end.
# ============================================================================

set -euo pipefail

say()  { printf '\n== %s ==\n' "$*"; }
note() { printf '   %s\n' "$*"; }
die()  { printf '\nSTOP: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight
say "Preflight"

[ "$(id -u)" -eq 0 ] || die "Run this as root:  su -   then   bash privacy-stack-setup.sh"

if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  [ "${ID:-}" = "debian" ] || die "This script targets Debian. Found: ${PRETTY_NAME:-unknown}"
  note "OS: $PRETTY_NAME"
else
  die "Cannot read /etc/os-release — is this Debian?"
fi

command -v apt-get >/dev/null || die "apt-get not found."

note "Checking network (Debian mirror)..."
if ! getent hosts deb.debian.org >/dev/null 2>&1; then
  die "No working network/DNS. Fix the connection first, then re-run."
fi
note "Network OK."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_FILE="$SCRIPT_DIR/obfs4-bridges.txt"

backup() { # backup <file>
  [ -f "$1" ] && cp -a "$1" "$1.pre-privacy-stack" && note "Backed up $1"
  return 0
}

# ---------------------------------------------------------------- packages
say "Installing packages from Debian's official repositories"
export DEBIAN_FRONTEND=noninteractive
apt-get update
# tor / obfs4proxy      — Tor daemon + obfs4 bridge transport
# proxychains4          — force apps through Tor
# macchanger            — manual MAC changes (boot spoofing uses NetworkManager)
# curl / ca-certificates— fetch Mullvad's official client over HTTPS
# overlayroot           — powers the amnesic boot entry (tmpfs overlay)
apt-get install -y tor obfs4proxy proxychains4 macchanger \
                   curl ca-certificates overlayroot
note "Packages installed."

# ---------------------------------------------------------------- tor + obfs4
say "Tor + obfs4 bridges"

backup /etc/tor/torrc
{
  echo "# Managed by privacy-stack-setup.sh"
  echo "SocksPort 9050"
  echo "ClientTransportPlugin obfs4 exec /usr/bin/obfs4proxy"
} > /etc/tor/torrc

if [ -s "$BRIDGE_FILE" ] && grep -q '^obfs4 ' "$BRIDGE_FILE"; then
  echo "UseBridges 1" >> /etc/tor/torrc
  while IFS= read -r line; do
    case "$line" in
      obfs4\ *) echo "Bridge $line" >> /etc/tor/torrc ;;
    esac
  done < "$BRIDGE_FILE"
  note "Bridges loaded from obfs4-bridges.txt and enabled."
  BRIDGES_SET=1
else
  note "No obfs4-bridges.txt found — Tor is configured with the obfs4"
  note "transport ready, bridges NOT enabled yet (Tor still works)."
  note "To add bridges later: get lines from bridges.torproject.org,"
  note "put them in $BRIDGE_FILE, and re-run this script."
  BRIDGES_SET=0
fi

systemctl enable tor >/dev/null 2>&1 || true
systemctl restart tor || note "Tor service will start on next boot."
note "Tor layer done. Verify after setup:  curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org"

# ---------------------------------------------------------------- proxychains
say "Proxychains (apps -> Tor)"

backup /etc/proxychains4.conf
cat > /etc/proxychains4.conf <<'EOF'
# Managed by privacy-stack-setup.sh — strict chain through Tor
strict_chain
proxy_dns
quiet_mode
tcp_read_time_out 15000
tcp_connect_time_out 8000
[ProxyList]
socks5  127.0.0.1 9050
EOF
note "Proxychains done. Use it like:  proxychains4 curl https://check.torproject.org"

# ---------------------------------------------------------------- MAC spoof
say "MAC spoofing at boot"

if [ -d /etc/NetworkManager ]; then
  mkdir -p /etc/NetworkManager/conf.d
  cat > /etc/NetworkManager/conf.d/00-mac-randomize.conf <<'EOF'
# Managed by privacy-stack-setup.sh — random MAC every connection/boot
[device]
wifi.scan-rand-mac-address=yes

[connection]
wifi.cloned-mac-address=random
ethernet.cloned-mac-address=random
EOF
  note "NetworkManager will randomize Wi-Fi and Ethernet MAC addresses."
  note "Manual one-off change:  sudo macchanger -r <interface>"
else
  note "NetworkManager not found — boot-time spoofing skipped."
  note "Manual change still available:  sudo macchanger -r <interface>"
fi

# ---------------------------------------------------------------- Mullvad VPN (optional)
say "Mullvad VPN (optional)"

printf 'Paste your Mullvad account number to activate the VPN now,\nor just press Enter to skip (VPN can be added later): '
read -r MULLVAD_NUMBER </dev/tty || MULLVAD_NUMBER=""

if [ -n "$MULLVAD_NUMBER" ]; then
  TMPD="$(mktemp -d)"
  note "Downloading Mullvad's official client..."
  if curl -fsSL -o "$TMPD/mullvad.deb" \
       "https://mullvad.net/en/download/app/deb/latest"; then
    apt-get install -y "$TMPD/mullvad.deb" || \
      note "Mullvad package install failed — download it from mullvad.net and install manually."
    if command -v mullvad >/dev/null; then
      mullvad account login "$MULLVAD_NUMBER" || \
        note "Login failed — check the number and run:  mullvad account login <number>"
      mullvad relay set location us >/dev/null 2>&1 || true
      note "VPN installed and account set. Connect with:  mullvad connect"
      note "Check anytime with:  mullvad status"
    fi
  else
    note "Download failed — VPN skipped. The other layers are unaffected."
  fi
  rm -rf "$TMPD"
else
  note "Skipped. Add it later: install the client from mullvad.net, then"
  note "  mullvad account login <number>   and   mullvad connect"
fi
unset MULLVAD_NUMBER

# ---------------------------------------------------------------- amnesic boot entry
say "Amnesic boot option (GRUB)"

GRUB_CFG=""
for c in /boot/grub/grub.cfg /boot/efi/EFI/debian/grub.cfg; do
  [ -f "$c" ] && GRUB_CFG="$c" && break
done

if [ -n "$GRUB_CFG" ] && command -v update-grub >/dev/null; then
  cp -a "$GRUB_CFG" "$GRUB_CFG.pre-privacy-stack"
  # Clone the first (default) menuentry, rename it, and append the
  # overlayroot tmpfs flag so the session lives in RAM only.
  awk '
    /^menuentry / && !done {
      capture=1
      line=$0
      sub(/menuentry '"'"'[^'"'"']*'"'"'/, "menuentry '"'"'Debian — AMNESIC (nothing is saved)'"'"'", line)
      print line; next
    }
    capture && /^}/ { print "}"; capture=0; done=1; next }
    capture {
      if ($1 == "linux") { $0 = $0 " overlayroot=tmpfs,recurse=0" }
      print
    }
  ' "$GRUB_CFG" > /etc/grub.d/41_amnesic_body 2>/dev/null || true

  if grep -q "AMNESIC" /etc/grub.d/41_amnesic_body 2>/dev/null; then
    { echo '#!/bin/sh'; echo 'cat << "EOF"'; cat /etc/grub.d/41_amnesic_body; echo 'EOF'; } \
      > /etc/grub.d/41_amnesic
    chmod +x /etc/grub.d/41_amnesic
    rm -f /etc/grub.d/41_amnesic_body
    update-grub
    note "Boot menu now has:  Debian — AMNESIC (nothing is saved)"
    note "Pick it at boot for a session that vanishes on power-off."
  else
    note "Could not clone your boot entry safely — amnesic entry skipped."
    note "Your existing boot setup was NOT changed."
    rm -f /etc/grub.d/41_amnesic_body
  fi
else
  note "GRUB not found in the usual places — amnesic entry skipped."
  note "Your existing boot setup was NOT changed."
fi

# ---------------------------------------------------------------- checklist
say "DONE — verify each layer (30 seconds each)"
cat <<'EOF'
   [ ] VPN:      mullvad status            -> "Connected" (if you added it)
   [ ] Tor:      curl --socks5-hostname 127.0.0.1:9050 https://check.torproject.org
                                             -> "Congratulations... using Tor"
   [ ] Bridges:  grep -c "^Bridge" /etc/tor/torrc   -> 1 or more (if added)
   [ ] Proxychains: proxychains4 curl https://check.torproject.org
   [ ] MAC:      reboot, then  ip link show  -> address differs from the
                 sticker on the machine / your router's old record
   [ ] Amnesic:  reboot, pick "Debian — AMNESIC", create a file on the
                 desktop, reboot normally -> the file is gone

   Remember: this stack reduces exposure. It does not make you invisible —
   accounts you log into still know it's you.
EOF
