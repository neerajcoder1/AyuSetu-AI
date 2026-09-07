"""
Test Suite: Configuration Management
====================================
Validates settings parsing, defaults, and PRD v2.0 parameters.
"""

import pytest
from ayusetu.common.config import Settings


def test_default_config():
    cfg = Settings(
        DATABASE_URL="postgresql+psycopg2://test:pass@localhost:5432/testdb",
        REDIS_URL="redis://localhost:6379/1"
    )
    assert cfg.AYUSETU_ENV in ["dev", "pilot", "prod"]
    assert cfg.SESSION_TTL_MINUTES == 30
    assert cfg.QUESTION_BUDGET == 40
    assert cfg.INTERVIEW_BUDGET_SECONDS == 480
    assert cfg.ASR_CONFIDENCE_FLOOR == 0.65
    assert cfg.OCR_CONFIDENCE_AMBER == 0.80
    assert cfg.STUCK_DETECT_SECONDS == 45
    assert cfg.TIER1_ESCALATE_SECONDS == 90
    assert cfg.TIER1_ESCALATE2_SECONDS == 180
    assert cfg.COMPANION_LINK_TTL_MINUTES == 60


def test_async_db_url_conversion():
    cfg = Settings(DATABASE_URL="postgresql+psycopg2://user:pass@db:5432/ayusetu")
    assert cfg.async_db_url == "postgresql+asyncpg://user:pass@db:5432/ayusetu"

    cfg_sqlite = Settings(DATABASE_URL="sqlite:///test.db")
    assert cfg_sqlite.async_db_url == "sqlite+aiosqlite:///test.db"
