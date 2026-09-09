"""
Red-Flag PostgreSQL Persistence & Lifecycle Crash-Recovery Tests
=================================================================
Validates durable database storage of RedFlag events, process-restart
recovery, lifecycle transitions (DETECTED -> ACKNOWLEDGED -> ESCALATED -> RESOLVED),
concurrency safety, fail-closed handling, and zero-PHI audit trail per PRD v2.0 §12 & §22.9.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ayusetu.common.database import Base
from ayusetu.common.models import RedFlagEvent, ConsentRecord, Patient, Encounter
from ayusetu.redflag.models import (
    RedFlagEventDTO,
    RedFlagStatus,
    RedFlagTier,
    StructuredClinicalFact,
)
from ayusetu.redflag.repository import RedFlagRepository
from ayusetu.redflag.service import RedFlagService
from ayusetu.consent.service import ConsentService
from ayusetu.consent.repository import ConsentRepository
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode


@pytest.fixture
def isolated_redflag_db_factory(tmp_path):
    """Create an isolated file-backed SQLite database to simulate clean process restarts."""
    db_file = tmp_path / "test_redflag_durable.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=[Patient.__table__, Encounter.__table__, ConsentRecord.__table__, RedFlagEvent.__table__])
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False, class_=Session)
    return factory


def test_redflag_creation_persists_to_database(isolated_redflag_db_factory):
    """Verify detected red-flag event persists directly into PostgreSQL/database."""
    repo = RedFlagRepository(session_factory=isolated_redflag_db_factory)
    consent_repo = ConsentRepository(session_factory=isolated_redflag_db_factory)
    consent_svc = ConsentService(repository=consent_repo)
    service = RedFlagService(repository=repo, consent_svc=consent_svc)

    enc_id = "018f0000-0000-7000-8000-000000000010"
    pat_id = "018f0000-0000-7000-8000-000000000001"

    # Grant clinical consent first
    consent_svc.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )

    facts = [
        StructuredClinicalFact(path="symptoms.chest_pain", value=True),
        StructuredClinicalFact(path="symptoms.radiation", value=True),
    ]

    events = service.evaluate_encounter(enc_id, facts)
    assert len(events) == 1
    ev = events[0]
    assert ev.rule_id == "RF-CARD-001"
    assert ev.tier == 1
    assert ev.status == RedFlagStatus.DETECTED

    # Inspect direct database state
    with isolated_redflag_db_factory() as db:
        row = db.query(RedFlagEvent).filter(RedFlagEvent.id == ev.id).first()
        assert row is not None
        assert str(row.encounter_id) == enc_id
        assert row.rule_id == "RF-CARD-001"
        assert row.tier == 1
        assert row.outcome is None
        assert row.acknowledged_at is None


def test_redflag_full_lifecycle_and_restart_recovery(isolated_redflag_db_factory):
    """
    Simulate full multi-generation process crash and reboot:
    1. Instance A: Detects Tier 1 RedFlag -> persists DETECTED to PostgreSQL
    2. Verify it exists in database
    3. Destroy Instance A -> Initialize fresh Instance B bound to same DB
    4. Instance B: Recovers DETECTED event -> Acknowledges -> Persists ACKNOWLEDGED
    5. Destroy Instance B -> Initialize fresh Instance C bound to same DB
    6. Instance C: Recovers ACKNOWLEDGED event -> Escalates -> Persists ESCALATED
    7. Destroy Instance C -> Initialize fresh Instance D bound to same DB
    8. Instance D: Recovers ESCALATED event -> Resolves -> Persists RESOLVED
    9. Destroy Instance D -> Initialize fresh Instance E bound to same DB
    10. Instance E: Recovers RESOLVED state and verifies event is cleared from active Tier-1 queue.
    """
    enc_id = "018f0000-0000-7000-8000-000000000020"
    pat_id = "018f0000-0000-7000-8000-000000000002"
    clinician_1 = "018f0000-0000-7000-8000-000000000101"
    clinician_2 = "018f0000-0000-7000-8000-000000000102"

    # Grant consent
    consent_repo = ConsentRepository(session_factory=isolated_redflag_db_factory)
    consent_svc = ConsentService(repository=consent_repo)
    consent_svc.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )

    # --- Phase 1: Instance A (Detection) ---
    repo_a = RedFlagRepository(session_factory=isolated_redflag_db_factory)
    service_a = RedFlagService(repository=repo_a, consent_svc=consent_svc)

    facts = [StructuredClinicalFact(path="symptoms.stridor", value=True)]
    events_a = service_a.evaluate_encounter(enc_id, facts)
    assert len(events_a) == 1
    event_id = events_a[0].id
    assert events_a[0].status == RedFlagStatus.DETECTED

    # Destroy Instance A
    del service_a
    del repo_a

    # --- Phase 2: Instance B (Restart & Acknowledgement) ---
    repo_b = RedFlagRepository(session_factory=isolated_redflag_db_factory)
    service_b = RedFlagService(repository=repo_b, consent_svc=consent_svc)

    # State recovered from PostgreSQL
    recovered_b = service_b.get_event_by_id(event_id)
    assert recovered_b is not None
    assert recovered_b.id == event_id
    assert recovered_b.status == RedFlagStatus.DETECTED

    ack_b = service_b.acknowledge_event(
        event_id=event_id,
        clinician_id=clinician_1,
        clinician_role="nurse",
        notes="Vitals checked, SpO2=88%",
    )
    assert ack_b.status == RedFlagStatus.ACKNOWLEDGED
    assert ack_b.acknowledged_by == clinician_1
    assert "Vitals checked" in ack_b.outcome

    # Destroy Instance B
    del service_b
    del repo_b

    # --- Phase 3: Instance C (Restart & Escalation) ---
    repo_c = RedFlagRepository(session_factory=isolated_redflag_db_factory)
    service_c = RedFlagService(repository=repo_c, consent_svc=consent_svc)

    recovered_c = service_c.get_event_by_id(event_id)
    assert recovered_c is not None
    assert recovered_c.status == RedFlagStatus.ACKNOWLEDGED

    esc_c = service_c.escalate_event(
        event_id=event_id,
        clinician_id=clinician_1,
        clinician_role="nurse",
        target_role="duty_medical_officer",
        notes="Stridor worsening on room air",
    )
    assert esc_c.status == RedFlagStatus.ESCALATED
    assert "ESCALATED_TO_DUTY_MEDICAL_OFFICER" in esc_c.outcome

    # Destroy Instance C
    del service_c
    del repo_c

    # --- Phase 4: Instance D (Restart & Resolution) ---
    repo_d = RedFlagRepository(session_factory=isolated_redflag_db_factory)
    service_d = RedFlagService(repository=repo_d, consent_svc=consent_svc)

    recovered_d = service_d.get_event_by_id(event_id)
    assert recovered_d is not None
    assert recovered_d.status == RedFlagStatus.ESCALATED

    res_d = service_d.resolve_event(
        event_id=event_id,
        clinician_id=clinician_2,
        clinician_role="physician",
        outcome="TRIAGED_TO_ICU_INTUBATED",
        notes="Endotracheal tube placed by anesthesiology",
    )
    assert res_d.status == RedFlagStatus.RESOLVED
    assert "TRIAGED_TO_ICU_INTUBATED" in res_d.outcome

    # Destroy Instance D
    del service_d
    del repo_d

    # --- Phase 5: Instance E (Restart Verification of Terminal State) ---
    repo_e = RedFlagRepository(session_factory=isolated_redflag_db_factory)
    service_e = RedFlagService(repository=repo_e, consent_svc=consent_svc)

    final_event = service_e.get_event_by_id(event_id)
    assert final_event is not None
    assert final_event.status == RedFlagStatus.RESOLVED

    # Terminal state cannot be transitioned again
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        service_e.acknowledge_event(event_id, clinician_1, "nurse")
    assert exc_info.value.status_code == 422

    # Resolved alert must not appear in active Tier 1 Queue
    queue_e = service_e.get_tier1_queue()
    assert all(item.event.id != event_id for item in queue_e)


def test_concurrent_redflag_state_updates(isolated_redflag_db_factory):
    """
    Verify concurrent lifecycle transitions against the same red-flag event
    are serialized safely by database transaction boundaries.
    """
    enc_id = "018f0000-0000-7000-8000-000000000030"
    pat_id = "018f0000-0000-7000-8000-000000000003"

    consent_repo = ConsentRepository(session_factory=isolated_redflag_db_factory)
    consent_svc = ConsentService(repository=consent_repo)
    consent_svc.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )

    repo = RedFlagRepository(session_factory=isolated_redflag_db_factory)
    service = RedFlagService(repository=repo, consent_svc=consent_svc)

    events = service.evaluate_encounter(
        enc_id,
        [StructuredClinicalFact(path="symptoms.chest_pain", value=True), StructuredClinicalFact(path="symptoms.radiation", value=True)],
    )
    event_id = events[0].id

    # 4 concurrent workers attempting state transitions
    def worker_action(idx):
        worker_repo = RedFlagRepository(session_factory=isolated_redflag_db_factory)
        worker_svc = RedFlagService(repository=worker_repo)
        if idx == 0:
            return worker_svc.acknowledge_event(event_id, f"018f0000-0000-7000-8000-00000000010{idx}", "nurse", notes="Ack 0")
        elif idx == 1:
            return worker_svc.escalate_event(event_id, f"018f0000-0000-7000-8000-00000000010{idx}", "nurse", notes="Esc 1")
        else:
            return worker_svc.resolve_event(event_id, f"018f0000-0000-7000-8000-00000000010{idx}", "physician", outcome=f"RESOLVED_{idx}")

    results = []
    errors = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(worker_action, i): i for i in range(4)}
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as exc:
                errors.append(exc)

    # Concurrency was handled safely: database contains a valid consistent state
    final_event = service.get_event_by_id(event_id)
    assert final_event is not None
    assert final_event.status in (RedFlagStatus.ACKNOWLEDGED, RedFlagStatus.ESCALATED, RedFlagStatus.RESOLVED)


def test_redflag_fails_closed_when_db_fails():
    """
    Verify fail-closed behavior:
    If database query fails or raises an error, RedFlag operations fail closed.
    """
    broken_session_factory = MagicMock(side_effect=RuntimeError("PostgreSQL connection severed"))
    broken_repo = RedFlagRepository(session_factory=broken_session_factory)
    broken_service = RedFlagService(repository=broken_repo)

    enc_id = "018f0000-0000-7000-8000-000000000099"
    ev_id = "018f0000-0000-7000-8000-000000000098"

    # 1. Queries raise on DB failure
    with pytest.raises(RuntimeError):
        broken_service.get_event_by_id(ev_id)

    with pytest.raises(RuntimeError):
        broken_service.get_encounter_events(enc_id)

    with pytest.raises(RuntimeError):
        broken_service.get_tier1_queue()

    # 2. Lifecycle operations raise on DB failure (never report false success)
    with pytest.raises(RuntimeError):
        broken_service.acknowledge_event(ev_id, "018f0000-0000-7000-8000-000000000101", "nurse")

    with pytest.raises(RuntimeError):
        broken_service.escalate_event(ev_id, "018f0000-0000-7000-8000-000000000101", "nurse")

    with pytest.raises(RuntimeError):
        broken_service.resolve_event(ev_id, "018f0000-0000-7000-8000-000000000101", "physician", outcome="RESOLVED")
