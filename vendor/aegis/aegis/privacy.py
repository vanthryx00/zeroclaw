"""Privacy posture auditing, Tor status, and amnesic-mode controls.

This module is read-mostly: it inspects the live environment and reports
leaks. Actual hardening is emitted as a *plan* of shell commands which the
caller runs through the normal :class:`~aegis.executor.Executor`, so every
change stays classified, confirmed, and audited.

Threat model note: the checks here catch *configuration* leaks (a public
resolver, an active swap partition, an unrandomized MAC). They do not and
cannot prove anonymity. See docs/PRIVACY.md.
"""

from __future__ import annotations

import os
import socket
import time
from dataclasses import dataclass, field
from typing import List, Optional

# Public resolvers that leak your queries away from Tor.
PUBLIC_DNS = {
    "8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9",
    "208.67.222.222", "208.67.220.220", "64.6.64.6", "64.6.65.6",
    "77.88.8.8", "76.76.2.0",
}

# Common Tor listening ports.
TOR_PORTS = {
    "socks": 9050,       # Tor SOCKS proxy
    "trans": 9040,       # transparent proxy (Tails-style)
    "dns": 5353,         # Tor DNS
    "control": 9051,     # control port
    "browser_socks": 9150,  # Tor Browser bundled
}


@dataclass
class PrivacyFinding:
    key: str
    label: str
    status: str  # "ok" | "warn" | "fail" | "unknown"
    detail: str
    fix: str = ""

    @property
    def icon(self) -> str:
        return {"ok": "✔", "warn": "!", "fail": "✘", "unknown": "?"}.get(self.status, "?")


