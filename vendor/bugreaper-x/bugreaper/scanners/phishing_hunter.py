from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import httpx

from bugreaper.core.models import Severity, Vulnerability

BRAND_KEYWORDS = [
    "paypal", "amazon", "apple", "microsoft", "google", "facebook", "instagram",
    "netflix", "bank", "chase", "wellsfargo", "citibank", "rbc", "bmo", "td",
    "government", "irs", "cra", "cra-arc", "sin", "ssn", "login", "verify",
    "secure", "update", "account", "suspended", "limited", "confirm",
]

PHISHING_INDICATORS = [
    r"your account.{0,50}(suspend|limit|verif)",
    r"(click|tap).{0,30}(here|below|link).{0,30}(verif|confirm|update)",
    r"(immediate|urgent|within \d+ hour)",
    r"(password|credit card|social security|sin number).{0,50}(enter|provide|update|confirm)",
    r"you have.{0,50}(won|been selected|prize|reward)",
]

CREDENTIAL_HARVESTING = [
    r'<input[^>]+type=["\']password["\'][^>]*>',
    r'<form[^>]+action=["\'][^"\']*(?:login|signin|auth|verify)[^"\']*["\']',
    r'<input[^>]+name=["\'](?:ssn|sin|credit.?card|card.?number)["\']',
]


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []
    parsed = urlparse(target)
    host = parsed.hostname or ""

    url_lower = target.lower()
    domain_lower = host.lower()

    brand_matches = [kw for kw in BRAND_KEYWORDS if kw in domain_lower and kw not in ["login", "secure", "update", "account", "verify"]]
    if len(brand_matches) >= 2:
        vulns.append(Vulnerability(
            title="Potential Brand Impersonation URL",
            description=f"Domain '{host}' contains multiple brand keywords: {brand_matches}",
            severity=Severity.HIGH,
            url=target,
            evidence=f"Brand keywords found: {brand_matches}",
            remediation="Investigate domain for phishing activity. Report to brand owner.",
            scanner="phishing_hunter",
            tags=["phishing", "brand-impersonation"],
        ))

    ip_pattern = r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    if re.match(ip_pattern, target):
        vulns.append(Vulnerability(
            title="IP-Based URL (Phishing Indicator)",
            description=f"Target uses raw IP address instead of domain name: {target}",
            severity=Severity.HIGH,
            url=target,
            remediation="Legitimate services use domain names. Treat IP-based URLs as suspicious.",
            scanner="phishing_hunter",
            tags=["phishing", "ip-url"],
        ))

    try:
        async with httpx.AsyncClient(verify=False, timeout=15, follow_redirects=True) as client:
            resp = await client.get(target)
            body = resp.text
            final_url = str(resp.url)
    except Exception:
        return vulns

    if final_url.rstrip("/") != target.rstrip("/"):
        final_domain = urlparse(final_url).hostname or ""
        original_domain = host
        if final_domain and original_domain and final_domain != original_domain:
            vulns.append(Vulnerability(
                title=f"Suspicious Redirect: {original_domain} → {final_domain}",
                description=f"URL redirects from {original_domain} to different domain {final_domain}.",
                severity=Severity.MEDIUM,
                url=target,
                evidence=f"Final URL: {final_url}",
                remediation="Verify redirect destinations are legitimate.",
                scanner="phishing_hunter",
                tags=["phishing", "redirect"],
            ))

    for pattern in PHISHING_INDICATORS:
        if re.search(pattern, body, re.IGNORECASE):
            vulns.append(Vulnerability(
                title="Phishing Language Detected",
                description=f"Phishing-style content pattern detected: {pattern}",
                severity=Severity.HIGH,
                url=target,
                evidence=re.search(pattern, body, re.IGNORECASE).group(0)[:200],
                remediation="Report to anti-phishing services. Investigate hosting provider.",
                scanner="phishing_hunter",
                tags=["phishing", "social-engineering"],
            ))
            break

    for pattern in CREDENTIAL_HARVESTING:
        matches = re.findall(pattern, body, re.IGNORECASE)
        if matches:
            vulns.append(Vulnerability(
                title="Credential Harvesting Form Detected",
                description="Page contains forms that may harvest sensitive credentials.",
                severity=Severity.HIGH,
                url=target,
                evidence=matches[0][:300],
                remediation="Verify this is a legitimate login page. Report if suspicious.",
                scanner="phishing_hunter",
                tags=["phishing", "credential-harvesting"],
            ))
            break

    return vulns
