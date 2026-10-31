from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin

import httpx

from bugreaper.core.models import Severity, Vulnerability

API_PATHS = [
    "/api", "/api/v1", "/api/v2", "/api/v3", "/rest", "/graphql",
    "/swagger.json", "/openapi.json", "/openapi.yaml", "/api-docs",
    "/v1", "/v2", "/v3",
]

AUTH_BYPASS_HEADERS = [
    {"X-Original-URL": "/admin"},
    {"X-Rewrite-URL": "/admin"},
    {"X-Custom-IP-Authorization": "127.0.0.1"},
    {"X-Forwarded-For": "127.0.0.1"},
    {"X-Real-IP": "127.0.0.1"},
    {"Authorization": "null"},
    {"Authorization": "undefined"},
    {"Authorization": "Bearer null"},
    {"Authorization": "Basic YWRtaW46YWRtaW4="},
]

GRAPHQL_INTROSPECTION = """
{
  __schema {
    types { name kind description }
    queryType { name }
    mutationType { name }
    subscriptionType { name }
  }
}
"""

GRAPHQL_DEPTH_BOMB = """
{
  a { b { c { d { e { f { g { h { i { j { k { l { __typename } } } } } } } } } } } }
}
"""


async def _probe(client: httpx.AsyncClient, url: str, method: str = "GET", **kwargs: Any) -> tuple[str, int, str]:
    try:
        func = getattr(client, method.lower())
        r = await func(url, timeout=10, **kwargs)
        return url, r.status_code, r.text[:500]
    except Exception:
        return url, 0, ""


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []
    base = target.rstrip("/")

    async with httpx.AsyncClient(verify=False, timeout=15, follow_redirects=True) as client:
        api_probe_tasks = [_probe(client, urljoin(base + "/", path.lstrip("/"))) for path in API_PATHS]
        api_results = await asyncio.gather(*api_probe_tasks, return_exceptions=True)

        found_apis: list[str] = []
        for result in api_results:
            if isinstance(result, Exception):
                continue
            url, status, content = result
            if status == 200 and len(content) > 10:
                found_apis.append(url)
                if "swagger" in url or "openapi" in url or "api-docs" in url:
                    vulns.append(Vulnerability(
                        title=f"API Documentation Exposed: {url}",
                        description=(
                            f"API documentation at {url} is publicly accessible. "
                            "This exposes all endpoints, parameters and authentication."
                        ),
                        severity=Severity.MEDIUM,
                        url=url,
                        evidence=content[:300],
                        remediation="Restrict API docs to authenticated users or internal networks.",
                        scanner="api_fuzzer",
                        tags=["api", "documentation", "information-disclosure"],
                    ))

        graphql_url = urljoin(base + "/", "graphql")
        _, status, content = await _probe(
            client, graphql_url, "POST",
            json={"query": GRAPHQL_INTROSPECTION},
            headers={"Content-Type": "application/json"},
        )
        if status == 200 and "__schema" in content:
            vulns.append(Vulnerability(
                title="GraphQL Introspection Enabled",
                description=(
                    "GraphQL introspection is enabled, exposing the complete API schema "
                    "including all types, queries, mutations and fields."
                ),
                severity=Severity.MEDIUM,
                url=graphql_url,
                evidence=content[:300],
                remediation="Disable introspection in production. Implement query depth limits.",
                scanner="api_fuzzer",
                tags=["graphql", "api", "information-disclosure"],
            ))

            _, depth_status, depth_content = await _probe(
                client, graphql_url, "POST",
                json={"query": GRAPHQL_DEPTH_BOMB},
                headers={"Content-Type": "application/json"},
            )
            if depth_status == 200:
                vulns.append(Vulnerability(
                    title="GraphQL No Query Depth Limit",
                    description=(
                        "GraphQL server processes deeply nested queries, "
                        "enabling DoS via query depth bombs."
                    ),
                    severity=Severity.HIGH,
                    url=graphql_url,
                    remediation="Implement maximum query depth limit (e.g. max depth=5).",
                    scanner="api_fuzzer",
                    tags=["graphql", "api", "dos"],
                ))

        protected_endpoints = ["/api/v1/admin", "/api/v1/users", "/api/admin", "/admin/api"]
        for endpoint in protected_endpoints:
            url = urljoin(base + "/", endpoint.lstrip("/"))
            _, base_status, _ = await _probe(client, url)
            if base_status == 403:
                for bypass_headers in AUTH_BYPASS_HEADERS:
                    try:
                        r = await client.get(url, headers=bypass_headers, timeout=8)
                        if r.status_code == 200 and len(r.text) > 50:
                            vulns.append(Vulnerability(
                                title=f"Authorization Bypass via Header: {endpoint}",
                                description=(
                                    f"Access to {endpoint} bypassed using headers: {bypass_headers}"
                                ),
                                severity=Severity.CRITICAL,
                                url=url,
                                evidence=str(bypass_headers),
                                remediation="Do not trust client-provided IP headers for access control.",
                                scanner="api_fuzzer",
                                tags=["api", "auth-bypass", "owasp-a01"],
                            ))
                            break
                    except Exception:
                        pass

    return vulns
