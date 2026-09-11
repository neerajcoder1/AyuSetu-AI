"""
Phase 9 Production Readiness: Configuration & Deployment Constraints
====================================================================
Validates all fail-closed rules of Settings under AYUSETU_ENV=prod.
"""

import pytest
from ayusetu.common.config import Settings


def test_production_config_valid():
    """Verify production settings pass validation when all security parameters are strict."""
    s = Settings(
        AYUSETU_ENV="prod",
        DEBUG=False,
        DATABASE_URL="postgresql+psycopg2://ayusetu_prod_user:K9#mQ!z8L2$wX7*p@prod-db.internal:5432/ayusetu_production",
        REDIS_URL="rediss://default:R9#zL1!kP7@prod-redis.internal:6379/0",
        CORS_ALLOWED_ORIGINS=["https://ayusetu.hospital.gov.in"],
        SESSION_TTL_MINUTES=30,
        RATE_LIMIT_DEVICE_RPM=60,
    )
    assert s.AYUSETU_ENV == "prod"
    assert s.DEBUG is False


def test_production_config_rejects_debug():
    """Verify DEBUG=True fails closed in production."""
    with pytest.raises(ValueError, match="DEBUG mode must be False in production"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=True,
            DATABASE_URL="postgresql+psycopg2://usr:K9#mQ!z8L2$wX7*p@prod-db.internal:5432/db",
            REDIS_URL="redis://prod-redis.internal:6379/0",
            CORS_ALLOWED_ORIGINS=["https://ayusetu.gov.in"],
        )


def test_production_config_rejects_insecure_database_password():
    """Verify default credentials fail closed in production."""
    with pytest.raises(ValueError, match="Default development database password 'ayusetu_dev_secret' is forbidden in production"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg2://ayusetu:ayusetu_dev_secret@prod-db.internal:5432/db",
            REDIS_URL="redis://prod-redis.internal:6379/0",
            CORS_ALLOWED_ORIGINS=["https://ayusetu.gov.in"],
        )


def test_production_config_rejects_wildcard_cors():
    """Verify wildcard CORS fails closed in production."""
    with pytest.raises(ValueError, match="Wildcard CORS origins are forbidden in production"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg2://usr:K9#mQ!z8L2$wX7*p@prod-db.internal:5432/db",
            REDIS_URL="redis://prod-redis.internal:6379/0",
            CORS_ALLOWED_ORIGINS=["*"],
        )


def test_production_config_rejects_non_postgres():
    """Verify SQLite database fails closed in production."""
    with pytest.raises(ValueError, match="PostgreSQL is mandatory in production environment"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=False,
            DATABASE_URL="sqlite:///./ayusetu.db",
            REDIS_URL="redis://prod-redis.internal:6379/0",
            CORS_ALLOWED_ORIGINS=["https://ayusetu.gov.in"],
        )


def test_production_config_rejects_invalid_session_ttl():
    """Verify TTL <= 0 or > 120 fails closed in production."""
    with pytest.raises(ValueError, match="SESSION_TTL_MINUTES must be between 1 and 120 minutes in production"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg2://usr:K9#mQ!z8L2$wX7*p@prod-db.internal:5432/db",
            REDIS_URL="redis://prod-redis.internal:6379/0",
            CORS_ALLOWED_ORIGINS=["https://ayusetu.gov.in"],
            SESSION_TTL_MINUTES=0,
        )
