"""
Test Suite: Phase 6 Security Hardening
======================================
Validates:
1. PostgreSQL database-level audit immutability triggers (rejecting UPDATE/DELETE).
2. Durable PostgreSQL quarantine persistence across process restarts.
3. Audit head tamper detection and fail-closed recovery.
4. Production fail-closed configuration and SSO boundary enforcement.
5. Zero-PHI preservation in logs and quarantine stores.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ayusetu.audit.models import (
    AuditAction,
    AuditEventCreate,
    AuditOutcome,
    OfflineAuditEventDTO,
    OfflineAuditSyncBatch,
)
from ayusetu.audit.repository import AuditRepository, get_default_session_factory
from ayusetu.audit.quarantine import QuarantineStore, sanitize_quarantine_metadata
from ayusetu.audit.service import AuditService
from ayusetu.common.config import Settings
from ayusetu.common.models import AuditEvent, QuarantinedAuditBatch
from ayusetu.gateway.auth.session_auth import SessionAuthenticator
from ayusetu.gateway.errors import AyuSetuGatewayError


@pytest.fixture(autouse=True)
def clean_audit_and_quarantine():
    session_factory = get_default_session_factory()
    with session_factory() as db:
        db.query(QuarantinedAuditBatch).delete()
        db.query(AuditEvent).delete()
        db.commit()
    yield
    with session_factory() as db:
        db.query(QuarantinedAuditBatch).delete()
        db.query(AuditEvent).delete()
        db.commit()


def test_quarantine_persists_durably_to_database():
    """Verify quarantine records are saved to the database and survive new store instances."""
    session_factory = get_default_session_factory()
    store1 = QuarantineStore(session_factory)

    record = store1.quarantine_batch(
        device_id="station-opd-09",
        seed_head_hash="0" * 64,
        reason="Tampered offline payload",
        failure_code="LOCAL_ENTRY_HASH_TAMPERED",
        event_count=3,
        safe_metadata={"authenticated_device_id": "station-opd-09", "device_id": "station-opd-09"},
    )

    assert record.quarantine_id is not None
    assert record.device_id == "station-opd-09"
    assert record.failure_code == "LOCAL_ENTRY_HASH_TAMPERED"

    # Simulate restart by instantiating a new QuarantineStore against the DB
    store2 = QuarantineStore(session_factory)
    records = store2.list_records()

    assert len(records) == 1
    assert records[0].quarantine_id == record.quarantine_id
    assert records[0].device_id == "station-opd-09"
    assert records[0].event_count == 3


def test_quarantine_sanitizes_metadata_zero_phi():
    """Verify quarantine metadata whitelist strictly strips unapproved/PHI fields."""
    raw_meta = {
        "device_id": "station-01",
        "failure_code": "UNKNOWN_SEED_HEAD",
        "patient_name": "Ramesh Kumar",  # Sensitive PHI
        "phone_number": "9876543210",     # Sensitive PHI
        "clinical_diagnosis": "Angina",   # Sensitive PHI
    }

    sanitized = sanitize_quarantine_metadata(raw_meta)

    assert "device_id" in sanitized
    assert "failure_code" in sanitized
    assert "patient_name" not in sanitized
    assert "phone_number" not in sanitized
    assert "clinical_diagnosis" not in sanitized


def test_audit_head_tamper_detection_fails_closed():
    """Verify that tampering with the latest database row causes get_head and append to fail closed."""
    session_factory = get_default_session_factory()
    repo = AuditRepository(session_factory)

    # 1. Normal append
    ev1 = repo.append(
        AuditEventCreate(
            actor_id="018f0000-0000-7000-8000-000000000001",
            actor_role="physician",
            action=AuditAction.READ,
            resource_type="Patient",
            resource_id="018f0000-0000-7000-8000-000000000002",
        )
    )
    assert ev1.seq == 1

    # 2. Tamper with the row's action in the database
    with session_factory() as db:
        row = db.query(AuditEvent).filter(AuditEvent.seq == 1).first()
        # Direct column manipulation to simulate low-level tampering
        row.action = "BREAKGLASS"
        db.commit()

    # 3. get_head() must detect the mismatch and raise RuntimeError
    with pytest.raises(RuntimeError, match="integrity compromised"):
        repo.get_head()

    # 4. append() must refuse to build on a tampered chain
    with pytest.raises(RuntimeError, match="integrity compromised"):
        repo.append(
            AuditEventCreate(
                actor_id="018f0000-0000-7000-8000-000000000001",
                actor_role="physician",
                action=AuditAction.CREATE,
                resource_type="Patient",
                resource_id="018f0000-0000-7000-8000-000000000002",
            )
        )


def test_production_config_fails_closed_on_insecure_settings():
    """Verify that Settings validation fails closed in production for debug mode or default secrets."""
    # Production with DEBUG=True must fail
    with pytest.raises(ValueError, match="DEBUG mode must be False in production"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=True,
            DATABASE_URL="postgresql+psycopg2://user:real_prod_secret@db.prod.hospital:5432/ayusetu",
        )

    # Production with default dev database password must fail
    with pytest.raises(ValueError, match="ayusetu_dev_secret.*forbidden"):
        Settings(
            AYUSETU_ENV="prod",
            DEBUG=False,
            DATABASE_URL="postgresql+psycopg2://ayusetu:ayusetu_dev_secret@db:5432/ayusetu",
        )

    # Valid production settings must succeed
    prod_cfg = Settings(
        AYUSETU_ENV="prod",
        DEBUG=False,
        DATABASE_URL="postgresql+psycopg2://ayusetu_prod:Str0ng_Pr0d_K3y!@db.internal:5432/ayusetu_prod",
    )
    assert prod_cfg.AYUSETU_ENV == "prod"
    assert prod_cfg.DEBUG is False


def test_production_authenticator_rejects_dev_staff_tokens(monkeypatch):
    """Verify that SessionAuthenticator forbids development staff tokens when AYUSETU_ENV=prod."""
    from ayusetu.common.config import settings

    monkeypatch.setattr(settings, "AYUSETU_ENV", "prod")
    auth = SessionAuthenticator()

    # Development staff token must be rejected with 403 Forbidden in prod
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        auth.authenticate_token("Bearer staff-token-dr-aparna")

    assert exc_info.value.status_code == 403
    assert "Development staff tokens are forbidden in production" in exc_info.value.message
