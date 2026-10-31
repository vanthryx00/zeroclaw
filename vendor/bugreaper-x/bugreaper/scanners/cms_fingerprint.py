from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin

import httpx

from bugreaper.core.models import Severity, Vulnerability

CMS_SIGNATURES = {
    "WordPress": {
        "paths": ["/wp-login.php", "/wp-admin/", "/wp-content/"],
        "body_patterns": ["wp-content", "wp-includes", "WordPress"],
        "headers": {},
    },
    "Drupal": {
        "paths": ["/sites/default/", "/modules/", "/?q=user/login"],
        "body_patterns": ["Drupal.settings", "drupal.js", "Drupal"],
        "headers": {"X-Generator": "Drupal"},
    },
    "Joomla": {
        "paths": ["/administrator/", "/components/", "/templates/"],
        "body_patterns": ["Joomla!", "option=com_"],
        "headers": {},
    },
    "Magento": {
        "paths": ["/skin/frontend/", "/js/mage/", "/downloader/"],
        "body_patterns": ["Magento", "mage/cookies"],
        "headers": {},
    },
    "Shopify": {
        "paths": ["/cdn/shop/", "/apps/"],
        "body_patterns": ["Shopify.theme", "myshopify.com"],
        "headers": {"X-ShopId": ""},
    },
    "Wix": {
        "paths": ["/wix-code-public-dispatch/"],
        "body_patterns": ["wixstatic.com", "Wix.com"],
        "headers": {},
    },
    "Ghost": {
        "paths": ["/ghost/", "/content/themes/"],
        "body_patterns": ["Ghost", "ghost/api"],
        "headers": {"X-Powered-By": "Express"},
    },
    "Squarespace": {
        "paths": ["/config/", "/api/1/"],
        "body_patterns": ["squarespace.com", "Squarespace"],
        "headers": {},
    },
    "OpenCart": {
        "paths": ["/index.php?route=common/home", "/catalog/"],
        "body_patterns": ["OpenCart", "route=account/login"],
        "headers": {},
    },
}

WP_VULNERABILITIES = [
    ("/wp-json/wp/v2/users", "WordPress User Enumeration via REST API", Severity.HIGH),
    ("/xmlrpc.php", "WordPress XML-RPC Enabled (brute-force amplification)", Severity.HIGH),
    ("/?author=1", "WordPress Author Enumeration via URL", Severity.MEDIUM),
    ("/wp-content/debug.log", "WordPress Debug Log Exposed", Severity.CRITICAL),
    ("/wp-config.php.bak", "WordPress Config Backup Exposed", Severity.CRITICAL),
    ("/wp-content/uploads/", "WordPress Uploads Directory Listing", Severity.MEDIUM),
]


async def _probe(client: httpx.AsyncClient, url: str) -> tuple[str, int, str]:
    try:
        r = await client.get(url, timeout=10)
        return url, r.status_code, r.text[:1000]
    except Exception:
        return url, 0, ""


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []
    base = target.rstrip("/")

    async with httpx.AsyncClient(verify=False, timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(target)
            body = resp.text
            headers = {k.lower(): v for k, v in resp.headers.items()}
        except Exception:
            return vulns

        detected_cms: list[str] = []
        for cms, sigs in CMS_SIGNATURES.items():
            for pattern in sigs["body_patterns"]:
                if pattern.lower() in body.lower():
                    detected_cms.append(cms)
                    break
            for header, value in sigs["headers"].items():
                h = headers.get(header.lower(), "")
                if (value and value.lower() in h.lower()) or (not value and h):
                    if cms not in detected_cms:
                        detected_cms.append(cms)

        for cms in detected_cms:
            vulns.append(Vulnerability(
                title=f"CMS Detected: {cms}",
                description=(
                    f"{cms} CMS detected. Known vulnerabilities should be checked "
                    "for the specific version in use."
                ),
                severity=Severity.INFO,
                url=target,
                remediation=f"Keep {cms} and all plugins/themes updated to the latest version.",
                scanner="cms_fingerprint",
                tags=["cms", cms.lower(), "fingerprint"],
            ))

        if "WordPress" in detected_cms:
            wp_tasks = [_probe(client, urljoin(base + "/", path.lstrip("/"))) for path, _, _ in WP_VULNERABILITIES]
            wp_results = await asyncio.gather(*wp_tasks, return_exceptions=True)

            for i, result in enumerate(wp_results):
                if isinstance(result, Exception):
                    continue
                url, status, content = result
                path, title, severity = WP_VULNERABILITIES[i]
                if status in (200, 301, 302):
                    evidence = content[:300] if status == 200 else f"HTTP {status}"
                    vulns.append(Vulnerability(
                        title=title,
                        description=f"WordPress misconfiguration: {title}",
                        severity=severity,
                        url=url,
                        evidence=evidence,
                        remediation=f"Disable or restrict access to {path}.",
                        scanner="cms_fingerprint",
                        tags=["wordpress", "cms", "misconfiguration"],
                    ))

    return vulns
