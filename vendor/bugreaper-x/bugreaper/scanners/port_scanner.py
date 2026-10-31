from __future__ import annotations

import asyncio
import socket
from typing import Any

from bugreaper.core.models import Severity, Vulnerability

DANGEROUS_SERVICES = {
    21: ("FTP", "high"), 22: ("SSH", "info"), 23: ("Telnet", "critical"),
    25: ("SMTP", "medium"), 53: ("DNS", "info"), 80: ("HTTP", "info"),
    110: ("POP3", "medium"), 135: ("RPC", "high"), 139: ("NetBIOS", "high"),
    143: ("IMAP", "medium"), 443: ("HTTPS", "info"), 445: ("SMB", "high"),
    1433: ("MSSQL", "high"), 1521: ("Oracle", "high"), 2049: ("NFS", "high"),
    3306: ("MySQL", "high"), 3389: ("RDP", "critical"), 4444: ("Metasploit", "god-tier"),
    5432: ("PostgreSQL", "high"), 5900: ("VNC", "critical"), 6379: ("Redis", "critical"),
    8080: ("HTTP-Alt", "info"), 8443: ("HTTPS-Alt", "info"), 9200: ("Elasticsearch", "critical"),
    27017: ("MongoDB", "critical"),
}

COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445,
    993, 995, 1433, 1521, 2049, 3306, 3389, 4444, 5432, 5900,
    6379, 8080, 8443, 8888, 9200, 9300, 27017,
]


async def _scan_port(host: str, port: int, timeout: float = 3.0) -> tuple[int, bool, str]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        banner = ""
        try:
            data = await asyncio.wait_for(reader.read(1024), timeout=2.0)
            banner = data.decode("utf-8", errors="replace").strip()[:200]
        except Exception:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return port, True, banner
    except Exception:
        return port, False, ""


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []
    ports = config.get("ports", COMMON_PORTS)

    try:
        host = target.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        ip = socket.gethostbyname(host)
    except Exception:
        return vulns

    tasks = [_scan_port(ip, port) for port in ports]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    open_ports: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        port, is_open, banner = result
        if not is_open:
            continue
        open_ports.append({"port": port, "banner": banner})

        svc_name, svc_severity = DANGEROUS_SERVICES.get(port, ("Unknown", "info"))
        severity = Severity(svc_severity)

        desc = f"Port {port}/{svc_name} is open on {ip}"
        if banner:
            desc += f". Banner: {banner}"

        extra = ""
        if port in (3389, 5900, 4444):
            extra = " This service exposes the host to direct exploitation."
        elif port in (6379, 9200, 27017):
            extra = " This database service may be unauthenticated and world-accessible."
        elif port == 23:
            extra = " Telnet transmits credentials in plaintext."

        vuln = Vulnerability(
            title=f"Open Port: {port}/{svc_name}",
            description=desc + extra,
            severity=severity,
            url=f"tcp://{ip}:{port}",
            evidence=f"Banner: {banner}" if banner else None,
            remediation=(
                f"Restrict access to port {port} via firewall rules. "
                "If the service is unnecessary, disable it."
            ),
            scanner="port_scanner",
            tags=["network", "port-scan", svc_name.lower()],
        )
        vulns.append(vuln)

    return vulns
