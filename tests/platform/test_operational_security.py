"""
Tests for Operational Security, Health, Readiness, and Runtime Hardening
========================================================================
Validates:
- /health and /live non-leaking liveness probes.
- /ready and /api/v1/health active dependency validation (PostgreSQL + Redis).
- 503 fail-closed behavior when dependencies are unreachable.
- Production configuration fail-closed validation (DEBUG=True, default credentials, wildcard CORS, invalid TTLs).
- Error pipeline sanitization (Zero stack traces or SQL details in 500 responses).
"""

from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from ayusetu.common.config import Settings
from ayusetu.gateway.app import gateway_app

client = TestClient(gateway_app)


def test_liveness_probes():
    """Verify lightweight liveness probes (/health and /live) return 200 OK without leaking secrets."""
    for endpoint in ("/health", "/live"):
        res = client.get(endpoint)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "ayusetu-gateway"
        # Zero secret strings
        assert "password" not in res.text
        assert "postgresql://" not in res.text
        assert "redis://" not in res.text


def test_readiness_probe_healthy():
    """Verify readiness returns 200 and 'ready' status when dependencies are reachable."""
    with patch("ayusetu.gateway.routes.health.SyncSessionLocal"), \
         patch("ayusetu.gateway.routes.health.ping_redis", return_value=True):
        res = client.get("/ready")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["components"]["database"] == "connected"
        assert data["components"]["redis"] == "connected"
        assert "ayusetu_dev_secret" not in res.text


def test_readiness_probe_database_down_fails_closed():
    """Verify readiness returns 503 and 'degraded' when database is unreachable."""
    with patch("ayusetu.gateway.routes.health.SyncSessionLocal", side_effect=Exception("DB Connection Timeout")), \
         patch("ayusetu.gateway.routes.health.ping_redis", return_value=True):
        res = client.get("/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"] == "unreachable"
        assert data["components"]["redis"] == "connected"
        # Ensure raw DB connection error / password is not exposed
        assert "DB Connection Timeout" not in res.text
        assert "password" not in res.text


def test_readiness_probe_redis_down_fails_closed():
    """Verify readiness returns 503 and 'degraded' when Redis is unreachable."""
    with patch("ayusetu.gateway.routes.health.SyncSessionLocal"), \
         patch("ayusetu.gateway.routes.health.ping_redis", return_value=False):
        res = client.get("/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"] == "connected"
        assert data["components"]["redis"] == "unreachable"


def test_production_config_debug_fails_closed():
    """Verify production startup fails closed if DEBUG is True."""
    with pytest.raises(ValueError, match="DEBUG mode must be False in production"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=True,
            DATABASE_URL="postgresql+psycopg2://admin:super_secret_pw@10.0.0.1:5432/ayusetu_db",
            REDIS_URL="redis://10.0.0.2:6379/0",
            CORS_ALLOWED_ORIGINS=["https://ayusetu.hospital.gov.in"],
        )


def test_production_config_default_password_fails_closed():
    """Verify production startup fails closed if default dev database password is used."""
    with pytest.raises(ValueError, match="Default development database password 'ayusetu_dev_secret' is forbidden in production"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg2://ayusetu:ayusetu_dev_secret@localhost:5432/ayusetu_db",
            REDIS_URL="redis://10.0.0.2:6379/0",
            CORS_ALLOWED_ORIGINS=["https://ayusetu.hospital.gov.in"],
        )


def test_production_config_wildcard_cors_fails_closed():
    """Verify production startup fails closed if wildcard CORS origin is specified."""
    with pytest.raises(ValueError, match="Wildcard CORS origins are forbidden in production"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg2://admin:secure_prod_password@10.0.0.1:5432/ayusetu_db",
            REDIS_URL="redis://10.0.0.2:6379/0",
            CORS_ALLOWED_ORIGINS=["*"],
        )


def test_production_config_invalid_session_ttl_fails_closed():
    """Verify production startup fails closed if SESSION_TTL_MINUTES is invalid."""
    with pytest.raises(ValueError, match="SESSION_TTL_MINUTES must be between 1 and 120 minutes"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg2://admin:secure_prod_password@10.0.0.1:5432/ayusetu_db",
            REDIS_URL="redis://10.0.0.2:6379/0",
            SESSION_TTL_MINUTES=180,
            CORS_ALLOWED_ORIGINS=["https://ayusetu.hospital.gov.in"],
        )


def test_production_config_non_postgres_fails_closed():
    """Verify production startup fails closed if non-PostgreSQL DB is configured."""
    with pytest.raises(ValueError, match="PostgreSQL is mandatory in production environment"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=False,
            DATABASE_URL="sqlite:///./ayusetu.db",
            REDIS_URL="redis://10.0.0.2:6379/0",
            CORS_ALLOWED_ORIGINS=["https://ayusetu.hospital.gov.in"],
        )


def test_unhandled_exception_sanitization():
    """Verify unhandled exceptions return safe 500 error envelope with correlation ID and no stack trace."""
    with patch("ayusetu.gateway.routes.health.SyncSessionLocal", side_effect=RuntimeError("Fatal DB crash: select * from internal_users where pwd='123'")), \
         patch("ayusetu.gateway.routes.health.ping_redis", side_effect=RuntimeError("Fatal Redis crash: redis://admin:super_secret@host:6379")):
        # We invoke an unhandled exception inside a testable endpoint
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from ayusetu.gateway.middleware.error_handler import register_error_handlers
        from ayusetu.gateway.middleware.request_id import RequestIDMiddleware

        test_app = FastAPI()
        register_error_handlers(test_app)
        test_app.add_middleware(RequestIDMiddleware)

        @test_app.get("/trigger-crash")
        def crash_route():
            raise RuntimeError("Secret DB Error: SELECT * FROM patient_records WHERE password='super_secret_pw'")

        c = TestClient(test_app)
        res = c.get("/trigger-crash")
        assert res.status_code == 500
        data = res.json()
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert "patient_records" not in res.text
        assert "super_secret_pw" not in res.text
        assert "Traceback" not in res.text
        assert "request_id" in data["error"]
