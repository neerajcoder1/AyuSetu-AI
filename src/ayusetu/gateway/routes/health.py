"""
Gateway Health & Readiness Router
=================================
Exposes liveness and readiness probes per PRD v2.0 §22.2 and Phase 8.
Guarantees ZERO leakage of credentials, database URLs, passwords, or stack traces.
"""

from typing import Any, Dict
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from ayusetu.common.config import settings
from ayusetu.common.database import SyncSessionLocal
from ayusetu.common.metrics import metrics_registry
from ayusetu.common.redis_client import ping_redis

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
@router.get("/live", status_code=status.HTTP_200_OK)
def liveness(response: Response) -> Dict[str, str]:
    """
    Lightweight, non-blocking liveness probe.
    Confirms gateway HTTP process is alive without executing heavy queries.
    """
    response.headers["Cache-Control"] = "no-store, no-cache"
    return {"status": "ok", "service": "ayusetu-gateway", "env": settings.AYUSETU_ENV}


@router.get("/ready", status_code=status.HTTP_200_OK)
def readiness(response: Response) -> Dict[str, Any]:
    """
    Readiness probe validating DB and Redis connectivity for the gateway.
    Returns 200 if all critical backends are available, 503 if degraded.
    Zero-PHI and zero credential leakage.
    """
    response.headers["Cache-Control"] = "no-store, no-cache"
    db_ok = False
    redis_ok = False

    try:
        with SyncSessionLocal() as session:
            session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    redis_ok = ping_redis()
    all_ready = db_ok and redis_ok

    # Record dependency telemetry
    metrics_registry.record_dependency_health("database", "connected" if db_ok else "unreachable")
    metrics_registry.record_dependency_health("redis", "connected" if redis_ok else "unreachable")

    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ready else "degraded",
        "service": "ayusetu-gateway",
        "components": {
            "database": "connected" if db_ok else "unreachable",
            "redis": "connected" if redis_ok else "unreachable",
        },
    }


@router.get("/api/v1/health", status_code=status.HTTP_200_OK)
def api_v1_health(response: Response) -> Dict[str, Any]:
    """Alias for readiness probe under /api/v1."""
    return readiness(response)
