from __future__ import annotations

from typing import Any

import httpx

from bugreaper.core.models import Severity, Vulnerability

REQUIRED_HEADERS = {
    "Strict-Transport-Security": (
        Severity.HIGH,
        "Missing HSTS header allows downgrade attacks.",
        "Add: Strict-Transport-Security: max-age=31536000; includeSubDomains; preload",
    ),
    "Content-Security-Policy": (
        Severity.HIGH,
        "Missing CSP exposes the application to XSS attacks.",
        "Implement a strict Content-Security-Policy header.",
    ),
    "X-Frame-Options": (
        Severity.MEDIUM,
        "Missing X-Frame-Options allows clickjacking.",
        "Add: X-Frame-Options: DENY or SAMEORIGIN",
    ),
    "X-Content-Type-Options": (
        Severity.MEDIUM,
        "Missing X-Content-Type-Options allows MIME sniffing.",
        "Add: X-Content-Type-Options: nosniff",
    ),
    "Referrer-Policy": (
        Severity.LOW,
        "Missing Referrer-Policy may leak sensitive URL data.",
        "Add: Referrer-Policy: strict-origin-when-cross-origin",
    ),
    "Permissions-Policy": (
        Severity.LOW,
        "Missing Permissions-Policy allows unrestricted browser API access.",
        "Add a Permissions-Policy header restricting camera, microphone, geolocation.",
    ),
    "X-XSS-Protection": (
        Severity.LOW,
        "Missing X-XSS-Protection (legacy browsers may be vulnerable).",
        "Add: X-XSS-Protection: 1; mode=block",
    ),
    "Cross-Origin-Embedder-Policy": (
        Severity.LOW,
        "Missing COEP weakens cross-origin isolation.",
        "Add: Cross-Origin-Embedder-Policy: require-corp",
    ),
    "Cross-Origin-Opener-Policy": (
        Severity.LOW,
        "Missing COOP allows cross-origin window access.",
        "Add: Cross-Origin-Opener-Policy: same-origin",
    ),
    "Cross-Origin-Resource-Policy": (
        Severity.LOW,
        "Missing CORP allows cross-origin resource embedding.",
        "Add: Cross-Origin-Resource-Policy: same-origin",
    ),
}

LEAKING_HEADERS = ["Server", "X-Powered-By", "X-AspNet-Version", "X-Generator", "Via"]


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []

    try:
        async with httpx.AsyncClient(verify=False, timeout=15, follow_redirects=True) as client:
            resp = await client.get(target)
    except Exception as e:
        return [Vulnerability(
            title="Header Analysis Failed",
            description=f"Could not connect to {target}: {e}",
            severity=Severity.INFO,
            scanner="header_analyzer",
        )]

    headers = {k.lower(): v for k, v in resp.headers.items()}
    raw_headers = dict(resp.headers)

    for header, (severity, desc, remediation) in REQUIRED_HEADERS.items():
        if header.lower() not in headers:
            vulns.append(Vulnerability(
                title=f"Missing Security Header: {header}",
                description=desc,
                severity=severity,
                url=target,
                remediation=remediation,
                scanner="header_analyzer",
                tags=["headers", "misconfiguration"],
            ))

    for header in LEAKING_HEADERS:
        if header.lower() in headers:
            value = headers[header.lower()]
            vulns.append(Vulnerability(
                title=f"Information Disclosure: {header} Header",
                description=(
                    f"The {header} header reveals technology details: '{value}'. "
                    "This aids reconnaissance by attackers."
                ),
                severity=Severity.LOW,
                url=target,
                evidence=f"{header}: {value}",
                remediation=f"Remove or obfuscate the {header} response header.",
                scanner="header_analyzer",
                tags=["headers", "information-disclosure"],
            ))

    cors_origin = headers.get("access-control-allow-origin", "")
    if cors_origin == "*":
        vulns.append(Vulnerability(
            title="Overly Permissive CORS Policy",
            description=(
                "Access-Control-Allow-Origin: * allows any origin to read responses. "
                "This may expose sensitive data to malicious sites."
            ),
            severity=Severity.HIGH,
            url=target,
            evidence="Access-Control-Allow-Origin: *",
            remediation="Restrict CORS to specific trusted origins.",
            scanner="header_analyzer",
            tags=["cors", "misconfiguration"],
        ))

    set_cookie = raw_headers.get("Set-Cookie", "")
    if set_cookie:
        if "httponly" not in set_cookie.lower():
            vulns.append(Vulnerability(
                title="Cookie Missing HttpOnly Flag",
                description="Session cookie lacks HttpOnly flag, enabling XSS theft.",
                severity=Severity.MEDIUM,
                url=target,
                evidence=set_cookie[:200],
                remediation="Set HttpOnly flag on all session cookies.",
                scanner="header_analyzer",
                tags=["cookies", "session"],
            ))
        if "secure" not in set_cookie.lower() and target.startswith("https"):
            vulns.append(Vulnerability(
                title="Cookie Missing Secure Flag",
                description="Cookie transmitted over HTTPS but lacks Secure flag.",
                severity=Severity.MEDIUM,
                url=target,
                evidence=set_cookie[:200],
                remediation="Set Secure flag on all cookies.",
                scanner="header_analyzer",
                tags=["cookies", "session"],
            ))
        if "samesite" not in set_cookie.lower():
            vulns.append(Vulnerability(
                title="Cookie Missing SameSite Attribute",
                description="Cookie lacks SameSite attribute, enabling CSRF attacks.",
                severity=Severity.MEDIUM,
                url=target,
                evidence=set_cookie[:200],
                remediation="Set SameSite=Strict or SameSite=Lax on session cookies.",
                scanner="header_analyzer",
                tags=["cookies", "csrf"],
            ))

    return vulns
