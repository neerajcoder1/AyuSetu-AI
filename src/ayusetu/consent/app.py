"""
Consent Service Standalone FastAPI Application
==============================================
Port: 8108 per PRD v2.0 §22.5.
Runs the Consent & DPDP service with security headers and error taxonomy.
"""

from fastapi import FastAPI, status
from ayusetu.gateway.middleware.error_handler import register_error_handlers
from ayusetu.consent.routes import router as consent_router

consent_app = FastAPI(
    title="AyuSetu Consent & DPDP Service",
    description="Microservice managing DPDP consent records, purposes, offline chains, and ABDM lifecycle",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Register uniform error taxonomy
register_error_handlers(consent_app)

# Health endpoints for consent service
@consent_app.get("/health", status_code=status.HTTP_200_OK, tags=["system"])
def consent_health():
    return {"status": "ok", "service": "consent", "port": 8108}


# Mount consent routes under /api/v1
consent_app.include_router(consent_router, prefix="/api/v1")
