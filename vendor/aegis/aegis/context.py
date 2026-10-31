"""System context gathering for the model prompt.

Collects a compact, non-sensitive snapshot of the machine so the local model
knows what OS, tools, and network state it is reasoning about. Deliberately
does NOT dump environment variables (they can contain secrets) — only a small
whitelist of safe, useful facts.

Cross-platform: Linux, macOS, and Windows.
"""

from __future__ import annotations

import os
import platform as _pyplatform
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List

from . import platform as aegis_platform

# Security tools we probe for so the model knows what is installed.
PROBE_TOOLS = [
    "nmap", "masscan", "nikto", "gobuster", "ffuf", "sqlmap", "wpscan",
    "hydra", "john", "hashcat", "aircrack-ng", "bettercap", "msfconsole",
    "msfvenom", "burpsuite", "zaproxy", "setoolkit", "mitmproxy", "wireshark",
    "tcpdump", "tshark", "searchsploit", "enum4linux", "smbclient", "ldapsearch",
    "gdb", "radare2", "ghidra", "binwalk", "foremost", "volatility",
    "docker", "git", "python3", "python", "go", "rustc", "cargo", "gcc",
    "node", "npm", "code", "pwsh",
]


def _run(cmd: List[str], timeout: float = 3.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (out.stdout or "").strip()
    except Exception:
        return ""


@dataclass
class SystemContext:
    facts: Dict[str, str] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    interfaces: List[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        lines = ["## Local system context"]
        for key, val in self.facts.items():
            lines.append(f"- {key}: {val}")
        if self.interfaces:
            lines.append(f"- network interfaces: {', '.join(self.interfaces)}")
        if self.tools:
            lines.append(f"- security/tooling available: {', '.join(self.tools)}")
        else:
            lines.append("- security/tooling available: (none detected)")
        return "\n".join(lines)


def gather(workspace: str = "") -> SystemContext:
    ctx = SystemContext()
    info = aegis_platform.detect()

    ctx.facts["os"] = _pretty_os()
    ctx.facts["kernel"] = f"{info.system} {info.release}"
    ctx.facts["arch"] = info.machine
    ctx.facts["hostname"] = socket.gethostname()
    ctx.facts["user"] = _current_user()
    ctx.facts["shell"] = info.shell
    ctx.facts["cwd"] = os.getcwd()
    if workspace:
        ctx.facts["workspace"] = workspace
    ctx.facts["python"] = info.python
    if info.package_managers:
        ctx.facts["package managers"] = ", ".join(info.package_managers)

    mem = _mem_summary(info)
    if mem:
        ctx.facts["memory"] = mem

    disk = _disk_summary()
    if disk:
        ctx.facts["home_disk"] = disk

    ctx.interfaces = _interfaces(info)
    ctx.tools = [t for t in PROBE_TOOLS if shutil.which(t)]
    return ctx


def _current_user() -> str:
    for var in ("USER", "LOGNAME", "USERNAME"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        return os.getlogin()
    except OSError:
        return "unknown"


def _pretty_os() -> str:
    system = _pyplatform.system()
    if system == "Linux":
        try:
            with open("/etc/os-release", encoding="utf-8") as fh:
                data = {}
                for line in fh:
                    if "=" in line:
                        k, v = line.rstrip().split("=", 1)
                        data[k] = v.strip('"')
            return data.get("PRETTY_NAME", _pyplatform.platform())
        except OSError:
            pass
    return _pyplatform.platform()


def _mem_summary(info: aegis_platform.PlatformInfo) -> str:
    # Linux
    if info.is_linux:
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                data = {}
                for line in fh:
                    key, _, rest = line.partition(":")
                    parts = rest.split()
                    if parts:
                        data[key] = int(parts[0])
            total = data.get("MemTotal", 0) // 1024
            avail = data.get("MemAvailable", data.get("MemTotal", 0)) // 1024
            return f"{avail} MiB available of {total} MiB"
        except (OSError, ValueError):
            return ""
    # macOS
    if info.is_macos:
        total = _run(["sysctl", "-n", "hw.memsize"])
        try:
            total_mb = int(total) // (1024 * 1024)
            return f"{total_mb} MiB total"
        except ValueError:
            return ""
    # Windows
    if info.is_windows:
        out = _run(["wmic", "OS", "get", "TotalVisibleMemorySize,FreePhysicalMemory", "/value"])
        vals = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.strip().split("=", 1)
                vals[k] = v
        try:
            total_mb = int(vals.get("TotalVisibleMemorySize", "0")) // 1024
            free_mb = int(vals.get("FreePhysicalMemory", "0")) // 1024
            return f"{free_mb} MiB available of {total_mb} MiB"
        except ValueError:
            return ""
    return ""


def _disk_summary() -> str:
    try:
        usage = shutil.disk_usage(os.path.expanduser("~"))
        return f"{usage.free // (1024**3)} GiB free of {usage.total // (1024**3)} GiB"
    except OSError:
        return ""


def _interfaces(info: aegis_platform.PlatformInfo) -> List[str]:
    if info.is_linux:
        try:
            return [n for n in os.listdir("/sys/class/net")]
        except OSError:
            return []
    if info.is_macos:
        out = _run(["networksetup", "-listallhardwareports"])
        names = []
        for line in out.splitlines():
            if line.startswith("Device:"):
                names.append(line.split(":", 1)[1].strip())
        return names
    if info.is_windows:
        out = _run(["wmic", "nic", "get", "NetConnectionID", "/value"])
        names = []
        for line in out.splitlines():
            if line.startswith("NetConnectionID=") and line.strip() != "NetConnectionID=":
                names.append(line.split("=", 1)[1].strip())
        return names
    return []
