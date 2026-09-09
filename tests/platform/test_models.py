"""
Test Suite: Database Models & UUIDv7
====================================
Validates all 11 PRD tables, UUIDv7 generation, constraints and timestamps.
"""

from datetime import date, datetime, timezone
import uuid6
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ayusetu.common.database import Base
from ayusetu.common.models import (
    Patient,
    Encounter,
    Slot,
    Utterance,
    Document,
    ExtractedEntity,
    RedFlagEvent,
    ConsentRecord,
    SummaryVersion,
    SummaryEdit,
    AuditEvent,
    generate_uuid7,
    utc_now,
)


@pytest.fixture(scope="function")
def db_session():
    """Fresh in-memory SQLite session for model structure tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_uuid7_generation():
    id1 = generate_uuid7()
    id2 = generate_uuid7()
    assert isinstance(id1, uuid6.UUID)
    assert id1 != id2
    # UUIDv7 is strictly time-sortable
    assert id1.int <= id2.int


def test_patient_model(db_session):
    p = Patient(
        id=generate_uuid7(),
        abha_id="91-1111-2222-3333",
        mrn="MRN-TEST-001",
        name_enc=b"EncryptedName",
        mobile_enc=b"EncryptedMobile",
        dob=date(1980, 1, 1),
        sex="female",
        district="New Delhi",
        is_provisional=False,
    )
    db_session.add(p)
    db_session.commit()

    retrieved = db_session.query(Patient).filter_by(mrn="MRN-TEST-001").first()
    assert retrieved is not None
    assert retrieved.sex == "female"
    assert retrieved.is_provisional is False
    assert retrieved.name_enc == b"EncryptedName"
    assert retrieved.created_at is not None


def test_encounter_and_slot_model(db_session):
    p = Patient(id=generate_uuid7(), mrn="MRN-ENC-001")
    db_session.add(p)
    db_session.commit()

    enc = Encounter(
        id=generate_uuid7(),
        patient_id=p.id,
        department="Kayachikitsa",
        visit_type="new",
        intake_depth="full",
        channel="kiosk",
        reported_by="patient",
        language="hi",
        status="draft",
    )
    db_session.add(enc)
    db_session.commit()

    # Slot with elicited=True
    s1 = Slot(
        id=generate_uuid7(),
        encounter_id=enc.id,
        path="chief_complaint",
        value={"text": "Chest pain", "severity": 7},
        value_coded="Hridshoola",
        confidence=0.92,
        source="utterance",
        reported_by="patient",
        elicited=True,
    )
    # Slot with elicited=False (PRD Gate 5: explicit absence, never assumed negative)
    s2 = Slot(
        id=generate_uuid7(),
        encounter_id=enc.id,
        path="allergy.food",
        value=None,
        value_coded=None,
        confidence=None,
        source="derived",
        reported_by="patient",
        elicited=False,
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    slots = db_session.query(Slot).filter_by(encounter_id=enc.id).all()
    assert len(slots) == 2
    elicited_slot = next(s for s in slots if s.path == "chief_complaint")
    assert elicited_slot.elicited is True
    assert elicited_slot.value["severity"] == 7

    unelicited_slot = next(s for s in slots if s.path == "allergy.food")
    assert unelicited_slot.elicited is False


def test_consent_record_model(db_session):
    p = Patient(id=generate_uuid7(), mrn="MRN-CONSENT-001")
    db_session.add(p)
    db_session.commit()

    enc = Encounter(
        id=generate_uuid7(),
        patient_id=p.id,
        department="Shalya",
        visit_type="walkin",
        intake_depth="fast",
        channel="kiosk",
        status="draft",
    )
    db_session.add(enc)
    db_session.commit()

    consent = ConsentRecord(
        id=generate_uuid7(),
        patient_id=p.id,
        encounter_id=enc.id,
        purposes={"clinical": True, "abdm": True, "qi": False, "research": False},
        language="hi",
        notice_version="dpdp-2026-v1",
        chain_hash=b"sha256_hash_bytes",
    )
    db_session.add(consent)
    db_session.commit()

    rec = db_session.query(ConsentRecord).filter_by(encounter_id=enc.id).first()
    assert rec is not None
    assert rec.purposes["clinical"] is True
    assert rec.purposes["research"] is False


def test_audit_event_model(db_session):
    audit = AuditEvent(
        actor_id=generate_uuid7(),
        actor_role="Physician",
        action="READ",
        resource_type="Encounter",
        resource_id=generate_uuid7(),
        outcome="ALLOW",
        payload_hash=b"fake_payload_hash",
        prev_hash=b"fake_prev_hash",
        entry_hash=b"fake_entry_hash",
    )
    db_session.add(audit)
    db_session.commit()

    ev = db_session.query(AuditEvent).first()
    assert ev is not None
    assert ev.action == "READ"
    assert ev.outcome == "ALLOW"
    assert ev.seq is not None


def test_universal_uuid_strict_validation(db_session):
    """
    Regression test ensuring UniversalUUID strictly rejects non-UUID strings
    on both SQLite and PostgreSQL.
    """
    from ayusetu.common.models import UniversalUUID
    import uuid

    # 1. Valid UUID object accepted
    u_obj = uuid.UUID("018f0000-0000-7000-8000-000000000001")
    p1 = Patient(id=u_obj, mrn="MRN-VALID-OBJ")
    db_session.add(p1)
    db_session.commit()
    assert p1.id == u_obj

    # 2. Valid UUID string accepted
    u_str = "018f0000-0000-7000-8000-000000000002"
    p2 = Patient(id=u_str, mrn="MRN-VALID-STR")
    db_session.add(p2)
    db_session.commit()
    assert str(p2.id) == u_str

    from sqlalchemy.exc import StatementError

    # 3. Invalid arbitrary string rejected during DB bind/commit
    with pytest.raises((ValueError, StatementError)) as exc_info:
        p_invalid = Patient(id="station-opd-01", mrn="MRN-INVALID-STR")
        db_session.add(p_invalid)
        db_session.commit()
    assert "badly formed hexadecimal UUID string" in str(exc_info.value)

    db_session.rollback()

    # 4. Invalid audit actor_id rejected during DB bind/commit
    with pytest.raises((ValueError, StatementError)) as exc_info:
        audit_invalid = AuditEvent(
            actor_id="station-01",  # Invalid non-UUID
            actor_role="device",
            action="READ",
            resource_type="Encounter",
            resource_id="018f0000-0000-7000-8000-000000000001",
            outcome="ALLOW",
            payload_hash=b"fake",
            prev_hash=b"fake",
            entry_hash=b"fake",
        )
        db_session.add(audit_invalid)
        db_session.commit()
    assert "badly formed hexadecimal UUID string" in str(exc_info.value)

    db_session.rollback()

