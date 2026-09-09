"""
Audit Service Standalone FastAPI Application
============================================
Port: 8109 per PRD v2.0 §22.8 and common/config.py.
Runs the cryptographic audit logging microservice with standard error handling.
"""

from fastapi import FastAPI, status
from ayusetu.gateway.middleware.error_handler import register_error_handlers
from ayusetu.audit.routes import router as audit_router

audit_app = FastAPI(
    title="AyuSetu Audit Service",
    description="Microservice managing append-only cryptographic hash-chained audit logs, offline sync, and integrity verification",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Register uniform error taxonomy
register_error_handlers(audit_app)


# Health endpoints for audit service
@audit_app.get("/health", status_code=status.HTTP_200_OK, tags=["system"])
def audit_health():
    return {"status": "ok", "service": "audit", "port": 8109}


# Mount audit routes under /api/v1
audit_app.include_router(audit_router, prefix="/api/v1")
