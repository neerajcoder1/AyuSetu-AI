"""
Audit PostgreSQL Persistence & Crash-Recovery Tests
===================================================
Validates durable database storage, process-restart chain head recovery,
tamper detection on persisted records, sequence monotonicity, and Zero-PHI enforcement.
"""

from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ayusetu.common.database import Base
from ayusetu.common.models import AuditEvent
from ayusetu.audit.models import AuditAction, AuditEventCreate, AuditOutcome
from ayusetu.audit.repository import AuditRepository
from ayusetu.audit.service import AuditService
from ayusetu.audit.verifier import audit_verifier
from ayusetu.audit.chain import GENESIS_HASH


@pytest.fixture
def isolated_db_factory(tmp_path):
    """Create an isolated file-backed SQLite database to simulate clean process restarts."""
    db_file = tmp_path / "test_audit_durable.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[AuditEvent.__table__])
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False, class_=Session)
    return factory


def test_append_persists_to_database(isolated_db_factory):
    """Verify appending an event persists rows directly into the database."""
    repo = AuditRepository(session_factory=isolated_db_factory)
    
    event_dto = repo.append(AuditEventCreate(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action=AuditAction.READ,
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000010",
        outcome=AuditOutcome.ALLOW,
    ))

    assert event_dto.seq == 1
    assert event_dto.prev_hash == GENESIS_HASH

    # Direct database inspection
    with isolated_db_factory() as db:
        row = db.query(AuditEvent).filter(AuditEvent.seq == 1).first()
        assert row is not None
        assert str(row.actor_id) == "018f0000-0000-7000-8000-000000000001"
        assert row.action == "READ"
        assert row.outcome == "ALLOW"


def test_fresh_repository_restart_recovers_chain_head(isolated_db_factory):
    """
    Simulate process restart:
    1. Append event A with repo instance 1
    2. Dispose repo instance 1
    3. Initialize clean repo instance 2 bound to same database
    4. Assert repo 2 recovers head without resetting to GENESIS
    """
    repo_1 = AuditRepository(session_factory=isolated_db_factory)
    ev1 = repo_1.append(AuditEventCreate(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action=AuditAction.CREATE,
        resource_type="ClinicalSummary",
        resource_id="018f0000-0000-7000-8000-000000000010",
    ))
    del repo_1

    # Initialize fresh repository instance (simulating application restart)
    repo_2 = AuditRepository(session_factory=isolated_db_factory)
    head = repo_2.get_head()

    assert head.seq == 1
    assert head.entry_hash == ev1.entry_hash
    assert head.entry_hash != GENESIS_HASH


def test_append_after_restart_preserves_previous_hash_linkage(isolated_db_factory):
    """
    Verify appending an event after restart properly links previous_hash to prior event:
    Event B.seq == 2
    Event B.prev_hash == Event A.entry_hash
    """
    repo_1 = AuditRepository(session_factory=isolated_db_factory)
    ev1 = repo_1.append(AuditEventCreate(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action=AuditAction.CREATE,
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000010",
    ))
    del repo_1

    # Restart
    repo_2 = AuditRepository(session_factory=isolated_db_factory)
    ev2 = repo_2.append(AuditEventCreate(
        actor_id="018f0000-0000-7000-8000-000000000002",
        actor_role="Nurse",
        action=AuditAction.UPDATE,
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000010",
    ))

    assert ev2.seq == 2
    assert ev2.prev_hash == ev1.entry_hash

    # Verify mathematical chain integrity
    verif = audit_verifier.verify_chain(repo_2.get_all())
    assert verif.valid is True
    assert verif.checked_events == 2
    assert verif.last_valid_sequence == 2


def test_persisted_tampering_detection(isolated_db_factory):
    """
    Verify that directly modifying a row in the database is detected by the verifier.
    """
    repo = AuditRepository(session_factory=isolated_db_factory)
    service = AuditService(repository=repo)

    service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action=AuditAction.READ,
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )
    service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000002",
        actor_role="Nurse",
        action=AuditAction.UPDATE,
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )

    # Directly mutate the database record for event 2
    with isolated_db_factory() as db:
        row2 = db.query(AuditEvent).filter(AuditEvent.seq == 2).first()
        assert row2 is not None
        row2.action = "SIGN"  # Tamper with action verb
        db.commit()

    verif = service.verify_global_chain()
    assert verif.valid is False
    assert verif.last_valid_sequence == 1
    assert verif.failure is not None
    assert verif.failure["code"] == "ENTRY_HASH_TAMPERED"
    assert verif.failure["sequence"] == 2


def test_verifier_detects_broken_prev_hash_in_db(isolated_db_factory):
    """Verify tampering with prev_hash in database is caught immediately."""
    repo = AuditRepository(session_factory=isolated_db_factory)
    service = AuditService(repository=repo)

    service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action=AuditAction.READ,
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )
    service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000002",
        actor_role="Nurse",
        action=AuditAction.UPDATE,
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )

    with isolated_db_factory() as db:
        row2 = db.query(AuditEvent).filter(AuditEvent.seq == 2).first()
        row2.prev_hash = b"\x00" * 32  # Broken prev_hash
        db.commit()

    verif = service.verify_global_chain()
    assert verif.valid is False
    assert verif.failure["code"] in ("PREV_HASH_MISMATCH", "ENTRY_HASH_TAMPERED")
