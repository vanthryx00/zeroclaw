from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    GOD_TIER = "god-tier"


class ScanType(str, Enum):
    PORT = "port"
    HEADERS = "headers"
    SSL = "ssl"
    DNS = "dns"
    PATTERNS = "patterns"
    PHISHING = "phishing"
    RECON = "recon"
    EXPLOIT = "exploit"
    SUBDOMAIN = "subdomain"
    WAF = "waf"
    CMS = "cms"
    API = "api"
    OWASP = "owasp"
    CLOUD = "cloud"


class ScanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Vulnerability(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    severity: Severity
    cvss_score: float | None = None
    cve_id: str | None = None
    cwe_id: str | None = None
    url: str | None = None
    parameter: str | None = None
    payload: str | None = None
    evidence: str | None = None
    remediation: str | None = None
    scanner: str = ""
    tags: list[str] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    discovered_at: datetime = Field(default_factory=datetime.utcnow)


class ScanTarget(BaseModel):
    url: str
    ip: str | None = None
    ports: list[int] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)
    auth_token: str | None = None
    proxy: str | None = None
    user_agent: str = "BugReaperX/4.0 (+https://bugreaper-x.ca)"
    verify_ssl: bool = True
    timeout: int = 30
    follow_redirects: bool = True


class ScanConfig(BaseModel):
    scan_types: list[ScanType] = Field(default_factory=lambda: list(ScanType))
    max_concurrent: int = 10
    rate_limit: float = 10.0
    depth: int = 3
    aggressive: bool = False
    burp_proxy: str | None = None
    burp_api_key: str | None = None
    ai_analysis: bool = True
    generate_report: bool = True
    report_format: str = "html"
    custom_wordlist: str | None = None


class ScanResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target: ScanTarget
    config: ScanConfig
    status: ScanStatus = ScanStatus.PENDING
    vulnerabilities: list[Vulnerability] = Field(default_factory=list)
    scanner_outputs: dict[str, Any] = Field(default_factory=dict)
    ai_analysis: str | None = None
    attack_chains: list[dict[str, Any]] = Field(default_factory=list)
    risk_score: float = 0.0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error: str | None = None

    @property
    def vuln_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.vulnerabilities:
            counts[v.severity.value] = counts.get(v.severity.value, 0) + 1
        return counts


class ScheduledScan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    target_url: str
    config: ScanConfig
    cron_expression: str
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class APIKey(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    key_hash: str
    permissions: list[str] = Field(default_factory=lambda: ["scan", "report", "read"])
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_used: datetime | None = None
    expires_at: datetime | None = None
