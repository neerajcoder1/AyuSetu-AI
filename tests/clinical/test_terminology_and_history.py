"""
Comprehensive M7.5 Terminology, Interaction, and Prior-Record History Tests
==========================================================================
Tests covering:
1. NAMASTE -> ICD-11 translation
2. ICD-11 -> NAMASTE translation
3. LOINC mapping
4. Confidence scoring
5. Unmapped terminology (fail-safe empty results)
6. Herb-drug interaction positive case
7. Herb-drug interaction negative case
8. Drug-drug interaction screening
9. Prior-record retrieval & longitudinal timeline
10. Provenance attribution
11. Consent enforcement (active clinical consent required)
12. RBAC/ABAC authorization via Gateway endpoints
13. Malformed input / error handling
14. Deterministic repeated results
"""

import uuid
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from ayusetu.clinical.terminology import TerminologyService, terminology_service, TERMINOLOGY_PROVENANCE
from ayusetu.clinical.repository import ClinicalRepository
from ayusetu.clinical.models import EncounterDTO, EncounterStatus, VisitType, IntakeDepth, Channel, SlotDTO, SlotSource, ReportedBy
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.models import Role
from ayusetu.gateway.errors import AyuSetuGatewayError


@pytest.fixture
def repo():
    r = ClinicalRepository()
    r.clear_for_testing()
    yield r
    r.clear_for_testing()


@pytest.fixture
def term_service(repo):
    return TerminologyService(repository=repo)


@pytest.fixture
def client():
    return TestClient(gateway_app)


# ---------------------------------------------------------------------------
# 1. NAMASTE -> ICD-11 Translation
# ---------------------------------------------------------------------------
def test_1_namaste_to_icd11_translation(term_service):
    # Test SK25 (Amlapitta)
    res = term_service.translate(code="SK25", system="NAMASTE")
    assert res["source_code"] == "SK25"
    assert len(res["matches"]) >= 2
    systems = {m["system"] for m in res["matches"]}
    assert "ICD-11 TM2" in systems
    assert "ICD-11 MMS" in systems
    tm2_match = next(m for m in res["matches"] if m["system"] == "ICD-11 TM2")
    assert tm2_match["code"] == "SK25"
    assert "Amlapitta" in tm2_match["display"]

    # Test AYU-PR-001 (Prameha)
    res_pr = term_service.translate(code="AYU-PR-001", system="NAMASTE")
    mms_match = next(m for m in res_pr["matches"] if m["system"] == "ICD-11 MMS")
    assert mms_match["code"] == "5A11"


# ---------------------------------------------------------------------------
# 2. ICD-11 -> NAMASTE Translation
# ---------------------------------------------------------------------------
def test_2_icd11_to_namaste_translation(term_service):
    # Test reverse mapping from ICD-11 MMS code 5A11
    res = term_service.translate(code="5A11", system="ICD-11")
    assert len(res["matches"]) >= 1
    namaste_match = res["matches"][0]
    assert namaste_match["system"] == "NAMASTE"
    assert namaste_match["code"] == "AYU-PR-001"
    assert namaste_match["display"] == "Prameha"

    # Test reverse mapping from ICD-11 MMS code DA42 (Dyspepsia -> Amlapitta)
    res_da42 = term_service.translate(code="DA42", system="ICD-11-MMS")
    assert res_da42["matches"][0]["code"] == "SK25"


# ---------------------------------------------------------------------------
# 3. LOINC Mapping
# ---------------------------------------------------------------------------
def test_3_loinc_mapping(term_service):
    # Lookup by LOINC code
    res = term_service.translate(code="718-7", system="LOINC")
    assert len(res["matches"]) == 1
    m = res["matches"][0]
    assert m["system"] == "LOINC"
    assert m["code"] == "718-7"
    assert m["analyte"] == "hemoglobin"
    assert m["reference_range"]["low"] == 12.0

    # Lookup by analyte name
    res_name = term_service.translate(code="hba1c", system="CLINICAL")
    assert any(m["code"] == "4548-4" for m in res_name["matches"])


