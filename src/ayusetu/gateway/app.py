"""
AyuSetu API Gateway Application
================================
Entry point for the API Gateway service running on port 8080 per PRD v2.0 §22.2.
Enforces security perimeter, rate limiting, request validation, CORS, and error taxonomy.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ayusetu.common.config import settings
from ayusetu.common.structured_logging import configure_structured_logging
from ayusetu.gateway.middleware.request_id import RequestIDMiddleware
from ayusetu.gateway.middleware.security_headers import SecurityHeadersMiddleware
from ayusetu.gateway.middleware.body_size_limit import BodySizeLimitMiddleware
from ayusetu.gateway.middleware.rate_limit import RateLimitMiddleware
from ayusetu.gateway.middleware.access_log import AccessLogMiddleware
from ayusetu.gateway.middleware.error_handler import register_error_handlers
from ayusetu.gateway.routes.health import router as health_router
from ayusetu.gateway.routes.metrics import router as metrics_router
from ayusetu.gateway.routes.v1_router import v1_router


def create_gateway_app() -> FastAPI:
    """Factory creating configured API Gateway FastAPI application."""
    configure_structured_logging(service_name="ayusetu-gateway", use_json=(settings.AYUSETU_ENV == "prod"))

    app = FastAPI(
        title="AyuSetu API Gateway",
        description="AyuSetu Clinical Intake & Security Perimeter Gateway",
        version="2.0.0",
        docs_url="/docs" if settings.DEBUG or settings.AYUSETU_ENV == "dev" else None,
        redoc_url="/redoc" if settings.DEBUG or settings.AYUSETU_ENV == "dev" else None,
    )

    # 1. Register Error Handlers (PRD §22.8 Taxonomy)
    register_error_handlers(app)

    # 2. Add Middlewares in explicit security pipeline order
    app.add_middleware(RateLimitMiddleware)
    
    # Strict CORS configuration per PRD §21.6 (No wildcard allowed with credentials)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # 3. Mount Routers
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(v1_router)

    @app.get("/")
    def root():
        return {
            "service": "AyuSetu API Gateway",
            "version": "2.0.0",
            "status": "active",
            "port": settings.GATEWAY_PORT,
            "prefix": "/api/v1"
        }

    return app


gateway_app = create_gateway_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "ayusetu.gateway.app:gateway_app",
        host=settings.GATEWAY_HOST,
        port=settings.GATEWAY_PORT,
        reload=settings.DEBUG,
    )
