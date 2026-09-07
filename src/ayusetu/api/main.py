"""
AyuSetu Backend Application Entry Point
========================================
Main FastAPI application for platform services.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ayusetu.common.config import settings
from ayusetu.api.health import router as health_router

app = FastAPI(
    title="AyuSetu Backend Platform",
    description="AyuSetu Clinical Intake & Platform Foundation",
    version="2.0.0",
    docs_url="/docs" if settings.DEBUG or settings.AYUSETU_ENV == "dev" else None,
    redoc_url="/redoc" if settings.DEBUG or settings.AYUSETU_ENV == "dev" else None,
)

# CORS configuration per PRD §21.6 (strict origin policy, no wildcard with credentials)
origins = ["http://localhost:3000", "http://localhost:5173"]
if settings.AYUSETU_ENV == "dev":
    origins.append("http://127.0.0.1:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include Health & System Routers
app.include_router(health_router)


@app.get("/")
def root():
    return {
        "service": "AyuSetu Platform API",
        "version": "2.0.0",
        "status": "running"
    }
