from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from bugreaper.core.models import Severity, Vulnerability

CLOUD_METADATA_ENDPOINTS = {
    "AWS": [
        ("http://169.254.169.254/latest/meta-data/", ["ami-id", "instance-id"]),
        ("http://169.254.169.254/latest/meta-data/iam/security-credentials/", ["role"]),
        ("http://169.254.169.254/latest/user-data", []),
    ],
    "GCP": [
        ("http://metadata.google.internal/computeMetadata/v1/", ["project"]),
        ("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token", ["access_token"]),
    ],
    "Azure": [
        ("http://169.254.169.254/metadata/instance?api-version=2021-02-01", ["subscriptionId"]),
        ("http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/", ["access_token"]),
    ],
}

S3_BUCKET_PATTERNS = [
    r"(https?://)?([a-z0-9-]+)\.s3(?:-[a-z0-9-]+)?\.amazonaws\.com",
    r"(https?://)?s3(?:-[a-z0-9-]+)?\.amazonaws\.com/([a-z0-9-]+)",
    r"(https?://)?([a-z0-9-]+)\.storage\.googleapis\.com",
    r"(https?://)?storage\.googleapis\.com/([a-z0-9-]+)",
    r"(https?://)?([a-z0-9-]+)\.blob\.core\.windows\.net",
]

CLOUD_SECRETS = [
    (r"AKIA[A-Z0-9]{16}", "AWS Access Key ID"),
    (r"[A-Za-z0-9/+=]{40}", "AWS Secret Access Key (potential)"),
    (r"ya29\.[A-Za-z0-9\-_]+", "Google OAuth Token"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API Key"),
    (r"(az[a-zA-Z0-9]{34})", "Azure SAS Token"),
    (r"DefaultEndpointsProtocol=(https?);AccountName=[^;]+;AccountKey=[^;]+", "Azure Storage Connection String"),
]


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []

    async with httpx.AsyncClient(verify=False, timeout=10, follow_redirects=True) as client:
        try:
            resp = await client.get(target)
            body = resp.text
        except Exception:
            return vulns

        for pattern, secret_type in CLOUD_SECRETS:
            matches = re.findall(pattern, body)
            if matches:
                vulns.append(Vulnerability(
                    title=f"Cloud Credential Exposed: {secret_type}",
                    description=f"Potential {secret_type} found in page response.",
                    severity=Severity.CRITICAL,
                    url=target,
                    evidence=str(matches[0])[:100],
                    remediation="Rotate all exposed credentials immediately. Use secret management.",
                    scanner="cloud_scanner",
                    tags=["cloud", "secrets", "credentials"],
                ))

        for pattern in S3_BUCKET_PATTERNS:
            matches = re.findall(pattern, body)
            for match in matches[:3]:
                bucket_name = match[1] if isinstance(match, tuple) and len(match) > 1 else str(match)
                if not bucket_name:
                    continue
                bucket_url = f"https://{bucket_name}.s3.amazonaws.com/" if "s3" in pattern else f"https://storage.googleapis.com/{bucket_name}/"
                try:
                    r = await client.get(bucket_url, timeout=8)
                    if r.status_code == 200 and ("ListBucketResult" in r.text or "<Contents>" in r.text):
                        vulns.append(Vulnerability(
                            title=f"Public Cloud Bucket: {bucket_name}",
                            description=f"Cloud storage bucket '{bucket_name}' is publicly readable.",
                            severity=Severity.HIGH,
                            url=bucket_url,
                            evidence=r.text[:300],
                            remediation="Set bucket ACL to private. Enable bucket policies.",
                            scanner="cloud_scanner",
                            tags=["cloud", "s3", "bucket", "public"],
                        ))
                except Exception:
                    pass

        for provider, endpoints in CLOUD_METADATA_ENDPOINTS.items():
            for endpoint_url, indicators in endpoints[:1]:
                extra_headers = {}
                if provider == "GCP":
                    extra_headers = {"Metadata-Flavor": "Google"}
                elif provider == "Azure":
                    extra_headers = {"Metadata": "true"}
                try:
                    r = await client.get(endpoint_url, headers=extra_headers, timeout=5)
                    if r.status_code == 200 and any(ind in r.text for ind in indicators):
                        vulns.append(Vulnerability(
                            title=f"Cloud Metadata Service Accessible: {provider}",
                            description=(
                                f"{provider} instance metadata endpoint is reachable from this context. "
                                "This may indicate an SSRF vulnerability or misconfiguration."
                            ),
                            severity=Severity.CRITICAL,
                            url=endpoint_url,
                            evidence=r.text[:300],
                            remediation="Block access to metadata endpoints via firewall. Fix SSRF vulnerabilities.",
                            scanner="cloud_scanner",
                            tags=["cloud", "metadata", "ssrf", provider.lower()],
                        ))
                except Exception:
                    pass

    return vulns
