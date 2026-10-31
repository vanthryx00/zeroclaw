from __future__ import annotations

from typing import Any

import httpx

from bugreaper.core.models import Severity, Vulnerability

WAF_SIGNATURES: dict[str, list[tuple[str, str]]] = {
    "Cloudflare": [
        ("server", "cloudflare"),
        ("cf-ray", ""),
        ("x-frame-options", "SAMEORIGIN"),
    ],
    "AWS WAF": [
        ("x-amzn-requestid", ""),
        ("x-amz-cf-id", ""),
    ],
    "ModSecurity": [
        ("server", "mod_security"),
        ("x-mod-security", ""),
    ],
    "F5 BIG-IP": [
        ("x-cnection", ""),
        ("set-cookie", "BIGipServer"),
    ],
    "Imperva Incapsula": [
        ("x-iinfo", ""),
        ("set-cookie", "incap_ses"),
    ],
    "Akamai": [
        ("x-akamai-transformed", ""),
        ("x-check-cacheable", ""),
    ],
    "Sucuri": [
        ("x-sucuri-id", ""),
        ("server", "sucuri/cloudbased"),
    ],
    "Barracuda": [
        ("set-cookie", "barra_counter_session"),
    ],
    "Wordfence": [
        ("set-cookie", "wfvt_"),
    ],
    "Nginx WAF": [
        ("server", "nginx"),
        ("x-nginx-cache", ""),
    ],
    "Palo Alto": [
        ("x-pan-unit", ""),
    ],
}

BYPASS_TECHNIQUES = [
    ("X-Forwarded-For: 127.0.0.1", "IP spoofing via X-Forwarded-For"),
    ("X-Real-IP: 127.0.0.1", "IP spoofing via X-Real-IP"),
    ("X-Originating-IP: 127.0.0.1", "IP spoofing via X-Originating-IP"),
    ("X-Custom-IP-Authorization: 127.0.0.1", "Authorization bypass via IP header"),
    ("X-Forward-For: 127.0.0.1", "Typo variant IP spoofing"),
]


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []
    detected_wafs: list[str] = []

    try:
        async with httpx.AsyncClient(verify=False, timeout=15, follow_redirects=True) as client:
            resp = await client.get(target)
            resp_headers = {k.lower(): v.lower() for k, v in resp.headers.items()}
            cookies = resp.headers.get("set-cookie", "").lower()

            for waf_name, signatures in WAF_SIGNATURES.items():
                matched = 0
                for header, value in signatures:
                    header_val = resp_headers.get(header, "")
                    if value and value.lower() in header_val:
                        matched += 1
                    elif not value and header in resp_headers:
                        matched += 1
                    elif header == "set-cookie" and value.lower() in cookies:
                        matched += 1
                if matched >= 1:
                    detected_wafs.append(waf_name)

            for header_val, description in BYPASS_TECHNIQUES:
                header_name, header_value = header_val.split(": ", 1)
                try:
                    bypass_resp = await client.get(
                        target,
                        headers={header_name: header_value, "X-Attack-Test": "<script>alert(1)</script>"},
                    )
                    if bypass_resp.status_code != 403 and bypass_resp.status_code != 406:
                        if detected_wafs:
                            vulns.append(Vulnerability(
                                title=f"WAF Bypass Possible: {description}",
                                description=(
                                    f"WAF may be bypassed using {description}. "
                                    f"Request returned {bypass_resp.status_code} instead of being blocked."
                                ),
                                severity=Severity.HIGH,
                                url=target,
                                evidence=f"Header: {header_val}",
                                remediation="Validate client IP from trusted proxy headers only.",
                                scanner="waf_detector",
                                tags=["waf", "bypass"],
                            ))
                except Exception:
                    pass

    except Exception:
        return vulns

    if detected_wafs:
        vulns.insert(0, Vulnerability(
            title=f"WAF Detected: {', '.join(detected_wafs)}",
            description=(
                f"Web Application Firewall detected: {', '.join(detected_wafs)}. "
                "WAF presence documented for exploitation planning."
            ),
            severity=Severity.INFO,
            url=target,
            evidence=f"Detected WAFs: {detected_wafs}",
            remediation="Ensure WAF rules are properly configured and regularly updated.",
            scanner="waf_detector",
            tags=["waf", "detection", "recon"],
        ))
    else:
        vulns.append(Vulnerability(
            title="No WAF Detected",
            description="No Web Application Firewall was detected. The application has no active filtering layer.",
            severity=Severity.MEDIUM,
            url=target,
            remediation="Deploy a WAF (Cloudflare, AWS WAF, ModSecurity) to filter malicious requests.",
            scanner="waf_detector",
            tags=["waf", "missing-control"],
        ))

    return vulns
