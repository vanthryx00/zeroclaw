"""Hardware and system diagnostics for rescue and triage.

Every check is read-only and degrades gracefully when a tool is missing, so
this runs on a bare live USB as well as a full install. Results feed the rescue
plan and the report builder.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

SEVERITIES = ["info", "warn", "critical"]


@dataclass
class DiagResult:
    key: str
    label: str
    severity: str = "info"
    detail: str = ""
    raw: str = ""

    def one_line(self) -> str:
        icon = {"info": "i", "warn": "!", "critical": "X"}.get(self.severity, "?")
        return f"[{icon}] {self.label}: {self.detail}"


def _run(cmd: List[str], timeout: float = 8.0) -> Optional[str]:
    if not shutil.which(cmd[0]):
        return None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.stdout
    except (subprocess.SubprocessError, OSError):
        return None


def _meminfo() -> dict:
    out = {}
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                k, _, rest = line.partition(":")
                out[k.strip()] = rest.strip()
    except OSError:
        pass
    return out


def _kb_to_mb(value: str) -> int:
    try:
        return int(value.split()[0]) // 1024
    except (ValueError, IndexError):
        return 0


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------

def check_memory() -> DiagResult:
    mi = _meminfo()
    total = _kb_to_mb(mi.get("MemTotal", "0 kB"))
    avail = _kb_to_mb(mi.get("MemAvailable", "0 kB"))
    if not total:
        return DiagResult("memory", "Memory", "info", "not available on this platform")
    used_pct = int(100 * (total - avail) / total) if total else 0
    sev = "warn" if used_pct >= 90 else "info"
    return DiagResult("memory", "Memory", sev,
                      f"{total} MiB total, {avail} MiB available ({used_pct}% used)")


def check_swap() -> DiagResult:
    try:
        with open("/proc/swaps") as fh:
            lines = [l for l in fh.read().splitlines() if l.strip()][1:]
    except OSError:
        return DiagResult("swap", "Swap", "info", "not available on this platform")
    if not lines:
        return DiagResult("swap", "Swap", "info", "no swap active")
    total_kb = 0
    for line in lines:
        parts = line.split()
        if len(parts) >= 3:
            try:
                total_kb += int(parts[2])
            except ValueError:
                pass
    return DiagResult("swap", "Swap", "info", f"{total_kb // 1024} MiB active")


def check_disk(path: str = "/") -> DiagResult:
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return DiagResult("disk", "Disk", "warn", f"cannot stat {path}: {exc}")
    free_pct = int(100 * usage.free / usage.total) if usage.total else 0
    free_gb = usage.free / (1024 ** 3)
    sev = "critical" if free_pct < 3 else ("warn" if free_pct < 10 else "info")
    return DiagResult("disk", "Disk", sev,
                      f"{free_gb:.1f} GiB free of {usage.total / (1024 ** 3):.1f} GiB "
                      f"({free_pct}% free)")


def check_inodes(path: str = "/") -> DiagResult:
    out = _run(["df", "-i", path])
    if not out:
        return DiagResult("inodes", "Inodes", "info", "df not available")
    lines = out.strip().splitlines()
    if len(lines) < 2:
        return DiagResult("inodes", "Inodes", "info", "no data")
    parts = lines[1].split()
    if len(parts) < 5:
        return DiagResult("inodes", "Inodes", "info", "unexpected df output")
    iused_pct = parts[4].rstrip("%")
    try:
        pct = int(iused_pct)
    except ValueError:
        return DiagResult("inodes", "Inodes", "info", f"used {iused_pct}")
    sev = "critical" if pct >= 95 else ("warn" if pct >= 85 else "info")
    return DiagResult("inodes", "Inodes", sev, f"{pct}% of inodes used")


def check_readonly_fs() -> DiagResult:
    out = _run(["mount"])
    if out is None:
        return DiagResult("readonly", "Filesystem", "info", "mount not available")
    ro = []
    for line in out.splitlines():
        if " ro," in line or line.endswith(" ro") or " ro " in line:
            dev = line.split()[0]
            mnt = line.split()[-1] if len(line.split()) >= 3 else ""
            if mnt in ("/", "/home") or dev.startswith("/dev/"):
                ro.append(mnt or dev)
    if ro:
        return DiagResult("readonly", "Filesystem", "critical",
                          f"read-only mounts: {', '.join(ro)} (possible fs error)")
    return DiagResult("readonly", "Filesystem", "info", "no unexpected read-only mounts")


def check_failed_units() -> DiagResult:
    out = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    if out is None:
        return DiagResult("units", "Systemd", "info", "systemctl not available")
    failed = [l.split()[0] for l in out.strip().splitlines() if l.strip()]
    if failed:
        return DiagResult("units", "Systemd", "warn",
                          f"{len(failed)} failed unit(s): {', '.join(failed[:5])}")
    return DiagResult("units", "Systemd", "info", "no failed units")


def check_kernel_errors() -> DiagResult:
    out = _run(["dmesg", "--level=err,crit,alert,emerg"])
    if out is None:
        return DiagResult("dmesg", "Kernel", "info", "dmesg not readable (needs root)")
    lines = [l for l in out.strip().splitlines() if l.strip()]
    if lines:
        return DiagResult("dmesg", "Kernel", "warn",
                          f"{len(lines)} kernel error line(s); latest: {lines[-1][:120]}",
                          raw="\n".join(lines[-20:]))
    return DiagResult("dmesg", "Kernel", "info", "no kernel errors")


def check_smart() -> DiagResult:
    if not shutil.which("smartctl"):
        return DiagResult("smart", "SMART", "info", "smartctl not installed")
    out = _run(["lsblk", "-ndo", "NAME,TYPE"])
    if not out:
        return DiagResult("smart", "SMART", "info", "no block devices found")
    bad = []
    checked = 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[1] != "disk":
            continue
        dev = f"/dev/{parts[0]}"
        health = _run(["smartctl", "-H", dev])
        if health is None:
            continue
        checked += 1
        if "FAILED" in health or "PASSED" not in health:
            bad.append(dev)
    if not checked:
        return DiagResult("smart", "SMART", "info", "no devices reported SMART health")
    if bad:
        return DiagResult("smart", "SMART", "critical",
                          f"SMART health FAILED on {', '.join(bad)}")
    return DiagResult("smart", "SMART", "info", f"all {checked} disk(s) report healthy")


def check_temperatures() -> DiagResult:
    out = _run(["sensors", "-A"])
    if out is None:
        return DiagResult("temps", "Temperature", "info", "lm-sensors not installed")
    temps = []
    for m in re.finditer(r"([+\-]?\d+\.\d+)°C", out):
        try:
            temps.append(float(m.group(1)))
        except ValueError:
            pass
    if not temps:
        return DiagResult("temps", "Temperature", "info", "no sensors reported")
    hot = max(temps)
    sev = "critical" if hot >= 90 else ("warn" if hot >= 80 else "info")
    return DiagResult("temps", "Temperature", sev, f"hottest sensor {hot:.1f} °C")


def check_uptime_load() -> DiagResult:
    try:
        with open("/proc/loadavg") as fh:
            load = fh.read().split()[:3]
        with open("/proc/uptime") as fh:
            up_s = float(fh.read().split()[0])
    except (OSError, ValueError, IndexError):
        return DiagResult("load", "Load", "info", "not available on this platform")
    cpus = os.cpu_count() or 1
    one = float(load[0])
    sev = "warn" if one > cpus * 2 else "info"
    hours = up_s / 3600
    return DiagResult("load", "Load", sev,
                      f"load {one:.2f} on {cpus} CPU(s), up {hours:.1f}h")


CHECKS = [
    check_memory, check_swap, check_disk, check_inodes, check_readonly_fs,
    check_failed_units, check_kernel_errors, check_smart, check_temperatures,
    check_uptime_load,
]


def run_all() -> List[DiagResult]:
    results = []
    for check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # never let one probe kill the report
            results.append(DiagResult(check.__name__, check.__name__, "info",
                                      f"check failed: {exc}"))
    return results


def worst(results: List[DiagResult]) -> str:
    order = {"info": 0, "warn": 1, "critical": 2}
    return max((r.severity for r in results), key=lambda s: order.get(s, 0),
               default="info")