# ---------------------------------------------------------------------------
# 4. Confidence Scoring
# ---------------------------------------------------------------------------
def test_4_confidence_scoring(term_service):
    # Exact code match has 1.0 confidence
    res_exact = term_service.translate(code="SK25", system="NAMASTE")
    assert res_exact["matches"][0]["confidence"] == 1.0

    # Synonym search has 0.85 - 0.95 confidence
    res_synonym = term_service.translate(code="hyperacidity", system="NAMASTE")
    assert 0.8 <= res_synonym["matches"][0]["confidence"] < 1.0


# ---------------------------------------------------------------------------
# 5. Unmapped Terminology (Zero Fabrication)
# ---------------------------------------------------------------------------
def test_5_unmapped_terminology_zero_fabrication(term_service):
    res = term_service.translate(code="NonExistentMedicalCode999", system="NAMASTE")
    assert res["source_code"] == "NonExistentMedicalCode999"
    assert res["matches"] == []
    assert res["provenance"] == TERMINOLOGY_PROVENANCE


# ---------------------------------------------------------------------------
# 6. Herb-Drug Interaction Positive Case
# ---------------------------------------------------------------------------
def test_6_herb_drug_interaction_positive(term_service):
    res = term_service.check_interactions(drugs=["turmeric", "anticoagulant"])
    assert len(res["interactions"]) == 1
    inter = res["interactions"][0]
    assert inter["kind"] == "herb_drug"
    assert inter["severity"] == "severe"
    assert "bleeding" in inter["description"].lower()


# ---------------------------------------------------------------------------
# 7. Herb-Drug Interaction Negative Case
# ---------------------------------------------------------------------------
def test_7_herb_drug_interaction_negative(term_service):
    res = term_service.check_interactions(drugs=["paracetamol"])
    assert res["checked_drugs"] == ["paracetamol"]
    assert res["interactions"] == []


# ---------------------------------------------------------------------------
# 8. Drug-Drug Interaction Screening
# ---------------------------------------------------------------------------
def test_8_drug_drug_interaction(term_service):
    res = term_service.check_interactions(drugs=["warfarin", "aspirin"])
    assert len(res["interactions"]) == 1
    inter = res["interactions"][0]
    assert inter["kind"] == "drug_drug"
    assert inter["severity"] == "severe"
    assert set(inter["substances"]) == {"warfarin", "aspirin"}


# ---------------------------------------------------------------------------
# 9. Prior-Record Retrieval & Longitudinal Timeline
# ---------------------------------------------------------------------------
def test_9_prior_record_retrieval(term_service, repo):
    patient_id = str(uuid.uuid4())
    enc1_id = str(uuid.uuid4())
    enc2_id = str(uuid.uuid4())

    # Encounter 1 (Historical)
    enc1 = EncounterDTO(
        id=enc1_id,
        patient_id=patient_id,
        department="Kayachikitsa",
        visit_type=VisitType.NEW,
        started_at=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        status=EncounterStatus.FINAL,
    )
    repo.create_encounter(enc1)
    repo.upsert_slot(SlotDTO(encounter_id=enc1_id, path="chief_complaint", value="Fever and severe body ache", source=SlotSource.UTTERANCE, reported_by=ReportedBy.PATIENT))
    repo.upsert_slot(SlotDTO(encounter_id=enc1_id, path="medications", value="Paracetamol 500mg", source=SlotSource.UTTERANCE, reported_by=ReportedBy.PATIENT))

    # Encounter 2 (Current)
    enc2 = EncounterDTO(
        id=enc2_id,
        patient_id=patient_id,
        department="Kayachikitsa",
        visit_type=VisitType.FOLLOWUP_STABLE,
        started_at=datetime(2025, 6, 20, 11, 0, tzinfo=timezone.utc),
        status=EncounterStatus.SUBMITTED,
    )
    repo.create_encounter(enc2)
    repo.upsert_slot(SlotDTO(encounter_id=enc2_id, path="chief_complaint", value="Followup for dyspepsia", source=SlotSource.UTTERANCE, reported_by=ReportedBy.PATIENT))

    # Grant consent for enc2
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=patient_id,
            encounter_id=enc2_id,
            purposes=Purposes(clinical=True, abdm=True),
            notice_version="dpdp-v1.0",
            language="hi",
        )
    )

    # Retrieve prior records for encounter 2
    prior = term_service.get_prior_records(encounter_id=enc2_id)
    assert prior["encounter_id"] == enc2_id
    assert prior["patient_id"] == patient_id
    assert prior["encounter_count"] == 2
    assert len(prior["records"]) >= 4

    # Verify event types and details exist
    titles = [r["title"] for r in prior["records"]]
    assert "Chief Complaint" in titles
    assert "Medications" in titles


