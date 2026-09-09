"""
AyuSetu Gateway v1 Router
=========================
Prefix: /api/v1
Mounts all REST endpoints and health checks.
"""

from fastapi import APIRouter
from ayusetu.gateway.routes.stubs import router as stubs_router
from ayusetu.gateway.routes.health import router as health_router

v1_router = APIRouter(prefix="/api/v1")

# Mount stubs and REST endpoints under /api/v1
v1_router.include_router(stubs_router)
