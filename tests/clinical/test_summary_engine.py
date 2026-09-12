"""
Phase M7.2: Clinical Summary Synthesis & Provenance Engine Tests
================================================================
Validates deterministic Slot -> Summary synthesis conforming to packages/schemas/summary.json,
structured clinical section extraction (HPI, PMH, Medications, Allergies, Lifestyle),
strict preservation of unelicited information (never inferring false negatives),
granular provenance tracking to source Slots/Utterances, SummaryVersion persistence (v1, preliminary),
idempotency, consent gating, and zero-PHI error sanitization.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List
import uuid
import uuid6
import pytest
from fastapi.testclient import TestClient
import jsonschema

from ayusetu.gateway.app import gateway_app
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes
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
    SummaryStatus,
    SummaryVersionDTO,
    ClinicalSummaryDTO,
)
from ayusetu.clinical.repository import ClinicalRepository
from ayusetu.clinical.service import ClinicalService, clinical_service
from ayusetu.clinical.summary_engine import SummarySynthesisEngine, summary_synthesis_engine, get_summary_schema
from ayusetu.gateway.errors import AyuSetuGatewayError

client = TestClient(gateway_app)

SCHEMA_PATH = Path(__file__).parents[2] / "packages" / "schemas" / "summary.json"


@pytest.fixture(autouse=True)
def clean_clinical_db():
    """Ensure clean clinical repository state before each test."""
    repo = ClinicalRepository()
    repo.clear_for_testing()
    yield
    repo.clear_for_testing()


# =====================================================================
# 1. Basic Slot -> Summary Transformation & Schema Validation
# =====================================================================

def test_basic_slot_to_summary_synthesis():
    """Verify basic transformation of slots into structured clinical summary matching summary.json."""
    enc_id = str(uuid6.uuid7())
    utt_id = str(uuid6.uuid7())
    slot_id = str(uuid6.uuid7())

    slots = [
        SlotDTO(
            id=slot_id,
            encounter_id=enc_id,
            path="hpi.chief_complaint",
            value="Amlapitta with burning sensation in chest",
            confidence=0.95,
            source=SlotSource.UTTERANCE,
            source_ref=utt_id,
            reported_by=ReportedBy.PATIENT,
            elicited=True,
        )
    ]

    summary = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)

    assert summary.encounter_id == enc_id
    assert summary.version == 1
    assert summary.status == SummaryStatus.PRELIMINARY
    assert summary.model_version == "ayusetu-synthesis-v1.0"
    assert len(summary.sections) == 5

    # Validate JSON Schema compliance directly
    summary_dict = summary.model_dump(mode="json")
    schema = get_summary_schema()
    format_checker = jsonschema.FormatChecker()
    jsonschema.validate(instance=summary_dict, schema=schema, format_checker=format_checker)


# =====================================================================
# 2. HPI Section Synthesis
# =====================================================================

def test_hpi_synthesis_with_complex_symptoms():
    """Verify HPI section combines chief complaint, duration, severity, location, onset, and associated symptoms."""
    enc_id = str(uuid6.uuid7())
    u1 = str(uuid6.uuid7())
    u2 = str(uuid6.uuid7())

    slots = [
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="hpi.chief_complaint",
            value="Severe epigastric burning pain",
            confidence=0.98,
            source=SlotSource.UTTERANCE,
            source_ref=u1,
            elicited=True,
        ),
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="hpi.duration",
            value="2 weeks",
            confidence=0.92,
            source=SlotSource.UTTERANCE,
            source_ref=u1,
            elicited=True,
        ),
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="hpi.severity",
            value="moderate-to-severe",
            confidence=0.88,
            source=SlotSource.UTTERANCE,
            source_ref=u1,
            elicited=True,
        ),
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="hpi.location",
            value="upper abdomen",
            confidence=0.90,
            source=SlotSource.TOUCH,
            source_ref=None,
            elicited=True,
        ),
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="symptoms.nausea",
            value="postprandial nausea",
            confidence=0.85,
            source=SlotSource.UTTERANCE,
            source_ref=u2,
            elicited=True,
        ),
    ]

    summary = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)
    hpi_sec = next(s for s in summary.sections if s.id == "hpi")

    assert hpi_sec.title == "History of Present Illness"
    assert len(hpi_sec.clauses) == 2

    # First clause: composite HPI
    c1 = hpi_sec.clauses[0]
    assert "Severe epigastric burning pain" in c1.text
    assert "for 2 weeks" in c1.text
    assert "with moderate-to-severe severity" in c1.text
    assert "located in upper abdomen" in c1.text
    assert c1.elicited is True
    assert "hpi.chief_complaint" in c1.slots
    assert "hpi.duration" in c1.slots
    assert "hpi.severity" in c1.slots
    assert "hpi.location" in c1.slots

    # Second clause: associated symptom
    c2 = hpi_sec.clauses[1]
    assert "postprandial nausea" in c2.text
    assert c2.elicited is True
    assert "symptoms.nausea" in c2.slots
    assert u2 in c2.source.get("ids", [])


# =====================================================================
# 3. Past Medical History (PMH) Synthesis
# =====================================================================

def test_pmh_synthesis():
    """Verify Past Medical History correctly aggregates diagnosed conditions."""
    enc_id = str(uuid6.uuid7())
    slot_id = str(uuid6.uuid7())

    slots = [
        SlotDTO(
            id=slot_id,
            encounter_id=enc_id,
            path="pmh.diabetes",
            value="Type 2 Diabetes Mellitus diagnosed 5 years ago",
            confidence=0.96,
            source=SlotSource.UTTERANCE,
            elicited=True,
        )
    ]

    summary = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)
    pmh_sec = next(s for s in summary.sections if s.id == "pmh")

    assert len(pmh_sec.clauses) == 1
    assert "Type 2 Diabetes Mellitus" in pmh_sec.clauses[0].text
    assert pmh_sec.clauses[0].elicited is True
    assert slot_id in pmh_sec.clauses[0].source.get("ids", [])


# =====================================================================
# 4. Medication Synthesis
# =====================================================================

def test_medication_synthesis():
    """Verify Medication section captures current medications with provenance."""
    enc_id = str(uuid6.uuid7())
    slot1_id = str(uuid6.uuid7())
    slot2_id = str(uuid6.uuid7())

    slots = [
        SlotDTO(
            id=slot1_id,
            encounter_id=enc_id,
            path="medications.allopathic",
            value="Metformin 500mg BD",
            confidence=0.94,
            source=SlotSource.UTTERANCE,
            elicited=True,
        ),
        SlotDTO(
            id=slot2_id,
            encounter_id=enc_id,
            path="medications.ayurvedic",
            value="Avipattikar Churna 3g before meals",
            confidence=0.91,
            source=SlotSource.UTTERANCE,
            elicited=True,
        ),
    ]

    summary = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)
    med_sec = next(s for s in summary.sections if s.id == "medications")

    assert len(med_sec.clauses) == 2
    assert "Metformin 500mg BD" in med_sec.clauses[0].text
    assert "Avipattikar Churna 3g" in med_sec.clauses[1].text
    assert med_sec.clauses[0].elicited is True
    assert med_sec.clauses[1].elicited is True


# =====================================================================
# 5. Allergy Synthesis: Elicited vs Explicit Negative Finding
# =====================================================================

def test_allergy_synthesis_positive_and_explicit_negative():
    """Verify positive allergy and explicit elicited negative finding ('no allergies') are handled correctly."""
    enc_id = str(uuid6.uuid7())

    # Case A: Positive allergy
    slots_pos = [
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="allergies.drug",
            value="Penicillin causing urticaria",
            confidence=0.97,
            source=SlotSource.UTTERANCE,
            elicited=True,
        )
    ]
    summary_pos = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots_pos)
    all_sec_pos = next(s for s in summary_pos.sections if s.id == "allergies")
    assert "Penicillin causing urticaria" in all_sec_pos.clauses[0].text
    assert all_sec_pos.clauses[0].elicited is True

    # Case B: Explicit elicited negative finding ("none" / "no known allergies")
    slots_neg = [
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="allergies.history",
            value="No known allergies",
            confidence=0.99,
            source=SlotSource.UTTERANCE,
            elicited=True,
        )
    ]
    summary_neg = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots_neg)
    all_sec_neg = next(s for s in summary_neg.sections if s.id == "allergies")
    assert "No known drug or environmental allergies reported" in all_sec_neg.clauses[0].text
    assert all_sec_neg.clauses[0].elicited is True


# =====================================================================
# 6. Lifestyle / Social History Synthesis
# =====================================================================

def test_lifestyle_synthesis():
    """Verify lifestyle factors (diet, tobacco, sleep) are synthesized with provenance."""
    enc_id = str(uuid6.uuid7())

    slots = [
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="lifestyle.diet",
            value="Vegetarian diet, irregular meal timings, high spicy food intake",
            confidence=0.89,
            source=SlotSource.UTTERANCE,
            elicited=True,
        ),
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="lifestyle.sleep",
            value="Late night sleep pattern (1 AM)",
            confidence=0.91,
            source=SlotSource.UTTERANCE,
            elicited=True,
        ),
    ]

    summary = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)
    life_sec = next(s for s in summary.sections if s.id == "lifestyle")

    assert len(life_sec.clauses) == 2
    assert "Vegetarian diet" in life_sec.clauses[0].text
    assert "Late night sleep" in life_sec.clauses[1].text


# =====================================================================
# 7 & 8. Unelicited Slots & No False Negative Inferences
# =====================================================================

def test_unelicited_slots_preserved_as_unelicited_never_negative():
    """
    CRITICAL REQUIREMENT:
    If information was never elicited, the engine must mark elicited=False
    and NEVER infer 'No allergies', 'None', 'Negative', 'No medications', etc.
    """
    enc_id = str(uuid6.uuid7())

    # Empty slot set (no intake questions asked)
    summary = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=[])

    for sec in summary.sections:
        assert len(sec.clauses) >= 1
        for clause in sec.clauses:
            assert clause.elicited is False
            # Check prohibited false-negative wording
            lower_text = clause.text.lower()
            assert "no known allergies" not in lower_text
            assert "denies" not in lower_text
            assert "no history" not in lower_text
            assert "not taking" not in lower_text
            assert "none" not in lower_text
            # Must explicitly state "not elicited"
            assert "not elicited" in lower_text


# =====================================================================
# 9. Provenance Citation Preservation
# =====================================================================

def test_provenance_linkage_to_source_slot_and_utterance():
    """Verify provenance contains slot ID, utterance ref, source type, and confidence."""
    enc_id = str(uuid6.uuid7())
    slot_id = str(uuid6.uuid7())
    utt_id = str(uuid6.uuid7())

    slots = [
        SlotDTO(
            id=slot_id,
            encounter_id=enc_id,
            path="hpi.chief_complaint",
            value="Acid reflux with regurgitation",
            confidence=0.93,
            source=SlotSource.UTTERANCE,
            source_ref=utt_id,
            elicited=True,
        )
    ]

    summary = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)
    hpi_sec = next(s for s in summary.sections if s.id == "hpi")
    clause = hpi_sec.clauses[0]

    assert clause.slots == ["hpi.chief_complaint"]
    assert clause.source["type"] == "utterance"
    assert slot_id in clause.source["ids"]
    assert utt_id in clause.source["ids"]
    assert clause.confidence == 0.93
    assert clause.elicited is True


# =====================================================================
# 10. Determinism (100% Reproducibility)
# =====================================================================

def test_deterministic_summary_output():
    """Verify that identical slot sets always generate identical summaries byte-for-byte."""
    enc_id = str(uuid6.uuid7())
    slot1_id = str(uuid6.uuid7())
    slot2_id = str(uuid6.uuid7())

    slots = [
        SlotDTO(
            id=slot1_id,
            encounter_id=enc_id,
            path="hpi.chief_complaint",
            value="Severe headache with photophobia",
            confidence=0.91,
            source=SlotSource.UTTERANCE,
            elicited=True,
        ),
        SlotDTO(
            id=slot2_id,
            encounter_id=enc_id,
            path="medications.current",
            value="Paracetamol 650mg SOS",
            confidence=0.88,
            source=SlotSource.UTTERANCE,
            elicited=True,
        ),
    ]

    summary1 = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)
    summary2 = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)

    assert summary1.model_dump(mode="json") == summary2.model_dump(mode="json")


# =====================================================================
# 11, 12, 13, 14. SummaryVersion Persistence & Idempotency
# =====================================================================

def test_summary_version_persistence_and_idempotency():
    """Verify SummaryVersion created with version=1, status=preliminary, and idempotent upsert."""
    repo = ClinicalRepository()
    service = ClinicalService(repository=repo)

    pat_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())

    enc_dto = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        department="Kayachikitsa",
        visit_type=VisitType.NEW,
        intake_depth=IntakeDepth.FULL,
        channel=Channel.KIOSK,
        status=EncounterStatus.SUBMITTED,
    )
    repo.create_encounter(enc_dto)

    slot_dto = SlotDTO(
        id=str(uuid6.uuid7()),
        encounter_id=enc_id,
        path="hpi.chief_complaint",
        value="Persistent dry cough",
        confidence=0.92,
        source=SlotSource.UTTERANCE,
        elicited=True,
    )
    repo.upsert_slot(slot_dto)

    # 1. Generate summary version 1
    sum_ver1 = service.generate_summary(enc_id)
    assert sum_ver1.version == 1
    assert sum_ver1.status == SummaryStatus.PRELIMINARY
    assert sum_ver1.encounter_id == enc_id
    assert sum_ver1.model_version == "ayusetu-synthesis-v1.0"
    assert sum_ver1.signed_by is None
    assert sum_ver1.signed_at is None

    # Total count of summaries in DB should be 1
    assert repo.count_summaries() == 1

    # 2. Repeated generation should update preliminary version 1, not duplicate
    sum_ver2 = service.generate_summary(enc_id)
    assert sum_ver2.version == 1
    assert repo.count_summaries() == 1
    assert sum_ver2.id == sum_ver1.id


# =====================================================================
# 15. Invalid / Malformed Slot Data Handling
# =====================================================================

def test_malformed_slot_data_rejected_safely():
    """Verify summary engine gracefully handles empty values and malformed paths."""
    enc_id = str(uuid6.uuid7())

    slots = [
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="unknown.random.path",
            value="",
            confidence=None,
            source=SlotSource.DERIVED,
            elicited=False,
        )
    ]

    summary = summary_synthesis_engine.synthesize(encounter_id=enc_id, slots=slots)
    assert summary.encounter_id == enc_id
    # Valid schema output even with unexpected slot paths
    summary_dict = summary.model_dump(mode="json")
    schema = get_summary_schema()
    jsonschema.validate(instance=summary_dict, schema=schema)


# =====================================================================
# 16. Consent & Authorization Enforcement on Summary
# =====================================================================

def test_consent_gating_on_summary_generation():
    """Verify summary generation is blocked if patient has explicitly revoked or withheld clinical consent."""
    repo = ClinicalRepository()
    service = ClinicalService(repository=repo)

    pat_id = str(uuid6.uuid7())
    enc_id = str(uuid6.uuid7())

    enc_dto = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        department="Kayachikitsa",
        visit_type=VisitType.NEW,
        intake_depth=IntakeDepth.FULL,
        channel=Channel.KIOSK,
        status=EncounterStatus.SUBMITTED,
    )
    repo.create_encounter(enc_dto)

    # Record consent with clinical=False
    consent_req = ConsentGrantRequest(
        encounter_id=enc_id,
        patient_id=pat_id,
        purposes=Purposes(clinical=False, research_aggregate=True),
        language_used="hi",
        signature_type="otp",
    )
    consent_service.grant_consent(consent_req)

    # Attempting to generate summary must raise 403 CONSENT_REQUIRED
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        service.generate_summary(enc_id)

    assert exc_info.value.status_code == 403


# =====================================================================
# 17. Zero-PHI Observability in Error Handling & Logging
# =====================================================================

def test_zero_phi_in_summary_error_handling(caplog):
    """Verify summary engine error responses contain zero patient health info."""
    service = ClinicalService()

    fake_enc_id = str(uuid6.uuid7())
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        service.generate_summary(fake_enc_id)

    err_msg = str(exc_info.value.detail)
    assert "not found" in err_msg
    # Ensure no patient data is reflected
    assert "Kaya" not in err_msg
    assert "Amlapitta" not in err_msg


# =====================================================================
# 18. End-to-End Lifecycle Integration Test
# =====================================================================

def test_end_to_end_summary_synthesis_lifecycle():
    """
    Integration test:
    Persisted Encounter -> Persisted Utterances -> Persisted Slots
    -> Summary Engine -> Structured Summary -> SummaryVersion(status=preliminary)
    -> Provenance preserved
    """
    repo = ClinicalRepository()
    service = ClinicalService(repository=repo)

    pat_id = str(uuid6.uuid7())
    enc_id = "018f0000-0000-7000-8000-000000000011"
    u1_id = str(uuid6.uuid7())
    u2_id = str(uuid6.uuid7())
    s1_id = str(uuid6.uuid7())
    s2_id = str(uuid6.uuid7())
    s3_id = str(uuid6.uuid7())

    enc_dto = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        department="Shalya",
        visit_type=VisitType.NEW,
        intake_depth=IntakeDepth.FULL,
        channel=Channel.KIOSK,
        status=EncounterStatus.DRAFT,
    )

    utterances = [
        UtteranceDTO(
            id=u1_id,
            encounter_id=enc_id,
            seq=1,
            speaker="patient",
            text="Mujhe 3 din se pet me dard ho raha hai.",
            lang="hi",
            asr_confidence=0.96,
        ),
        UtteranceDTO(
            id=u2_id,
            encounter_id=enc_id,
            seq=2,
            speaker="patient",
            text="Mujhe Sulfa drugs se allergy hai.",
            lang="hi",
            asr_confidence=0.94,
        ),
    ]

    slots = [
        SlotDTO(
            id=s1_id,
            encounter_id=enc_id,
            path="hpi.chief_complaint",
            value="Abdominal pain for 3 days",
            confidence=0.95,
            source=SlotSource.UTTERANCE,
            source_ref=u1_id,
            elicited=True,
        ),
        SlotDTO(
            id=s2_id,
            encounter_id=enc_id,
            path="allergies.drug",
            value="Sulfa drugs allergy",
            confidence=0.93,
            source=SlotSource.UTTERANCE,
            source_ref=u2_id,
            elicited=True,
        ),
        SlotDTO(
            id=s3_id,
            encounter_id=enc_id,
            path="lifestyle.diet",
            value="Mixed diet, regular water intake",
            confidence=0.88,
            source=SlotSource.TOUCH,
            elicited=True,
        ),
    ]

    # Atomic submission
    persisted_enc = repo.submit_encounter_atomic(
        encounter=enc_dto,
        utterances=utterances,
        slots=slots,
    )
    assert persisted_enc.status == EncounterStatus.SUBMITTED

    # Synthesize & persist summary version 1
    summary_ver = service.generate_summary(enc_id)
    assert summary_ver.version == 1
    assert summary_ver.status == SummaryStatus.PRELIMINARY

    # Verify provenance preserved in composition
    comp = summary_ver.composition
    hpi_clause = comp["sections"][0]["clauses"][0]
    assert "Abdominal pain" in hpi_clause["text"]
    assert s1_id in hpi_clause["source"]["ids"]
    assert u1_id in hpi_clause["source"]["ids"]

    allergy_clause = comp["sections"][3]["clauses"][0]
    assert "Sulfa drugs" in allergy_clause["text"]
    assert s2_id in allergy_clause["source"]["ids"]
    assert u2_id in allergy_clause["source"]["ids"]

    # Verify unelicited PMH remains explicitly unelicited
    pmh_clause = comp["sections"][1]["clauses"][0]
    assert pmh_clause["elicited"] is False
    assert "not elicited" in pmh_clause["text"].lower()

    # Verify retrieval via HTTP API with physician credentials
    headers = {"Authorization": "Bearer staff-token-dr-aparna"}
    resp = client.get(f"/api/v1/encounters/{enc_id}/summary", headers=headers)
    assert resp.status_code == 200
    api_summary = resp.json()
    assert api_summary["encounter_id"] == enc_id
    assert api_summary["status"] == "preliminary"
    assert len(api_summary["sections"]) == 5
