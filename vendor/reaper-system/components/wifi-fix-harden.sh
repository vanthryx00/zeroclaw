#!/usr/bin/env bash
# wifi-fix-harden.sh v1.0.0 — diagnose, repair, and harden Wi-Fi on Debian.
#
# Built for the PROJECT-STINGRAY Debian drive (privacy box). Complements
# privacy-stack-setup.sh; where they overlap (MAC randomization), this
# script configures it at the NetworkManager layer, which is the layer
# that actually manages connections.
#
# What it does, in order:
#   1. DIAGNOSE  — interface, rfkill, driver/firmware, NetworkManager,
#                  signal, latency. Read-only in --check mode.
#   2. REPAIR    — unblock rfkill, install missing tools/firmware,
#                  bring the interface up, restart NetworkManager,
#                  disable Wi-Fi power saving (a top cause of drops
#                  and multi-second latency spikes), set regulatory
#                  domain.
#   3. HARDEN    — per-connection MAC randomization + randomized scan
#                  MACs, WPS disabled on every saved Wi-Fi connection,
#                  NetworkManager connectivity-check (phone-home)
#                  disabled, audit of saved networks for open/WEP.
#   4. VERIFY    — link status, gateway + internet pings, latency
#                  summary, PASS/WARN report.
#
# Usage:
#   sudo bash wifi-fix-harden.sh           # diagnose + fix + harden
#   sudo bash wifi-fix-harden.sh --check   # diagnose only, change nothing
#
# Every file it changes is first copied to <file>.pre-wifi-fix.
# Restore: copy the .pre-wifi-fix file back and restart NetworkManager.
# No total-anonymity promises — this fixes Wi-Fi and closes the usual
# tracking holes (stable MAC, WPS, phone-home). It is not Tor.
set -uo pipefail

# ---------------------------------------------------------------------------
# Configuration (edit here, not below)
# ---------------------------------------------------------------------------
REGDOMAIN="CA"                    # regulatory domain (Alberta)
MAC_RANDOMIZATION=1               # 1 = random MAC per connection + scan
DISABLE_POWERSAVE=1               # 1 = Wi-Fi power saving off (stability)
DISABLE_CONNECTIVITY_CHECK=1      # 1 = no NM phone-home captive checks
BACKUP_SUFFIX=".pre-wifi-fix"
NM_CONF="/etc/NetworkManager/conf.d/10-wifi-hardening.conf"

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
say()  { printf '%s\n' "$*"; }
ok()   { printf '  [ ok ] %s\n' "$*"; }
fix()  { printf '  [fix ] %s\n' "$*"; }
warn() { printf '  [warn] %s\n' "$*"; }
die()  { printf '  [FAIL] %s\n' "$*" >&2; exit 1; }

backup() {
    # backup <file> — copy once, before first modification.
    local f="$1"
    if [ -f "$f" ] && [ ! -f "$f$BACKUP_SUFFIX" ]; then
        cp -a "$f" "$f$BACKUP_SUFFIX" && ok "backup: $f$BACKUP_SUFFIX"
    fi
}

