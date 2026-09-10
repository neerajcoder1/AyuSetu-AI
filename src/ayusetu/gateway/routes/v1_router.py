"""
AyuSetu Gateway v1 Router
=========================
Prefix: /api/v1
Mounts all REST endpoints and health checks.
"""

from fastapi import APIRouter
from ayusetu.gateway.routes.stubs import router as stubs_router
from ayusetu.gateway.routes.health import router as health_router
from ayusetu.consent.routes import router as consent_router
from ayusetu.audit.routes import router as audit_router
from ayusetu.redflag.routes import router as redflag_router
from ayusetu.deid.routes import router as deid_router

v1_router = APIRouter(prefix="/api/v1")

# Mount consent service routes
v1_router.include_router(consent_router)

# Mount audit service routes
v1_router.include_router(audit_router)

# Mount redflag service routes
v1_router.include_router(redflag_router)

# Mount de-identification service routes
v1_router.include_router(deid_router)

# Mount stubs and REST endpoints under /api/v1
v1_router.include_router(stubs_router)

