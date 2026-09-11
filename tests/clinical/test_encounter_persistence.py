"""
Phase M7.1: Clinical Encounter & Slot Persistence Engine Tests
==============================================================
Validates authoritative PostgreSQL persistence for Encounter, Slot, and Utterance
models, state machine transitions, session submission, slot conflict resolution,
consent gating, RedFlag integration, and audit event logging.
"""

from datetime import datetime, timezone
import uuid
import uuid6
import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.common.session_cache import SessionCache
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.audit.service import audit_service
from ayusetu.clinical.models import (
    EncounterDTO,
    EncounterStatus,
    VisitType,
    IntakeDepth,
    Channel,
    ReportedBy,
    SlotSource,
    SlotDTO,
    UtteranceDTO,
)
from ayusetu.clinical.repository import ClinicalRepository
from ayusetu.clinical.service import ClinicalService, clinical_service

client = TestClient(gateway_app)


@pytest.fixture(autouse=True)
def clean_clinical_db():
    """Ensure clean clinical repository state before each test."""
    repo = ClinicalRepository()
    repo.clear_for_testing()
    yield
    repo.clear_for_testing()


def test_encounter_creation_and_retrieval():
    """Verify Encounter creation in draft state and retrieval by ID."""
    repo = ClinicalRepository()
    pat_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())

    enc_dto = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        department="Kayachikitsa",
        visit_type=VisitType.NEW,
        intake_depth=IntakeDepth.FULL,
        channel=Channel.KIOSK,
        reported_by=ReportedBy.PATIENT,
        status=EncounterStatus.DRAFT,
    )

    created = repo.create_encounter(enc_dto)
    assert created.id == enc_id
    assert created.patient_id == pat_id
    assert created.status == EncounterStatus.DRAFT

    retrieved = repo.get_encounter(enc_id)
    assert retrieved is not None
    assert retrieved.id == enc_id
    assert retrieved.department == "Kayachikitsa"
    assert retrieved.status == EncounterStatus.DRAFT


def test_encounter_state_machine_valid_transition():
    """Verify draft -> submitted transition updates status and submitted_at."""
    repo = ClinicalRepository()
    pat_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())

    enc_dto = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        status=EncounterStatus.DRAFT,
    )
    repo.create_encounter(enc_dto)

    updated = repo.update_encounter_status(enc_id, EncounterStatus.SUBMITTED)
    assert updated.status == EncounterStatus.SUBMITTED
    assert updated.submitted_at is not None


def test_encounter_state_machine_invalid_transition_rejected():
    """Verify invalid state transitions are rejected with ValueError."""
    repo = ClinicalRepository()
    pat_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())

    enc_dto = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        status=EncounterStatus.DRAFT,
    )
    repo.create_encounter(enc_dto)
    repo.update_encounter_status(enc_id, EncounterStatus.SUBMITTED)

    # Invalid: submitted -> draft is forbidden
    with pytest.raises(ValueError, match="Invalid encounter state transition"):
        repo.update_encounter_status(enc_id, EncounterStatus.DRAFT)


def test_utterance_persistence_and_ordering():
    """Verify utterances are persisted with sequence ordering preserved."""
    repo = ClinicalRepository()
    pat_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())

    enc_dto = EncounterDTO(id=enc_id, patient_id=pat_id)
    repo.create_encounter(enc_dto)

    u1 = UtteranceDTO(
        id=str(uuid6.uuid7()),
        encounter_id=enc_id,
        seq=1,
        speaker="patient",
        text="मुझे दो दिन से सीने में दर्द है",
        lang="hi",
        asr_confidence=0.95,
    )
    u2 = UtteranceDTO(
        id=str(uuid6.uuid7()),
        encounter_id=enc_id,
        seq=2,
        speaker="system",
        text="क्या आपको सांस लेने में तकलीफ भी है?",
        lang="hi",
        asr_confidence=1.0,
    )
    u3 = UtteranceDTO(
        id=str(uuid6.uuid7()),
        encounter_id=enc_id,
        seq=3,
        speaker="patient",
        text="हाँ, बहुत पसीना आ रहा है",
        lang="hi",
        asr_confidence=0.92,
    )

    repo.save_utterances(enc_id, [u2, u1, u3])  # Intentionally out of order

    retrieved = repo.get_utterances(enc_id)
    assert len(retrieved) == 3
    assert [u.seq for u in retrieved] == [1, 2, 3]
    assert retrieved[0].text == "मुझे दो दिन से सीने में दर्द है"
    assert retrieved[2].text == "हाँ, बहुत पसीना आ रहा है"


def test_slot_persistence_and_conflict_resolution():
    """Verify slot upsertion and deterministic conflict resolution on unique path."""
    repo = ClinicalRepository()
    pat_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())

    enc_dto = EncounterDTO(id=enc_id, patient_id=pat_id)
    repo.create_encounter(enc_dto)

    slot_initial = SlotDTO(
        id=str(uuid6.uuid7()),
        encounter_id=enc_id,
        path="hpi.chief_complaint",
        value="mild chest pain",
        confidence=0.85,
        source=SlotSource.UTTERANCE,
        reported_by=ReportedBy.PATIENT,
        elicited=True,
    )
    repo.upsert_slot(slot_initial)

    retrieved = repo.get_slot(enc_id, "hpi.chief_complaint")
    assert retrieved is not None
    assert retrieved.value == "mild chest pain"
    assert retrieved.confidence == 0.85

    # Conflict update: patient clarifies severe chest pain with radiation
    slot_update = SlotDTO(
        id=str(uuid6.uuid7()),
        encounter_id=enc_id,
        path="hpi.chief_complaint",
        value="severe retrosternal chest pain radiating to left arm",
        confidence=0.98,
        source=SlotSource.UTTERANCE,
        reported_by=ReportedBy.PATIENT,
        elicited=True,
    )
    repo.upsert_slot(slot_update)

    slots = repo.get_slots(enc_id)
    assert len(slots) == 1
    assert slots[0].value == "severe retrosternal chest pain radiating to left arm"
    assert slots[0].confidence == 0.98


