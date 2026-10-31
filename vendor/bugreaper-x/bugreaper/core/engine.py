from __future__ import annotations

import asyncio
import importlib
import time
from datetime import datetime
from typing import Any, Callable

from bugreaper.core.models import ScanConfig, ScanResult, ScanStatus, ScanTarget, ScanType, Vulnerability

SCANNER_MAP = {
    ScanType.PORT: "bugreaper.scanners.port_scanner",
    ScanType.HEADERS: "bugreaper.scanners.header_analyzer",
    ScanType.SSL: "bugreaper.scanners.ssl_analyzer",
    ScanType.DNS: "bugreaper.scanners.dns_scanner",
    ScanType.PATTERNS: "bugreaper.scanners.pattern_engine",
    ScanType.PHISHING: "bugreaper.scanners.phishing_hunter",
    ScanType.RECON: "bugreaper.scanners.recon_engine",
    ScanType.EXPLOIT: "bugreaper.scanners.exploit_engine",
    ScanType.SUBDOMAIN: "bugreaper.scanners.subdomain_enum",
    ScanType.WAF: "bugreaper.scanners.waf_detector",
    ScanType.CMS: "bugreaper.scanners.cms_fingerprint",
    ScanType.API: "bugreaper.scanners.api_fuzzer",
    ScanType.OWASP: "bugreaper.scanners.owasp_scanner",
    ScanType.CLOUD: "bugreaper.scanners.cloud_scanner",
}

SCAN_PHASES: list[list[ScanType]] = [
    [ScanType.PORT, ScanType.DNS, ScanType.SSL],
    [ScanType.HEADERS, ScanType.WAF, ScanType.RECON, ScanType.SUBDOMAIN],
    [ScanType.CMS, ScanType.API, ScanType.OWASP, ScanType.CLOUD],
    [ScanType.PATTERNS, ScanType.EXPLOIT, ScanType.PHISHING],
]


class ScanEngine:
    def __init__(self) -> None:
        self._event_handlers: list[Callable[[str, Any], None]] = []
        self._active_scans: dict[str, ScanResult] = {}

    def on_event(self, handler: Callable[[str, Any], None]) -> None:
        self._event_handlers.append(handler)

    def _emit(self, event_type: str, data: Any) -> None:
        for handler in self._event_handlers:
            try:
                handler(event_type, data)
            except Exception:
                pass

    async def _run_scanner(self, scan_type: ScanType, target: str, config: dict[str, Any]) -> list[Vulnerability]:
        module_path = SCANNER_MAP.get(scan_type)
        if not module_path:
            return []
        try:
            module = importlib.import_module(module_path)
            vulns = await module.run(target, config)
            self._emit("scanner_complete", {"scanner": scan_type.value, "count": len(vulns)})
            return vulns
        except Exception as e:
            self._emit("scanner_error", {"scanner": scan_type.value, "error": str(e)})
            return []

    async def scan(self, target: ScanTarget, config: ScanConfig) -> ScanResult:
        result = ScanResult(target=target, config=config, status=ScanStatus.RUNNING)
        result.started_at = datetime.utcnow()
        self._active_scans[result.id] = result

        self._emit("scan_start", {"scan_id": result.id, "target": target.url})

        scanner_config: dict[str, Any] = {
            "timeout": target.timeout,
            "proxy": target.proxy or config.burp_proxy,
            "aggressive": config.aggressive,
            "depth": config.depth,
        }

        try:
            for phase_num, phase_scanners in enumerate(SCAN_PHASES, 1):
                active_scanners = [s for s in phase_scanners if s in config.scan_types]
                if not active_scanners:
                    continue

                self._emit("phase_start", {"phase": phase_num, "scanners": [s.value for s in active_scanners]})

                tasks = [self._run_scanner(st, target.url, scanner_config) for st in active_scanners]
                phase_results = await asyncio.gather(*tasks, return_exceptions=True)

                for scan_type, phase_result in zip(active_scanners, phase_results):
                    if isinstance(phase_result, list):
                        result.vulnerabilities.extend(phase_result)
                        result.scanner_outputs[scan_type.value] = len(phase_result)

                self._emit("phase_complete", {
                    "phase": phase_num,
                    "vulns_so_far": len(result.vulnerabilities),
                })

            if config.ai_analysis:
                from bugreaper.core.config import settings
                if settings.anthropic_api_key:
                    self._emit("ai_analysis_start", {"scan_id": result.id})
                    from bugreaper.ai.analyst import analyze_results
                    result.ai_analysis = await analyze_results(
                        result, settings.anthropic_api_key, settings.ai_model
                    )
                    self._emit("ai_analysis_complete", {"scan_id": result.id})

            result.risk_score = _calculate_risk_score(result)
            result.attack_chains = _build_attack_chains(result)
            result.status = ScanStatus.COMPLETED

        except asyncio.CancelledError:
            result.status = ScanStatus.CANCELLED
        except Exception as e:
            result.status = ScanStatus.FAILED
            result.error = str(e)
        finally:
            result.completed_at = datetime.utcnow()
            if result.started_at:
                result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
            self._active_scans.pop(result.id, None)
            self._emit("scan_complete", {
                "scan_id": result.id,
                "status": result.status.value,
                "vuln_count": len(result.vulnerabilities),
                "risk_score": result.risk_score,
            })

        return result

    def get_active_scans(self) -> list[str]:
        return list(self._active_scans.keys())


def _calculate_risk_score(result: ScanResult) -> float:
    weights = {"god-tier": 10.0, "critical": 9.0, "high": 7.0, "medium": 4.0, "low": 1.5, "info": 0.1}
    total = sum(weights.get(v.severity.value, 0) for v in result.vulnerabilities)
    return min(10.0, round(total / max(1, len(result.vulnerabilities)) + (len(result.vulnerabilities) * 0.1), 1))


def _build_attack_chains(result: ScanResult) -> list[dict[str, Any]]:
    chains = []
    critical = [v for v in result.vulnerabilities if v.severity.value in ("critical", "god-tier")]
    high = [v for v in result.vulnerabilities if v.severity.value == "high"]

    if critical and high:
        chain = {
            "name": "Multi-Stage Exploitation Chain",
            "steps": [
                {"step": 1, "finding": critical[0].title, "tactic": "Initial Access"},
                {"step": 2, "finding": high[0].title if high else critical[0].title, "tactic": "Privilege Escalation"},
            ],
            "impact": "Full system compromise possible",
            "likelihood": "High",
        }
        chains.append(chain)

    recon_vulns = [v for v in result.vulnerabilities if "recon" in v.tags or "information-disclosure" in v.tags]
    exploit_vulns = [v for v in result.vulnerabilities if "injection" in " ".join(v.tags) or "ssrf" in v.tags]
    if recon_vulns and exploit_vulns:
        chains.append({
            "name": "Recon → Exploitation Chain",
            "steps": [
                {"step": 1, "finding": recon_vulns[0].title, "tactic": "Discovery"},
                {"step": 2, "finding": exploit_vulns[0].title, "tactic": "Exploitation"},
            ],
            "impact": "Data exfiltration or code execution",
            "likelihood": "Medium",
        })

    return chains


engine = ScanEngine()
