from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from bugreaper.core.models import Severity, Vulnerability


async def _resolve(host: str, record_type: str) -> list[str]:
    try:
        import dns.resolver
        answers = dns.resolver.resolve(host, record_type, lifetime=10)
        return [str(r) for r in answers]
    except Exception:
        return []


async def _zone_transfer(host: str) -> bool:
    try:
        import dns.query
        import dns.zone
        ns_records = await _resolve(host, "NS")
        for ns in ns_records[:3]:
            ns = ns.rstrip(".")
            try:
                z = dns.zone.from_xfr(dns.query.xfr(ns, host, timeout=5))
                if z:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []
    parsed = urlparse(target)
    host = parsed.hostname or target.split("/")[0]

    zone_xfr = await _zone_transfer(host)
    if zone_xfr:
        vulns.append(Vulnerability(
            title="DNS Zone Transfer Allowed (AXFR)",
            description=(
                f"DNS zone transfer is permitted for {host}. "
                "This exposes the complete DNS zone including internal hosts."
            ),
            severity=Severity.CRITICAL,
            url=target,
            remediation="Restrict AXFR to authorized secondary nameservers only.",
            scanner="dns_scanner",
            tags=["dns", "zone-transfer", "information-disclosure"],
        ))

    spf = await _resolve(host, "TXT")
    has_spf = any("v=spf1" in r for r in spf)
    if not has_spf:
        vulns.append(Vulnerability(
            title="Missing SPF Record",
            description=f"No SPF record found for {host}. Domain is vulnerable to email spoofing.",
            severity=Severity.MEDIUM,
            url=target,
            remediation="Add an SPF TXT record: v=spf1 include:... -all",
            scanner="dns_scanner",
            tags=["dns", "email", "spf", "spoofing"],
        ))

    has_dmarc = False
    try:
        dmarc = await _resolve(f"_dmarc.{host}", "TXT")
        has_dmarc = any("v=DMARC1" in r for r in dmarc)
    except Exception:
        pass

    if not has_dmarc:
        vulns.append(Vulnerability(
            title="Missing DMARC Record",
            description=f"No DMARC policy for {host}. Phishing and spoofing are unmitigated.",
            severity=Severity.MEDIUM,
            url=target,
            remediation="Add: _dmarc.yourdomain TXT v=DMARC1; p=reject; rua=mailto:dmarc@yourdomain",
            scanner="dns_scanner",
            tags=["dns", "email", "dmarc", "phishing"],
        ))

    dnssec = await _resolve(host, "DNSKEY")
    if not dnssec:
        vulns.append(Vulnerability(
            title="DNSSEC Not Enabled",
            description=f"DNSSEC is not configured for {host}. DNS cache poisoning is possible.",
            severity=Severity.LOW,
            url=target,
            remediation="Enable DNSSEC signing on the domain and registrar.",
            scanner="dns_scanner",
            tags=["dns", "dnssec"],
        ))

    TAKEOVER_CNAMES = [
        "github.io", "amazonaws.com", "heroku.com", "netlify.app",
        "squarespace.com", "wixsite.com", "shopify.com", "fastly.net",
        "azure-api.net", "azurewebsites.net", "cloudapp.net",
    ]
    cname = await _resolve(host, "CNAME")
    for record in cname:
        for svc in TAKEOVER_CNAMES:
            if svc in record:
                vulns.append(Vulnerability(
                    title=f"Potential Subdomain Takeover: {host}",
                    description=(
                        f"{host} has a CNAME to {record} which may be an unclaimed "
                        f"{svc} resource, enabling subdomain takeover."
                    ),
                    severity=Severity.CRITICAL,
                    url=f"https://{host}",
                    evidence=f"CNAME: {record}",
                    remediation="Remove the dangling DNS record or claim the resource.",
                    scanner="dns_scanner",
                    tags=["dns", "subdomain-takeover"],
                ))

    return vulns