@dataclass
class PrivacyReport:
    findings: List[PrivacyFinding] = field(default_factory=list)

    @property
    def failures(self) -> int:
        return sum(1 for f in self.findings if f.status == "fail")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.status == "warn")

    @property
    def score(self) -> int:
        """0-100. Only counts checks that produced a definite verdict."""
        scored = [f for f in self.findings if f.status in ("ok", "warn", "fail")]
        if not scored:
            return 0
        weight = {"ok": 1.0, "warn": 0.5, "fail": 0.0}
        return round(100 * sum(weight[f.status] for f in scored) / len(scored))

    def to_text(self) -> str:
        lines = [f"Privacy score: {self.score}/100  "
                 f"({self.failures} fail, {self.warnings} warn)"]
        for f in self.findings:
            lines.append(f"  [{f.icon}] {f.label}: {f.detail}")
            if f.fix and f.status in ("warn", "fail"):
                lines.append(f"      fix: {f.fix}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Low-level probes (all read-only)
# --------------------------------------------------------------------------

def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_locally_administered(mac: str) -> bool:
    """A randomized MAC has the locally-administered bit set (2nd LSB of octet 1)."""
    try:
        first = int(mac.split(":")[0], 16)
    except (ValueError, IndexError):
        return False
    return bool(first & 0x02)


class PrivacyAuditor:
    def __init__(self, cfg):
        self.cfg = cfg

    # -- individual checks ---------------------------------------------
    def _check_amnesic(self) -> PrivacyFinding:
        mounts = _read("/proc/mounts")
        root_line = ""
        home_line = ""
        for line in mounts.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            if parts[1] == "/":
                root_line = line
            if parts[1] in ("/home", "/root"):
                home_line = line
        amnesic_fs = ("tmpfs", "overlay", "squashfs")
        root_ok = any(fs in root_line for fs in amnesic_fs)
        home_ok = (not home_line) or any(fs in home_line for fs in amnesic_fs)
        if root_ok and home_ok:
            return PrivacyFinding(
                "amnesic", "Amnesic root", "ok",
                "root and home are on RAM/overlay; nothing persists to disk",
            )
        if root_ok and not home_ok:
            return PrivacyFinding(
                "amnesic", "Amnesic root", "warn",
                "root is RAM-backed but /home appears to be on a real disk",
                "boot without the persistence partition, or set privacy.amnesic=true",
            )
        return PrivacyFinding(
            "amnesic", "Amnesic root", "fail",
            "running from a persistent install; changes will be written to disk",
            "use the live USB with persistence disabled for amnesic operation",
        )

    def _check_swap(self) -> PrivacyFinding:
        swaps = _read("/proc/swaps").splitlines()[1:]
        active = [s.split()[0] for s in swaps if s.strip()]
        if not active:
            return PrivacyFinding("swap", "Swap disabled", "ok",
                                  "no active swap — no plaintext leaks to disk")
        return PrivacyFinding(
            "swap", "Swap disabled", "fail",
            f"active swap on {', '.join(active)} — memory can leak to disk",
            "sudo swapoff -a",
        )

    def _check_dns(self) -> PrivacyFinding:
        resolv = _read("/etc/resolv.conf")
        servers = []
        for line in resolv.splitlines():
            line = line.strip()
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    servers.append(parts[1])
        if not servers:
            return PrivacyFinding("dns", "DNS leak", "unknown",
                                  "no nameservers found in /etc/resolv.conf")
        leaked = [s for s in servers if s in PUBLIC_DNS]
        local = [s for s in servers if s.startswith("127.")]
        if leaked:
            return PrivacyFinding(
                "dns", "DNS leak", "fail",
                f"public resolver(s) in use: {', '.join(leaked)} — queries leave Tor",
                "route DNS through Tor (privacy.dns_over_tor) and set "
                "nameserver 127.0.0.1",
            )
        if local:
            return PrivacyFinding("dns", "DNS leak", "ok",
                                  f"resolver is local ({', '.join(local)})")
        return PrivacyFinding("dns", "DNS leak", "warn",
                              f"non-public but non-local resolver: {', '.join(servers)}")

    def _check_ipv6(self) -> PrivacyFinding:
        val = _read("/proc/sys/net/ipv6/conf/all/disable_ipv6").strip()
        if val == "1":
            return PrivacyFinding("ipv6", "IPv6 disabled", "ok",
                                  "IPv6 off — one less leak path")
        return PrivacyFinding(
            "ipv6", "IPv6 disabled", "warn",
            "IPv6 is enabled; many Tor setups leak over IPv6",
            "sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1",
        )

    def _check_tor(self) -> PrivacyFinding:
        cfg = self.cfg.privacy
        socks = _port_open("127.0.0.1", cfg.tor_socks_port)
        trans = _port_open("127.0.0.1", cfg.tor_trans_port)
        browser = _port_open("127.0.0.1", TOR_PORTS["browser_socks"])
        running = socks or trans or browser
        if running:
            where = []
            if trans:
                where.append(f"transparent:{cfg.tor_trans_port}")
            if socks:
                where.append(f"socks:{cfg.tor_socks_port}")
            if browser:
                where.append("tor-browser:9150")
            return PrivacyFinding("tor", "Tor running", "ok",
                                  f"Tor detected ({', '.join(where)})")
        return PrivacyFinding(
            "tor", "Tor running", "fail",
            "no Tor process found on the usual ports",
            "sudo systemctl start tor  (or start the Whonix Gateway VM)",
        )

    def _check_mac(self) -> PrivacyFinding:
        base = "/sys/class/net"
        ifaces = []
        try:
            ifaces = [n for n in os.listdir(base) if n != "lo"]
        except OSError:
            return PrivacyFinding("mac", "MAC randomization", "unknown",
                                  "cannot read /sys/class/net")
        real = []
        random = []
        for name in ifaces:
            mac = _read(f"{base}/{name}/address").strip()
            if not mac or mac == "00:00:00:00:00:00":
                continue
            (random if _is_locally_administered(mac) else real).append(name)
        if real:
            return PrivacyFinding(
                "mac", "MAC randomization", "warn",
                f"real (vendor) MAC on: {', '.join(real)}",
                "run the MAC randomization service (privacy.randomize_mac)",
            )
        if random:
            return PrivacyFinding("mac", "MAC randomization", "ok",
                                  f"randomized MAC on: {', '.join(random)}")
        return PrivacyFinding("mac", "MAC randomization", "unknown",
                              "no usable interfaces found")

    def _check_hostname(self) -> PrivacyFinding:
        host = socket.gethostname()
        if host in ("amnesia", "localhost", "aegis", "aegisos"):
            return PrivacyFinding("hostname", "Hostname", "ok",
                                  f"generic hostname '{host}'")
        return PrivacyFinding(
            "hostname", "Hostname", "warn",
            f"hostname '{host}' may be identifying",
            "set a generic hostname (e.g. 'aegis') before connecting",
        )

    def _check_timezone(self) -> PrivacyFinding:
        tz = ""
        try:
            tz = time.tzname[0] or ""
        except Exception:
            pass
        if tz.upper() in ("UTC", "GMT") or tz == "":
            return PrivacyFinding("timezone", "UTC clock", "ok",
                                  "clock is UTC — no timezone fingerprint")
        return PrivacyFinding(
            "timezone", "UTC clock", "warn",
            f"timezone appears to be '{tz}'",
            "sudo timedatectl set-timezone UTC",
        )

    def _check_firewall(self) -> PrivacyFinding:
        ufw = _read("/etc/ufw/ufw.conf")
        if "ENABLED=yes" in ufw:
            return PrivacyFinding("firewall", "Firewall", "ok", "ufw is enabled")
        return PrivacyFinding(
            "firewall", "Firewall", "warn",
            "ufw is not enabled (or not installed)",
            "sudo ufw default deny incoming && sudo ufw enable",
        )

    def _check_proxychains(self) -> PrivacyFinding:
        conf = _read("/etc/proxychains4.conf") or _read("/etc/proxychains.conf")
        if not conf:
            return PrivacyFinding("proxychains", "proxychains", "unknown",
                                  "proxychains not installed")
        if "socks4 127.0.0.1 9050" in conf or "socks5 127.0.0.1 9050" in conf:
            return PrivacyFinding("proxychains", "proxychains", "ok",
                                  "configured to use Tor SOCKS")
        return PrivacyFinding(
            "proxychains", "proxychains", "warn",
            "proxychains present but not pointed at Tor",
            "set 'socks5 127.0.0.1 9050' in the [ProxyList] section",
        )

    # -- aggregate ------------------------------------------------------
    def audit(self) -> PrivacyReport:
        report = PrivacyReport()
        for check in (
            self._check_amnesic,
            self._check_swap,
            self._check_dns,
            self._check_ipv6,
            self._check_tor,
            self._check_mac,
            self._check_hostname,
            self._check_timezone,
            self._check_firewall,
            self._check_proxychains,
        ):
            try:
                report.findings.append(check())
            except Exception as exc:  # never let one check kill the audit
                report.findings.append(PrivacyFinding(
                    check.__name__, check.__name__, "unknown", f"check error: {exc}"))
        return report

    # -- hardening plan -------------------------------------------------
    def hardening_plan(self) -> List[str]:
        """Return the shell commands that would fix the current findings."""
        report = self.audit()
        plan: List[str] = []
        for f in report.findings:
            if f.status in ("warn", "fail") and f.fix:
                plan.append(f.fix)
        return plan


class TorController:
    """Reports Tor state and generates (but does not silently apply) proxy rules."""

    def __init__(self, cfg):
        self.cfg = cfg

    def status(self) -> str:
        p = self.cfg.privacy
        lines = []
        for label, port in (
            ("socks", p.tor_socks_port),
            ("transparent", p.tor_trans_port),
            ("dns", p.tor_dns_port),
            ("control", TOR_PORTS["control"]),
        ):
            state = "open" if _port_open("127.0.0.1", port) else "closed"
            lines.append(f"  127.0.0.1:{port:<5} {label:<12} {state}")
        lines.append(f"  force_tor={p.force_tor}  proxy={p.proxy or '(none)'}")
        return "\n".join(lines)

    def transparent_rules(self) -> List[str]:
        """iptables rules that route all TCP + DNS through Tor (Tails-style).

        These are emitted for review; they are applied only through the
        Executor, which classifies them RISKY and asks first.
        """
        p = self.cfg.privacy
        return [
            "# Flush old NAT/filter rules",
            "iptables -t nat -F",
            "iptables -F",
            "# Allow loopback",
            "iptables -t nat -A OUTPUT -o lo -j RETURN",
            "# Do not re-tor the Tor process itself",
            "iptables -t nat -A OUTPUT -m owner --uid-owner debian-tor -j RETURN",
            "iptables -t nat -A OUTPUT -m owner --uid-owner tor -j RETURN",
            "# Redirect all TCP to the Tor transparent port",
            f"iptables -t nat -A OUTPUT -p tcp --syn -j REDIRECT --to-ports {p.tor_trans_port}",
            "# Redirect DNS to Tor's DNSPort",
            f"iptables -t nat -A OUTPUT -p udp --dport 53 -j REDIRECT --to-ports {p.tor_dns_port}",
            "# Drop everything else that is not loopback",
            "iptables -A OUTPUT ! -o lo ! -d 127.0.0.1 -j DROP",
        ]

    # -- control port ---------------------------------------------------
    def _control(self, command: str) -> str:
        """Send a command to the Tor control port. Best-effort, never raises."""
        port = getattr(self.cfg.privacy, "tor_control_port", TOR_PORTS["control"])
        password = getattr(self.cfg.privacy, "tor_control_password", "") or ""
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=3.0) as sock:
                sock.settimeout(3.0)
                auth = (f'AUTHENTICATE "{password}"\r\n' if password
                        else "AUTHENTICATE\r\n")
                sock.sendall(auth.encode())
                resp = sock.recv(512).decode(errors="replace")
                if "250" not in resp:
                    return f"auth failed: {resp.strip()[:120]}"
                sock.sendall(f"{command}\r\n".encode())
                return sock.recv(512).decode(errors="replace").strip()
        except OSError as exc:
            return f"control port unavailable: {exc}"

    def new_identity(self) -> str:
        """Ask Tor for fresh circuits (SIGNAL NEWNYM)."""
        if not _port_open("127.0.0.1", getattr(self.cfg.privacy, "tor_control_port", 9051)):
            return "Tor control port is closed — is Tor running with ControlPort set?"
        resp = self._control("SIGNAL NEWNYM")
        if resp.startswith("250"):
            return "New Tor identity requested — new circuits will be used shortly."
        return f"Could not signal Tor: {resp}"

    def circuit_status(self) -> str:
        return self._control("GETINFO circuit-status")


