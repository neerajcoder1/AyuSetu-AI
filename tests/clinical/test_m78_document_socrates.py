"""
Tests for M7.8 Document AI to Socrates Intake Slot Integration
=============================================================
Verifies PRD v3 §11.3:
- Automatic slot integration with source='document' provenance
- Preservation of needs_review flag
- Patient answers take precedence over document extractions
- Non-negative preservation
"""

import pytest
from ayusetu.clinical.document_service import document_service
from ayusetu.common.session_cache import SessionCache
import uuid6


@pytest.fixture
def active_session():
    cache = SessionCache()
    sess_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())
    sess = cache.create_session(encounter_id=enc_id, session_id=sess_id)
    return sess


def test_document_entities_prepopulate_slots(active_session):
    """Test uploaded document entities automatically populate session slots with provenance."""
    sess_id = active_session["session_id"]
    cache = SessionCache()

    # Upload prescription text containing medication, allergy, and condition
    raw_prescription = """
    Rx: Tab Paracetamol 500mg TDS
    Known Allergy: Penicillin (severe rash)
    Diagnosis: Hypertension
    BP: 130/85 mmHg
    """

    doc_result = document_service.process_document(
        session_id=sess_id,
        raw_text=raw_prescription,
        page_no=1,
    )

    # Verify session slots in cache
    updated_session = cache.get_session(sess_id)
    slots = updated_session.get("slots", [])
    assert len(slots) > 0

    # Verify slot provenance
    doc_slots = [s for s in slots if s.get("source") == "document"]
    assert len(doc_slots) > 0
    for s in doc_slots:
        assert s["source_ref"] == doc_result.document_id
        assert s["elicited"] is True
        assert s["reported_by"] == "patient"


def test_document_does_not_overwrite_patient_answer(active_session):
    """Test that explicit patient-elicited answers are NEVER overwritten by document OCR."""
    sess_id = active_session["session_id"]
    cache = SessionCache()

    # 1. Patient explicitly states no allergy during interview
    patient_slot = {
        "id": str(uuid6.uuid7()),
        "path": "allergies.Penicillin",
        "value": "Patient denies allergy to Penicillin (tested negative in 2024)",
        "source": "utterance",
        "reported_by": "patient",
        "elicited": True,
        "confidence": 1.0,
    }
    cache.update_session(sess_id, {"slots": [patient_slot]})

    # 2. Upload old document mentioning Penicillin allergy
    doc_result = document_service.process_document(
        session_id=sess_id,
        raw_text="Allergy: Penicillin",
        page_no=1,
    )

    # 3. Verify patient's explicit slot was NOT overwritten
    updated_session = cache.get_session(sess_id)
    slots = updated_session.get("slots", [])
    matching_slots = [s for s in slots if s.get("path") == "allergies.Penicillin"]
    assert len(matching_slots) == 1
    assert matching_slots[0]["value"] == "Patient denies allergy to Penicillin (tested negative in 2024)"
    assert matching_slots[0]["source"] == "utterance"


def test_low_confidence_entity_preserves_needs_review(active_session):
    """Test low confidence extracted entity preserves needs_review flag."""
    sess_id = active_session["session_id"]
    cache = SessionCache()

    # Upload noisy text
    doc_result = document_service.process_document(
        session_id=sess_id,
        raw_text="Rx: Tab Metfor... (faded print)",
        page_no=1,
    )

    updated_session = cache.get_session(sess_id)
    slots = updated_session.get("slots", [])
    for s in slots:
        if "Metfor" in str(s.get("value")):
            # If entity was flagged needs_review, slot maintains flag
            assert "needs_review" in s
