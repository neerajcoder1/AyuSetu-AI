"""
Red-Flag Engine Standalone FastAPI Application
==============================================
Port: 8105 per PRD v2.0 §22.9 and common/config.py.
Runs the deterministic clinical safety rule evaluation microservice.
"""

from fastapi import FastAPI, status
from ayusetu.gateway.middleware.error_handler import register_error_handlers
from ayusetu.redflag.routes import router as redflag_router

redflag_app = FastAPI(
    title="AyuSetu Red-Flag Engine",
    description="Microservice managing deterministic clinical safety red-flag evaluation, 3-tier severity escalation, and alert queues",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Register uniform error taxonomy
register_error_handlers(redflag_app)


# Health endpoints for red-flag service
@redflag_app.get("/health", status_code=status.HTTP_200_OK, tags=["system"])
def redflag_health():
    return {"status": "ok", "service": "redflag", "port": 8105}


# Mount red-flag routes under /api/v1
redflag_app.include_router(redflag_router, prefix="/api/v1")
