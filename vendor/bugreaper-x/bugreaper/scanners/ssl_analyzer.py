from __future__ import annotations

import ssl
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from bugreaper.core.models import Severity, Vulnerability


async def run(target: str, config: dict[str, Any]) -> list[Vulnerability]:
    vulns: list[Vulnerability] = []
    parsed = urlparse(target)
    host = parsed.hostname or target
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    if parsed.scheme != "https" and port != 443:
        vulns.append(Vulnerability(
            title="No HTTPS / TLS Encryption",
            description=f"Target {target} does not use HTTPS. All traffic is unencrypted.",
            severity=Severity.CRITICAL,
            url=target,
            remediation="Deploy TLS certificate and redirect all HTTP to HTTPS.",
            scanner="ssl_analyzer",
            tags=["ssl", "encryption"],
        ))
        return vulns

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_OPTIONAL

        conn = ctx.wrap_socket(
            socket.create_connection((host, port), timeout=10),
            server_hostname=host,
        )
        cert = conn.getpeercert()
        cipher = conn.cipher()
        protocol = conn.version()
        conn.close()
    except ssl.SSLCertVerificationError as e:
        vulns.append(Vulnerability(
            title="SSL Certificate Verification Failed",
            description=f"Certificate error for {host}: {e}",
            severity=Severity.HIGH,
            url=target,
            remediation="Install a valid certificate from a trusted CA.",
            scanner="ssl_analyzer",
            tags=["ssl", "certificate"],
        ))
        return vulns
    except Exception as e:
        vulns.append(Vulnerability(
            title="SSL Connection Failed",
            description=f"Could not establish TLS connection to {host}:{port}: {e}",
            severity=Severity.HIGH,
            url=target,
            scanner="ssl_analyzer",
        ))
        return vulns

    if cert:
        not_after = cert.get("notAfter", "")
        if not_after:
            try:
                expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
                    tzinfo=timezone.utc
                )
                now = datetime.now(timezone.utc)
                days_left = (expiry - now).days
                if days_left < 0:
                    vulns.append(Vulnerability(
                        title="Expired SSL Certificate",
                        description=f"Certificate expired {abs(days_left)} days ago ({not_after}).",
                        severity=Severity.CRITICAL,
                        url=target,
                        remediation="Renew the SSL certificate immediately.",
                        scanner="ssl_analyzer",
                        tags=["ssl", "certificate", "expired"],
                    ))
                elif days_left < 30:
                    vulns.append(Vulnerability(
                        title=f"SSL Certificate Expiring Soon ({days_left} days)",
                        description=f"Certificate expires {not_after}.",
                        severity=Severity.MEDIUM,
                        url=target,
                        remediation="Renew the SSL certificate before expiry.",
                        scanner="ssl_analyzer",
                        tags=["ssl", "certificate"],
                    ))
            except Exception:
                pass

        issuer = dict(x[0] for x in cert.get("issuer", []))
        subject = dict(x[0] for x in cert.get("subject", []))
        if issuer.get("organizationName") == subject.get("organizationName"):
            vulns.append(Vulnerability(
                title="Self-Signed SSL Certificate",
                description="Certificate is self-signed and not trusted by browsers.",
                severity=Severity.HIGH,
                url=target,
                evidence=f"Issuer: {issuer}",
                remediation="Replace with a certificate from a trusted CA (e.g. Let's Encrypt).",
                scanner="ssl_analyzer",
                tags=["ssl", "certificate", "self-signed"],
            ))

    if protocol in ("TLSv1", "TLSv1.1", "SSLv3", "SSLv2"):
        vulns.append(Vulnerability(
            title=f"Deprecated TLS Protocol: {protocol}",
            description=f"{protocol} is deprecated and vulnerable to POODLE/BEAST attacks.",
            severity=Severity.HIGH,
            url=target,
            remediation="Disable all protocols below TLS 1.2. Prefer TLS 1.3.",
            scanner="ssl_analyzer",
            tags=["ssl", "protocol", "deprecated"],
        ))

    if cipher:
        cipher_name = cipher[0] if cipher else ""
        weak = any(w in cipher_name.upper() for w in ["RC4", "DES", "3DES", "NULL", "EXPORT", "MD5"])
        if weak:
            vulns.append(Vulnerability(
                title=f"Weak SSL Cipher: {cipher_name}",
                description=f"Server supports weak cipher suite: {cipher_name}",
                severity=Severity.HIGH,
                url=target,
                remediation="Disable weak ciphers. Use AES-256-GCM or ChaCha20-Poly1305.",
                scanner="ssl_analyzer",
                tags=["ssl", "cipher", "weak"],
            ))

    return vulns
