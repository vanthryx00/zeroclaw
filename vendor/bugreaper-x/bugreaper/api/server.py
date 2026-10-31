from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from bugreaper.core.models import ScanConfig, ScanResult, ScanStatus, ScanTarget
from bugreaper.core.config import settings


_scan_store: dict[str, ScanResult] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from bugreaper.core.engine import engine
    app.state.engine = engine
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="BugReaper X API",
        description="REAPER — Autonomous Vulnerability Intelligence Platform",
        version="4.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def timing_middleware(request, call_next):
        start = time.time()
        response = await call_next(request)
        response.headers["X-Process-Time"] = str(round(time.time() - start, 4))
        response.headers["X-Powered-By"] = "BugReaper X REAPER v4.0"
        return response

    @app.get("/", tags=["info"])
    async def root():
        return {
            "name": "BugReaper X",
            "version": "4.0.0",
            "description": "REAPER Autonomous Vulnerability Intelligence",
            "by": "Kairyx Security Solutions, Fort Saskatchewan, Alberta",
            "docs": "/docs",
            "health": "/health",
        }

    @app.get("/health", tags=["info"])
    async def health():
        return {"status": "operational", "version": "4.0.0"}

    class ScanRequest(BaseModel):
        url: str
        scan_types: list[str] | None = None
        aggressive: bool = False
        ai_analysis: bool = True
        burp_proxy: str | None = None
        timeout: int = 30

    @app.post("/api/v1/scans", tags=["scans"])
    async def create_scan(req: ScanRequest, background_tasks: BackgroundTasks):
        from bugreaper.core.models import ScanType
        from bugreaper.core.engine import engine

        scan_types = list(ScanType)
        if req.scan_types:
            try:
                scan_types = [ScanType(t) for t in req.scan_types]
            except ValueError as e:
                raise HTTPException(400, f"Invalid scan type: {e}")

        target = ScanTarget(url=req.url, timeout=req.timeout, proxy=req.burp_proxy)
        config = ScanConfig(
            scan_types=scan_types,
            ai_analysis=req.ai_analysis,
            aggressive=req.aggressive,
            burp_proxy=req.burp_proxy,
        )

        result = ScanResult(target=target, config=config, status=ScanStatus.PENDING)
        _scan_store[result.id] = result

        async def run_scan():
            _scan_store[result.id] = await engine.scan(target, config)

        background_tasks.add_task(run_scan)
        return {"scan_id": result.id, "status": "started", "target": req.url}

    @app.get("/api/v1/scans/{scan_id}", tags=["scans"])
    async def get_scan(scan_id: str):
        result = _scan_store.get(scan_id)
        if not result:
            raise HTTPException(404, "Scan not found")
        return {
            "scan_id": result.id,
            "status": result.status.value,
            "target": result.target.url,
            "risk_score": result.risk_score,
            "vuln_count": len(result.vulnerabilities),
            "vuln_counts": result.vuln_counts,
            "duration_seconds": result.duration_seconds,
            "ai_analysis": result.ai_analysis,
            "attack_chains": result.attack_chains,
        }

    @app.get("/api/v1/scans/{scan_id}/vulnerabilities", tags=["scans"])
    async def get_vulnerabilities(scan_id: str):
        result = _scan_store.get(scan_id)
        if not result:
            raise HTTPException(404, "Scan not found")
        return [v.model_dump() for v in result.vulnerabilities]

    @app.get("/api/v1/scans/{scan_id}/report", tags=["reports"])
    async def get_report(scan_id: str, fmt: str = "json"):
        from bugreaper.reporting.generator import generate_report
        result = _scan_store.get(scan_id)
        if not result:
            raise HTTPException(404, "Scan not found")
        if result.status != ScanStatus.COMPLETED:
            raise HTTPException(400, f"Scan not complete (status: {result.status.value})")
        content = generate_report(result, fmt)
        content_type = {
            "html": "text/html",
            "json": "application/json",
            "csv": "text/csv",
            "sarif": "application/json",
            "markdown": "text/markdown",
        }.get(fmt, "text/plain")
        from fastapi.responses import Response
        return Response(content=content, media_type=content_type)

    @app.get("/api/v1/scans", tags=["scans"])
    async def list_scans():
        return [
            {"scan_id": r.id, "target": r.target.url, "status": r.status.value, "risk_score": r.risk_score}
            for r in _scan_store.values()
        ]

    @app.delete("/api/v1/scans/{scan_id}", tags=["scans"])
    async def delete_scan(scan_id: str):
        if scan_id not in _scan_store:
            raise HTTPException(404, "Scan not found")
        del _scan_store[scan_id]
        return {"deleted": scan_id}

    return app


app = create_app()
