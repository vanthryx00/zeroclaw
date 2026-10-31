from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, parse_qs, urlencode

import httpx

from bugreaper.core.models import Severity, Vulnerability


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []

    async with httpx.AsyncClient(verify=False, timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(target)
            body = resp.text.lower()
            headers = {k.lower(): v for k, v in resp.headers.items()}
        except Exception:
            return vulns

        if "access-control-allow-origin" not in headers:
            pass

        if "x-content-type-options" not in headers:
            vulns.append(Vulnerability(
                title="A05: Security Misconfiguration — Missing X-Content-Type-Options",
                description="Missing header allows MIME-type sniffing attacks.",
                severity=Severity.MEDIUM,
                url=target,
                remediation="Add: X-Content-Type-Options: nosniff",
                scanner="owasp_scanner",
                tags=["owasp-a05", "misconfiguration", "headers"],
            ))

        error_patterns = [
            ("sql syntax", "A03: SQL Error Disclosure", Severity.HIGH),
            ("you have an error in your sql", "A03: MySQL Error Disclosure", Severity.HIGH),
            ("warning: mysql", "A03: MySQL Warning Disclosure", Severity.HIGH),
            ("ora-0", "A03: Oracle Error Disclosure", Severity.HIGH),
            ("pg::", "A03: PostgreSQL Error Disclosure", Severity.HIGH),
            ("stack trace", "A05: Stack Trace Disclosure", Severity.MEDIUM),
            ("exception in thread", "A05: Java Exception Disclosure", Severity.MEDIUM),
            ("system.exception", "A05: .NET Exception Disclosure", Severity.MEDIUM),
            ("traceback (most recent call last)", "A05: Python Traceback Disclosure", Severity.MEDIUM),
            ("fatal error:", "A05: PHP Fatal Error Disclosure", Severity.MEDIUM),
        ]
        for pattern, title, severity in error_patterns:
            if pattern in body:
                vulns.append(Vulnerability(
                    title=title,
                    description=f"Error message found in response body: '{pattern}'",
                    severity=severity,
                    url=target,
                    evidence=pattern,
                    remediation="Configure custom error pages. Disable debug mode in production.",
                    scanner="owasp_scanner",
                    tags=["owasp-a05", "information-disclosure", "error"],
                ))

        try:
            r404 = await client.get(f"{target.rstrip('/')}/nonexistent-page-xyz-12345")
            if r404.status_code == 200:
                vulns.append(Vulnerability(
                    title="A05: Custom 404 Not Implemented",
                    description="Server returns 200 for non-existent pages (soft 404).",
                    severity=Severity.LOW,
                    url=target,
                    remediation="Implement proper 404 error handling.",
                    scanner="owasp_scanner",
                    tags=["owasp-a05", "misconfiguration"],
                ))
        except Exception:
            pass

        for method in ["PUT", "DELETE", "PATCH", "TRACE", "OPTIONS"]:
            try:
                r = await client.request(method, target, timeout=8)
                if r.status_code not in (405, 403, 501):
                    vulns.append(Vulnerability(
                        title=f"A05: Dangerous HTTP Method Allowed: {method}",
                        description=f"HTTP {method} method is accepted by the server.",
                        severity=Severity.MEDIUM if method != "TRACE" else Severity.HIGH,
                        url=target,
                        evidence=f"HTTP {r.status_code}",
                        remediation=f"Disable {method} method unless explicitly required.",
                        scanner="owasp_scanner",
                        tags=["owasp-a05", "http-methods"],
                    ))
            except Exception:
                pass

        sensitive_data_patterns = [
            (r"\b\d{16}\b", "A02: Credit Card Number in Response", Severity.CRITICAL),
            (r"\b[0-9]{3}-?[0-9]{2}-?[0-9]{4}\b", "A02: SSN in Response", Severity.CRITICAL),
            (r"password\s*[=:]\s*\S+", "A02: Password in Response", Severity.HIGH),
        ]

        import re
        raw_body = resp.text
        for pattern, title, severity in sensitive_data_patterns:
            if re.search(pattern, raw_body):
                vulns.append(Vulnerability(
                    title=title,
                    description=f"Sensitive data pattern detected in response: {title}",
                    severity=severity,
                    url=target,
                    remediation="Remove sensitive data from responses. Implement data masking.",
                    scanner="owasp_scanner",
                    tags=["owasp-a02", "sensitive-data"],
                ))

    return vulns
