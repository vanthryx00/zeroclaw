from __future__ import annotations

import asyncio
import socket
from typing import Any
from urllib.parse import urlparse

from bugreaper.core.models import Severity, Vulnerability

SUBDOMAIN_WORDLIST = [
    "www", "mail", "ftp", "localhost", "webmail", "smtp", "pop", "ns1", "webdisk",
    "ns2", "cpanel", "whm", "autodiscover", "autoconfig", "m", "imap", "test",
    "ns", "blog", "pop3", "dev", "www2", "admin", "forum", "news", "vpn",
    "ns3", "mail2", "new", "mysql", "old", "lists", "support", "mobile",
    "mx", "static", "docs", "beta", "wiki", "media", "email", "images",
    "img", "www3", "info", "mail3", "pop2", "video", "cdn", "proxy",
    "api", "api2", "staging", "stage", "demo", "portal", "app", "apps",
    "uat", "qa", "prod", "production", "internal", "intranet", "private",
    "secure", "login", "remote", "shop", "store", "db", "database",
    "git", "gitlab", "github", "jenkins", "jira", "confluence", "sonar",
    "kibana", "grafana", "prometheus", "vault", "consul", "k8s", "kubernetes",
    "docker", "registry", "harbor", "nexus", "artifactory", "s3", "storage",
    "backup", "backups", "dev2", "test2", "uat2", "alpha", "preview",
    "status", "monitor", "metrics", "logs", "sentry", "analytics",
    "auth", "sso", "oauth", "idp", "ldap", "ad", "dc",
    "vpn2", "remote2", "rdp", "ssh", "bastion", "jump",
    "erp", "crm", "hr", "finance", "accounting", "payroll",
]


async def _resolve_subdomain(subdomain: str, domain: str) -> tuple[str, str | None]:
    fqdn = f"{subdomain}.{domain}"
    try:
        ip = await asyncio.get_event_loop().run_in_executor(
            None, socket.gethostbyname, fqdn
        )
        return fqdn, ip
    except Exception:
        return fqdn, None


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []
    parsed = urlparse(target)
    host = parsed.hostname or target.split("/")[0]

    parts = host.split(".")
    if len(parts) < 2:
        return vulns
    domain = ".".join(parts[-2:])

    tasks = [_resolve_subdomain(sub, domain) for sub in SUBDOMAIN_WORDLIST]
    chunk_size = 50
    discovered: list[tuple[str, str]] = []

    for i in range(0, len(tasks), chunk_size):
        chunk = tasks[i:i + chunk_size]
        results = await asyncio.gather(*chunk, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                continue
            fqdn, ip = result
            if ip:
                discovered.append((fqdn, ip))

    for fqdn, ip in discovered:
        severity = Severity.INFO
        tags = ["subdomain", "recon"]

        sensitive_keywords = [
            "admin", "dev", "staging", "internal", "test", "qa", "uat",
            "private", "secure", "backup", "db", "database", "git",
            "jenkins", "jira", "kibana", "grafana", "vault", "docker",
            "registry", "nexus", "ldap", "erp", "crm", "hr", "finance",
        ]

        for keyword in sensitive_keywords:
            if keyword in fqdn.lower():
                severity = Severity.MEDIUM
                tags.append("sensitive")
                break

        if any(k in fqdn.lower() for k in ["admin", "internal", "private", "vpn", "bastion"]):
            severity = Severity.HIGH

        vulns.append(Vulnerability(
            title=f"Subdomain Discovered: {fqdn}",
            description=f"Subdomain {fqdn} resolves to {ip}.",
            severity=severity,
            url=f"https://{fqdn}",
            evidence=f"IP: {ip}",
            remediation=(
                "Ensure all discovered subdomains are intended and secured. "
                "Remove unused DNS records."
            ),
            scanner="subdomain_enum",
            tags=tags,
        ))

    return vulns