changed=0
note_change() { changed=1; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    if [ "$CHECK_ONLY" -eq 1 ]; then
        warn "not root: diagnostics will be partial (run with sudo for full detail)"
    else
        die "run as root: sudo bash wifi-fix-harden.sh"
    fi
fi
grep -qi debian /etc/os-release 2>/dev/null || warn "not Debian per /etc/os-release — proceeding anyway"

say "== wifi-fix-harden v1.0.0 =="
[ "$CHECK_ONLY" -eq 1 ] && say "mode: CHECK ONLY (no changes)"

# ---------------------------------------------------------------------------
# 1. Diagnose
# ---------------------------------------------------------------------------
say "-- diagnose"

IFACE=""
if command -v iw >/dev/null 2>&1; then
    IFACE="$(iw dev 2>/dev/null | awk '$1=="Interface"{print $2; exit}')"
fi
if [ -z "$IFACE" ]; then
    for d in /sys/class/net/*; do
        [ -d "$d/wireless" ] && IFACE="$(basename "$d")" && break
    done
fi
[ -n "$IFACE" ] && ok "wireless interface: $IFACE" || warn "no wireless interface found"

if command -v rfkill >/dev/null 2>&1; then
    if rfkill list wifi 2>/dev/null | grep -q "Soft blocked: yes"; then
        warn "rfkill: Wi-Fi is SOFT BLOCKED"
        RFKILL_BLOCKED=1
    elif rfkill list wifi 2>/dev/null | grep -q "Hard blocked: yes"; then
        warn "rfkill: Wi-Fi is HARD BLOCKED (hardware switch / Fn key / BIOS)"
        RFKILL_BLOCKED=2
    else
        ok "rfkill: not blocked"
        RFKILL_BLOCKED=0
    fi
else
    RFKILL_BLOCKED=0
fi

FW_MISSING=0
if dmesg 2>/dev/null | grep -qiE "firmware.*(failed|missing|not found)"; then
    warn "dmesg shows firmware load failures:"
    dmesg 2>/dev/null | grep -iE "firmware.*(failed|missing|not found)" | tail -3 | sed 's/^/         /'
    FW_MISSING=1
else
    ok "no firmware load failures in dmesg"
fi

NM_ACTIVE=0
if systemctl is-active --quiet NetworkManager 2>/dev/null; then
    NM_ACTIVE=1; ok "NetworkManager: active"
elif command -v nmcli >/dev/null 2>&1; then
    warn "NetworkManager installed but not active"
else
    warn "NetworkManager not found — hardening that needs it will be skipped"
fi

if [ -n "$IFACE" ] && command -v iw >/dev/null 2>&1; then
    LINK="$(iw dev "$IFACE" link 2>/dev/null)"
    if printf '%s' "$LINK" | grep -q "Connected to"; then
        SIG="$(printf '%s' "$LINK" | grep -oE 'signal: -[0-9]+' | grep -oE '[0-9]+' || true)"
        ok "link: connected, signal -${SIG:-?} dBm"
    else
        warn "link: not connected"
    fi
    PS="$(iw dev "$IFACE" get power_save 2>/dev/null | grep -oE 'on|off' || true)"
    [ -n "$PS" ] && ok "power_save: $PS"
fi

[ "$CHECK_ONLY" -eq 1 ] && { say "== check complete (no changes made)"; exit 0; }

# ---------------------------------------------------------------------------
# 2. Repair
# ---------------------------------------------------------------------------
say "-- repair"

# Tools + firmware (only what's missing; non-free-firmware on bookworm+).
PKGS=""
command -v iw >/dev/null 2>&1 || PKGS="$PKGS iw"
command -v rfkill >/dev/null 2>&1 || PKGS="$PKGS rfkill"
if ! dpkg -s wireless-regdb >/dev/null 2>&1; then PKGS="$PKGS wireless-regdb"; fi
if [ "$FW_MISSING" -eq 1 ]; then
    for p in firmware-iwlwifi firmware-atheros firmware-realtek firmware-ralink firmware-brcm80211 firmware-misc-nonfree; do
        dpkg -s "$p" >/dev/null 2>&1 || PKGS="$PKGS $p"
    done
fi
if [ -n "$PKGS" ]; then
    if grep -rqsE "non-free-firmware|non-free" /etc/apt/sources.list /etc/apt/sources.list.d/ 2>/dev/null; then
        fix "installing:$PKGS"
        apt-get update -qq && apt-get install -y $PKGS && note_change \
            || warn "apt install failed — check network/sources, then re-run"
    else
        warn "apt sources lack non-free firmware components; add 'non-free-firmware' (bookworm+) to sources.list, apt update, re-run. Wanted:$PKGS"
    fi
fi

# rfkill
if [ "${RFKILL_BLOCKED:-0}" -eq 1 ]; then
    rfkill unblock wifi && { fix "rfkill soft block removed"; note_change; }
elif [ "${RFKILL_BLOCKED:-0}" -eq 2 ]; then
    warn "hard block cannot be fixed in software — check the laptop's Wi-Fi switch / Fn key / BIOS wireless toggle"
fi

# Regulatory domain (legal TX power + correct channels for Canada).
if command -v iw >/dev/null 2>&1; then
    CUR_REG="$(iw reg get 2>/dev/null | grep -oE 'country [A-Z]{2}' | head -1 | cut -d' ' -f2 || true)"
    if [ "$CUR_REG" != "$REGDOMAIN" ]; then
        iw reg set "$REGDOMAIN" && { fix "regulatory domain: ${CUR_REG:-unset} -> $REGDOMAIN"; note_change; }
    else
        ok "regulatory domain: $REGDOMAIN"
    fi
fi

# Interface up + NetworkManager restart (picks up new firmware/conf).
if [ -n "$IFACE" ]; then
    ip link set "$IFACE" up 2>/dev/null || true
fi
if [ "$NM_ACTIVE" -eq 1 ] || command -v nmcli >/dev/null 2>&1; then
    systemctl restart NetworkManager 2>/dev/null && fix "NetworkManager restarted"
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        nmcli -t -f RUNNING general status >/dev/null 2>&1 && break
        sleep 1
    done
fi

# Power saving off — immediate + persistent. A powersaving radio is the
# classic cause of 'connected but 5-second pings' and random drops.
if [ "$DISABLE_POWERSAVE" -eq 1 ] && [ -n "$IFACE" ] && command -v iw >/dev/null 2>&1; then
    iw dev "$IFACE" set power_save off 2>/dev/null && fix "power_save off (this boot)"
fi

# ---------------------------------------------------------------------------
# 3. Harden (NetworkManager drop-in + per-connection settings)
# ---------------------------------------------------------------------------
say "-- harden"

if command -v nmcli >/dev/null 2>&1; then
    mkdir -p "$(dirname "$NM_CONF")"
    backup "$NM_CONF"
    {
        echo "# Written by wifi-fix-harden.sh — MAC randomization + no phone-home."
        echo "[device]"
        if [ "$MAC_RANDOMIZATION" -eq 1 ]; then
            echo "wifi.scan-rand-mac-address=yes"
        fi
        echo ""
        echo "[connection]"
        if [ "$MAC_RANDOMIZATION" -eq 1 ]; then
            echo "wifi.cloned-mac-address=random"
            echo "ethernet.cloned-mac-address=random"
        fi
        if [ "$DISABLE_POWERSAVE" -eq 1 ]; then
            echo "wifi.powersave=2"
        fi
        if [ "$DISABLE_CONNECTIVITY_CHECK" -eq 1 ]; then
            echo ""
            echo "[connectivity]"
            echo "uri="
            echo "interval=0"
        fi
    } > "$NM_CONF"
    fix "wrote $NM_CONF (MAC randomization=$MAC_RANDOMIZATION, powersave off, connectivity check off)"
    note_change

    # WPS off on every saved Wi-Fi connection (WPS PIN is brute-forceable).
    # Audit: flag open / WEP networks — reported, never deleted silently.
    nmcli -t -f NAME,TYPE connection show 2>/dev/null | while IFS=: read -r name type; do
        [ "$type" = "802-11-wireless" ] || continue
        nmcli connection modify "$name" 802-11-wireless-security.wps-method disabled 2>/dev/null \
            && fix "WPS disabled: $name"
        SEC="$(nmcli -t -f 802-11-wireless-security.key-mgmt connection show "$name" 2>/dev/null | cut -d: -f2)"
        case "$SEC" in
            ""|none|wep*) warn "WEAK/OPEN saved network: '$name' (key-mgmt: ${SEC:-none}) — delete it if you don't use it: nmcli connection delete \"$name\"" ;;
        esac
    done

    systemctl restart NetworkManager 2>/dev/null && fix "NetworkManager restarted to apply hardening"
    ok "hardening applied — reconnect to your network so it picks up a randomized MAC"
else
    warn "no nmcli — skipped NM hardening. Manual equivalents: wpa_supplicant ctrl_interface + 'mac_addr=1' / scan_ssid discipline; powersave via iw."
fi

# ---------------------------------------------------------------------------
# 4. Verify
# ---------------------------------------------------------------------------
say "-- verify"
VERDICT=0
if [ -n "$IFACE" ] && command -v iw >/dev/null 2>&1; then
    sleep 3
    LINK="$(iw dev "$IFACE" link 2>/dev/null)"
    if printf '%s' "$LINK" | grep -q "Connected to"; then
        SIG="$(printf '%s' "$LINK" | grep -oE 'signal: -[0-9]+' | grep -oE '[0-9]+' || true)"
        RATE="$(printf '%s' "$LINK" | grep -oE 'tx bitrate: [0-9.]+ MBit/s' | head -1 || true)"
        ok "link up — signal -${SIG:-?} dBm, ${RATE:-rate unknown}"
    else
        warn "interface not connected yet — connect once (it will rejoin saved networks automatically), then re-run with --check"
        VERDICT=1
    fi
    GW="$(ip route show dev "$IFACE" 2>/dev/null | awk '/default/{print $3; exit}')"
    if [ -n "$GW" ]; then
        LAT="$(ping -c 3 -W 2 "$GW" 2>/dev/null | awk -F/ '/rtt|round-trip/{print $5}')"
        [ -n "$LAT" ] && ok "gateway $GW avg latency: ${LAT} ms" || warn "gateway $GW did not answer ping"
    fi
    if ping -c 2 -W 3 1.1.1.1 >/dev/null 2>&1; then
        ok "internet reachable (1.1.1.1)"
    else
        warn "internet ping failed — if the gateway answered, suspect DNS or upstream"
        VERDICT=1
    fi
    MACNOW="$(cat /sys/class/net/"$IFACE"/address 2>/dev/null || true)"
    [ -n "$MACNOW" ] && ok "current MAC: $MACNOW (compare across reconnects — it should change with randomization on)"
fi

say "== done =="
[ "$changed" -eq 1 ] && say "changes were made (backups carry the suffix $BACKUP_SUFFIX)"
[ "$VERDICT" -eq 0 ] && say "RESULT: PASS — Wi-Fi repaired and hardened" || say "RESULT: WARN — see [warn] lines above"
exit "$VERDICT"
