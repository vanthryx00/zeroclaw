from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin

import httpx

from bugreaper.core.models import Severity, Vulnerability

DISCOVERY_PATHS = [
    "/.env", "/.git/config", "/.git/HEAD", "/config.php", "/config.yml", "/config.yaml",
    "/wp-config.php", "/database.yml", "/settings.py", "/local.settings.py",
    "/.htaccess", "/.htpasswd", "/web.config", "/appsettings.json",
    "/api/swagger.json", "/api/openapi.json", "/swagger.json", "/openapi.yaml",
    "/api-docs", "/swagger-ui.html", "/redoc", "/graphql",
    "/admin", "/admin/", "/administrator", "/wp-admin", "/phpmyadmin",
    "/phpinfo.php", "/info.php", "/test.php", "/debug.php",
    "/backup.zip", "/backup.tar.gz", "/backup.sql", "/dump.sql",
    "/server-status", "/server-info", "/.well-known/security.txt",
    "/robots.txt", "/sitemap.xml", "/crossdomain.xml", "/clientaccesspolicy.xml",
    "/.DS_Store", "/Thumbs.db", "/error_log", "/debug.log",
    "/actuator", "/actuator/health", "/actuator/env", "/actuator/beans",
    "/metrics", "/health", "/status", "/_cat/indices", "/_nodes",
    "/console", "/h2-console", "/rails/info/properties",
    "/.git/", "/.svn/", "/.hg/", "/.bzr/",
    "/node_modules/", "/vendor/", "/.npmrc", "/.dockerenv",
    "/docker-compose.yml", "/Dockerfile", "/Makefile",
]

TECH_FINGERPRINTS = {
    "WordPress": ["wp-content", "wp-includes", "wp-json"],
    "Drupal": ["drupal.js", "sites/default", "?q=user"],
    "Joomla": ["option=com_", "Joomla!", "/components/com_"],
    "Laravel": ["laravel_session", "X-Powered-By: PHP", "XSRF-TOKEN"],
    "Django": ["csrfmiddlewaretoken", "django", "__admin__"],
    "Spring Boot": ["X-Application-Context", "Whitelabel Error Page"],
    "Express.js": ["X-Powered-By: Express"],
    "ASP.NET": ["__VIEWSTATE", "ASP.NET", "X-AspNet-Version"],
    "Ruby on Rails": ["_rails_session", "X-Request-Id"],
    "Next.js": ["__NEXT_DATA__", "_next/static"],
}


async def _probe(client: httpx.AsyncClient, url: str) -> tuple[str, int, str]:
    try:
        resp = await client.get(url, timeout=8)
        return url, resp.status_code, resp.text[:500]
    except Exception:
        return url, 0, ""


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []

    async with httpx.AsyncClient(verify=False, timeout=15, follow_redirects=True) as client:
        try:
            resp = await client.get(target)
            body = resp.text
            base_url = str(resp.url).rstrip("/")
        except Exception:
            return vulns

        detected_tech: list[str] = []
        for tech, patterns in TECH_FINGERPRINTS.items():
            if any(p.lower() in body.lower() for p in patterns):
                detected_tech.append(tech)

        if detected_tech:
            vulns.append(Vulnerability(
                title=f"Technology Fingerprinted: {', '.join(detected_tech)}",
                description=f"Identified technologies: {', '.join(detected_tech)}",
                severity=Severity.INFO,
                url=target,
                evidence=f"Technologies: {detected_tech}",
                remediation="Remove version headers and generic error pages to reduce fingerprinting.",
                scanner="recon_engine",
                tags=["recon", "fingerprint"] + [t.lower() for t in detected_tech],
            ))

        tasks = [_probe(client, urljoin(base_url + "/", path.lstrip("/"))) for path in DISCOVERY_PATHS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                continue
            url, status, content = result
            if status not in (200, 301, 302, 403):
                continue

            path = url.replace(base_url, "")
            severity = Severity.MEDIUM
            tags = ["recon", "discovery"]

            if any(x in path for x in [".env", "config", "database", "settings", "wp-config"]):
                severity = Severity.CRITICAL
                tags.append("secrets")
            elif any(x in path for x in ["backup", "dump", ".sql", ".tar", ".zip"]):
                severity = Severity.CRITICAL
                tags.append("backup")
            elif ".git" in path or ".svn" in path:
                severity = Severity.CRITICAL
                tags.append("source-code")
            elif "swagger" in path or "openapi" in path or "graphql" in path:
                severity = Severity.MEDIUM
                tags.append("api-exposure")
            elif any(x in path for x in ["admin", "phpmyadmin", "console"]):
                severity = Severity.HIGH
                tags.append("admin-panel")
            elif any(x in path for x in ["phpinfo", "actuator", "metrics", "health"]):
                severity = Severity.HIGH
                tags.append("information-disclosure")

            vuln_title = f"Sensitive Path Exposed: {path}"
            if status == 403:
                vuln_title = f"Access Restricted Path Exists: {path}"
                severity = Severity.LOW

            vulns.append(Vulnerability(
                title=vuln_title,
                description=f"Path {url} returned HTTP {status}.",
                severity=severity,
                url=url,
                evidence=content[:300] if status == 200 else f"HTTP {status}",
                remediation=f"Restrict access to {path} or remove it from the server.",
                scanner="recon_engine",
                tags=tags,
            ))

    return vulns
