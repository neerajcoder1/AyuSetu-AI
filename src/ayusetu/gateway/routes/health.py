"""
Gateway Health & Readiness Router
=================================
Exposes healthcheck probes mounted on gateway endpoints.
"""

from typing import Any, Dict
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from ayusetu.common.database import SyncSessionLocal
from ayusetu.common.redis_client import ping_redis
from ayusetu.common.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health", status_code=status.HTTP_200_OK)
def liveness() -> Dict[str, str]:
    """Basic liveness probe."""
    return {"status": "ok", "service": "ayusetu-gateway", "env": settings.AYUSETU_ENV}


@router.get("/ready", status_code=status.HTTP_200_OK)
def readiness(response: Response) -> Dict[str, Any]:
    """
    Readiness probe validating DB and Redis connectivity for the gateway.
    Returns 200 if all critical backends are available, 503 if degraded.
    """
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

    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ready else "degraded",
        "service": "ayusetu-gateway",
        "components": {
            "database": "connected" if db_ok else "unreachable",
            "redis": "connected" if redis_ok else "unreachable"
        }
    }


@router.get("/api/v1/health", status_code=status.HTTP_200_OK)
def api_v1_health(response: Response) -> Dict[str, Any]:
    return readiness(response)