def test_session_submission_full_workflow():
    """Verify session submission seals encounter, persists slots/utterances, and purges cache."""
    cache = SessionCache()
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())
    sess_id = f"sess-{enc_id}"

    # Setup session in cache
    session_data = cache.create_session(
        encounter_id=uuid.UUID(enc_id),
        patient_id=uuid.UUID(pat_id),
        channel="kiosk",
        session_id=sess_id,
    )
    cache.update_session(
        sess_id,
        {
            "status": "INTERVIEW",
            "department": "Kayachikitsa",
            "utterances": [
                {"seq": 1, "speaker": "patient", "text": "Fever for 3 days", "lang": "en", "asr_confidence": 0.96}
            ],
            "slots": {
                "hpi.chief_complaint": "Fever",
                "hpi.duration": "3 days",
            },
        },
    )

    # Grant clinical consent
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True, qi=False, research=False),
        )
    )

    # Submit session via service
    res = clinical_service.submit_session(
        session_id=sess_id,
        confirmed_by="patient",
        readback_accepted=True,
    )

    assert res.encounter_id == enc_id
    assert res.status == "submitted"
    assert res.session_purged is True
    assert res.slots_persisted == 2
    assert res.utterances_persisted == 1

    # Verify session cache is purged
    assert cache.get_session(sess_id) is None

    # Verify PostgreSQL records exist
    repo = ClinicalRepository()
    enc = repo.get_encounter(enc_id)
    assert enc is not None
    assert enc.status == EncounterStatus.SUBMITTED
    assert enc.submitted_at is not None

    slots = repo.get_slots(enc_id)
    assert len(slots) == 2
    slot_paths = {s.path for s in slots}
    assert "hpi.chief_complaint" in slot_paths
    assert "hpi.duration" in slot_paths

    utts = repo.get_utterances(enc_id)
    assert len(utts) == 1
    assert utts[0].text == "Fever for 3 days"


def test_session_submission_fails_closed_without_clinical_consent():
    """Verify session submission is rejected if clinical consent is not granted."""
    cache = SessionCache()
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())
    sess_id = f"sess-{enc_id}"

    cache.create_session(
        encounter_id=uuid.UUID(enc_id),
        patient_id=uuid.UUID(pat_id),
        session_id=sess_id,
    )

    # Grant consent with clinical=False
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=False, abdm=True, qi=False, research=False),
        )
    )

    from ayusetu.gateway.errors import AyuSetuGatewayError
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        clinical_service.submit_session(session_id=sess_id)

    assert exc_info.value.status_code == 403
    # Session cache should remain intact on failure
    assert cache.get_session(sess_id) is not None


def test_session_submission_triggers_redflag_evaluation():
    """Verify Tier 1 RedFlag trigger is evaluated and recorded on session submission."""
    cache = SessionCache()
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())
    sess_id = f"sess-{enc_id}"

    cache.create_session(
        encounter_id=uuid.UUID(enc_id),
        patient_id=uuid.UUID(pat_id),
        session_id=sess_id,
    )
    cache.update_session(
        sess_id,
        {
            "status": "INTERVIEW",
            "slots": [
                {"path": "symptoms.chest_pain", "value": True, "source": "utterance"},
                {"path": "symptoms.dyspnea", "value": True, "source": "utterance"},
                {"path": "symptoms.sweating", "value": True, "source": "utterance"},
            ],
        },
    )

    # Grant clinical consent
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True, qi=False, research=False),
        )
    )

    res = clinical_service.submit_session(session_id=sess_id)
    assert res.redflags_detected >= 1


def test_session_submission_records_audit_event():
    """Verify cryptographic audit event is emitted on encounter submission."""
    cache = SessionCache()
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())
    sess_id = f"sess-{enc_id}"

    cache.create_session(
        encounter_id=uuid.UUID(enc_id),
        patient_id=uuid.UUID(pat_id),
        session_id=sess_id,
    )
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )

    clinical_service.submit_session(
        session_id=sess_id,
        actor_id=pat_id,
        actor_role="patient",
    )

    # Verify audit event in audit service
    history = audit_service._repo.get_all()
    submission_events = [
        e for e in history
        if str(e.encounter_id) == enc_id and e.action == "CREATE" and e.resource_type == "ENCOUNTER"
    ]
    assert len(submission_events) >= 1
    assert submission_events[0].outcome == "ALLOW"


def test_api_session_submission_endpoint():
    """Verify REST POST /api/v1/sessions/{id}/submit endpoint executes end-to-end."""
    cache = SessionCache()
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())
    sess_id = f"sess-{enc_id}"

    cache.create_session(
        encounter_id=uuid.UUID(enc_id),
        patient_id=uuid.UUID(pat_id),
        session_id=sess_id,
    )
    cache.update_session(
        sess_id,
        {
            "status": "INTERVIEW",
            "slots": {"hpi.chief_complaint": "Joint pain", "hpi.duration": "1 week"},
        },
    )

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )

    response = client.post(
        f"/api/v1/sessions/{sess_id}/submit",
        json={"confirmed_by": "patient", "readback_accepted": True},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["encounter_id"] == enc_id
    assert data["status"] == "submitted"
    assert data["slots_persisted"] == 2
    assert data["session_purged"] is True