# ---------------------------------------------------------------------------
# 10. Provenance Attribution
# ---------------------------------------------------------------------------
def test_10_provenance_attribution(term_service):
    res = term_service.translate(code="SK25")
    assert res["provenance"] == TERMINOLOGY_PROVENANCE


# ---------------------------------------------------------------------------
# 11. Consent Enforcement
# ---------------------------------------------------------------------------
def test_11_consent_enforcement(term_service, repo):
    patient_id = str(uuid.uuid4())
    enc_id = str(uuid.uuid4())

    enc = EncounterDTO(
        id=enc_id,
        patient_id=patient_id,
        department="Kayachikitsa",
        status=EncounterStatus.DRAFT,
    )
    repo.create_encounter(enc)

    # Without consent -> must raise 403 CONSENT_REQUIRED
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        term_service.get_prior_records(encounter_id=enc_id)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# 12. RBAC/ABAC Authorization via Gateway Endpoints
# ---------------------------------------------------------------------------
def test_12_rbac_gateway_authorization(client, repo):
    patient_id = str(uuid.uuid4())
    enc_id = str(uuid.uuid4())

    enc = EncounterDTO(
        id=enc_id,
        patient_id=patient_id,
        department="Kayachikitsa",
        status=EncounterStatus.SUBMITTED,
    )
    repo.create_encounter(enc)

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=patient_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
            notice_version="dpdp-v1.0",
        )
    )

    # Physician token -> 200 OK
    resp_phys = client.get(
        f"/api/v1/encounters/{enc_id}/prior",
        headers={"Authorization": "Bearer staff-token-dr-aparna"}
    )
    assert resp_phys.status_code == 200
    assert resp_phys.json()["encounter_id"] == enc_id

    # Nurse token -> 200 OK
    resp_nurse = client.get(
        f"/api/v1/encounters/{enc_id}/prior",
        headers={"Authorization": "Bearer staff-token-nurse-sunita"}
    )
    assert resp_nurse.status_code == 200

    # Attendant token (non-clinical reviewer) -> 403 Forbidden
    resp_att = client.get(
        f"/api/v1/encounters/{enc_id}/prior",
        headers={"Authorization": "Bearer staff-token-attendant-ravi"}
    )
    assert resp_att.status_code == 403


# ---------------------------------------------------------------------------
# 13. Malformed Input / Error Handling
# ---------------------------------------------------------------------------
def test_13_malformed_input_error_handling(term_service):
    # Non-existent encounter
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        term_service.get_prior_records(encounter_id=str(uuid.uuid4()))
    assert exc_info.value.status_code == 404

    # Empty translation
    res = term_service.translate(code="")
    assert res["matches"] == []

    # Empty interactions
    res_inter = term_service.check_interactions(drugs=[])
    assert res_inter["interactions"] == []


# ---------------------------------------------------------------------------
# 14. Deterministic Repeated Results
# ---------------------------------------------------------------------------
def test_14_deterministic_repeated_results(term_service):
    res1 = term_service.translate(code="AYU-PR-001", system="NAMASTE")
    res2 = term_service.translate(code="AYU-PR-001", system="NAMASTE")
    assert res1 == res2

    inter1 = term_service.check_interactions(drugs=["turmeric", "anticoagulant", "warfarin", "aspirin"])
    inter2 = term_service.check_interactions(drugs=["aspirin", "warfarin", "anticoagulant", "turmeric"])
    assert inter1["interactions"] == inter2["interactions"]