# ---------------------------------------------------------------------------
# DNS leak test
# ---------------------------------------------------------------------------

@dataclass
class LeakTestResult:
    resolver: str = ""
    loopback_resolver: bool = False
    public_resolvers: List[str] = field(default_factory=list)
    tor_dns_open: bool = False
    live_probe: str = "skipped"  # blocked | answered | skipped | error
    verdict: str = "unknown"
    detail: str = ""

    def to_text(self) -> str:
        lines = [
            f"resolver(s): {self.resolver or '(none)'}",
            f"loopback resolver: {self.loopback_resolver}",
            f"public resolvers in use: {', '.join(self.public_resolvers) or '(none)'}",
            f"Tor DNSPort open: {self.tor_dns_open}",
            f"live probe to a public resolver: {self.live_probe}",
            f"verdict: {self.verdict}",
        ]
        if self.detail:
            lines.append(self.detail)
        return "\n".join(lines)


def _parse_nameservers(text: str) -> List[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("nameserver"):
            parts = line.split()
            if len(parts) >= 2:
                out.append(parts[1])
    return out


def dns_leak_test(cfg, live: bool = False) -> LeakTestResult:
    """Analyse DNS configuration and, optionally, probe for a real leak.

    The live probe sends a single UDP query to a public resolver with a short
    timeout. If it answers, DNS traffic can bypass Tor — a genuine leak.
    """
    result = LeakTestResult()
    resolvers = _parse_nameservers(_read("/etc/resolv.conf"))
    result.resolver = ", ".join(resolvers)
    result.loopback_resolver = any(r.startswith("127.") or r in ("::1", "localhost")
                                   for r in resolvers)
    result.public_resolvers = [r for r in resolvers if r in PUBLIC_DNS]
    result.tor_dns_open = _port_open("127.0.0.1", getattr(cfg.privacy, "tor_dns_port", 5353))

    if live:
        result.live_probe = _probe_public_dns("8.8.8.8")

    if result.public_resolvers:
        result.verdict = "LEAK"
        result.detail = ("Your system is configured to use a public resolver directly. "
                         "Route DNS through Tor (127.0.0.1) or you leak every lookup.")
    elif result.live_probe == "answered":
        result.verdict = "LEAK"
        result.detail = ("A public resolver answered a direct query, so DNS can bypass "
                         "Tor even though resolv.conf looks clean. Block port 53 outbound.")
    elif result.loopback_resolver and result.tor_dns_open:
        result.verdict = "OK"
        result.detail = "DNS points at the local Tor resolver and the DNSPort is open."
    elif result.loopback_resolver:
        result.verdict = "LIKELY_OK"
        result.detail = "DNS points at loopback, but the Tor DNSPort is closed."
    else:
        result.verdict = "UNKNOWN"
        result.detail = "No nameserver found in /etc/resolv.conf."
    return result


def _probe_public_dns(server: str, timeout: float = 2.0) -> str:
    """Send one A-record query for example.com to a resolver; report the outcome."""
    try:
        query = _build_dns_query("example.com")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(query, (server, 53))
            data, _ = sock.recvfrom(512)
        return "answered" if data else "error"
    except socket.timeout:
        return "blocked"
    except OSError:
        return "blocked"


def _build_dns_query(domain: str) -> bytes:
    import struct
    tid = 0x1A2B
    header = struct.pack(">HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    q = b""
    for label in domain.split("."):
        q += bytes([len(label)]) + label.encode()
    q += b"\x00" + struct.pack(">HH", 1, 1)
    return header + q


# ---------------------------------------------------------------------------
# Panic button
# ---------------------------------------------------------------------------

class PanicController:
    """Emergency actions for physical-safety situations.

    Generates an ordered plan; the caller runs it through the Executor so every
    step is classified and audited. Intended for when you need the machine to
    stop and its memory gone *now*.
    """

    def __init__(self, cfg):
        self.cfg = cfg

    def interfaces(self) -> List[str]:
        try:
            return sorted(n for n in os.listdir("/sys/class/net") if n != "lo")
        except OSError:
            return []

    def plan(self) -> List[str]:
        action = getattr(self.cfg.privacy, "panic_action", "poweroff")
        cmds = ["# 1. cut the network immediately"]
        for iface in self.interfaces():
            cmds.append(f"ip link set {iface} down")
        cmds += [
            "# 2. drop swap so nothing can be recovered from disk",
            "swapoff -a",
            "# 3. flush caches to reduce residual data",
            "sync",
        ]
        cmds += [
            "# 4. overwrite RAM (best effort; power loss skips this)",
            "sdmem -fll",
        ]
        cmds += {
            "poweroff": ["# 5. power off now", "systemctl poweroff -f"],
            "halt": ["# 5. halt now", "systemctl halt -f"],
            "reboot": ["# 5. reboot now", "systemctl reboot -f"],
            "network": ["# 5. network-only panic (stay up, stay dark)",
                        "nmcli networking off"],
        }.get(action, ["systemctl poweroff -f"])
        return cmds

    def to_text(self) -> str:
        return "\n".join(self.plan())
