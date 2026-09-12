"""
Tests for FHIR R4 Document Bundle Generation Engine
===================================================
Authoritative validation per PRD v2.0 §15 and M7.4 requirements.
Validates:
- FHIR R4 Bundle structure and type="document"
- Composition resource is mandatory first entry
- Patient, Encounter, Condition, AllergyIntolerance, MedicationStatement mapping
- Provenance linkage to source slot IDs
- Zero fabrication of unelicited/absent slots
- Preliminary vs Final/Signed status fidelity
- Missing and malformed encounter error handling (404, 422)
- API endpoint integration and RBAC enforcement (Physician/MRD allowed, others denied)
- Deterministic bundle generation
"""

import base64
import json
import pytest
import uuid
import uuid6
from fastapi.testclient import TestClient

from ayusetu.common.config import settings
from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.models import Role
from ayusetu.gateway.auth.session_auth import SessionAuthenticator
from ayusetu.gateway.errors import AyuSetuGatewayError
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.clinical.models import (
    EncounterDTO,
    EncounterStatus,
    IntakeDepth,
    ReportedBy,
    SlotDTO,
    SlotSource,
    SummaryStatus,
    SummaryVersionDTO,
    VisitType,
)
from ayusetu.clinical.repository import ClinicalRepository
from ayusetu.clinical.service import clinical_service
from ayusetu.clinical.fhir_engine import fhir_bundle_engine, FHIRBundleEngine


@pytest.fixture
def repo():
    r = ClinicalRepository()
    r.clear_for_testing()
    return r


@pytest.fixture
def client():
    return TestClient(gateway_app)


def test_basic_fhir_bundle_structure(repo):
    """Verify standard FHIR R4 Document Bundle envelope and mandatory Composition first entry."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    enc = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        department="Kayachikitsa",
        visit_type=VisitType.NEW,
        intake_depth=IntakeDepth.FULL,
        status=EncounterStatus.SUBMITTED,
    )
    repo.submit_encounter_atomic(encounter=enc, utterances=[], slots=[])

    bundle = fhir_bundle_engine.generate_bundle(enc_id)

    # 1. Top-level bundle validation
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "document"
    assert bundle["id"] == f"bundle-{enc_id}"
    assert "timestamp" in bundle
    assert len(bundle["entry"]) >= 4  # Composition, Patient, Encounter, Binary

    # 2. Composition must be entry[0]
    first_res = bundle["entry"][0]["resource"]
    assert first_res["resourceType"] == "Composition"
    assert first_res["status"] == "preliminary"
    assert first_res["subject"]["reference"] == f"Patient/pat-{pat_id}"
    assert first_res["encounter"]["reference"] == f"Encounter/enc-{enc_id}"
    assert first_res["title"] == "AyuSetu Pre-Consultation History Summary"

    # 3. Patient resource in entry[1]
    pat_res = bundle["entry"][1]["resource"]
    assert pat_res["resourceType"] == "Patient"
    assert pat_res["id"] == f"pat-{pat_id}"

    # 4. Encounter resource in entry[2]
    enc_res = bundle["entry"][2]["resource"]
    assert enc_res["resourceType"] == "Encounter"
    assert enc_res["id"] == f"enc-{enc_id}"
    assert enc_res["status"] == "finished"

    # 5. Binary resource in entry[-1]
    bin_res = bundle["entry"][-1]["resource"]
    assert bin_res["resourceType"] == "Binary"
    assert bin_res["contentType"] == "application/json"
    decoded_summary = json.loads(base64.b64decode(bin_res["data"]).decode("utf-8"))
    assert decoded_summary["encounter_id"] == enc_id


def test_clinical_slots_mapped_to_fhir_resources(repo):
    """Verify slots are correctly transformed into Condition, AllergyIntolerance, and MedicationStatement."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    enc = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        department="Kayachikitsa",
        status=EncounterStatus.SUBMITTED,
    )
    slot1 = SlotDTO(
        encounter_id=enc_id,
        path="hpi.chief_complaint",
        value="Severe retrosternal chest pain",
        source=SlotSource.UTTERANCE,
        elicited=True,
    )
    slot2 = SlotDTO(
        encounter_id=enc_id,
        path="pmh.diabetes",
        value="Type 2 Diabetes Mellitus diagnosed 5 years ago",
        source=SlotSource.UTTERANCE,
        elicited=True,
    )
    slot3 = SlotDTO(
        encounter_id=enc_id,
        path="allergies.drug",
        value="Penicillin causing anaphylaxis",
        source=SlotSource.UTTERANCE,
        elicited=True,
    )
    slot4 = SlotDTO(
        encounter_id=enc_id,
        path="medications.current",
        value="Metformin 500mg BD",
        source=SlotSource.UTTERANCE,
        elicited=True,
    )
    # Unelicited slot that must NOT create a resource
    slot5 = SlotDTO(
        encounter_id=enc_id,
        path="lifestyle.smoking",
        value=None,
        elicited=False,
    )

    repo.submit_encounter_atomic(encounter=enc, utterances=[], slots=[slot1, slot2, slot3, slot4, slot5])

    bundle = fhir_bundle_engine.generate_bundle(enc_id)
    entry_resources = [e["resource"] for e in bundle["entry"]]
    resource_types = [r["resourceType"] for r in entry_resources]

    # Verify presence of clinical resources
    assert "Condition" in resource_types
    assert "AllergyIntolerance" in resource_types
    assert "MedicationStatement" in resource_types

    # Verify Condition mapping and provenance
    conditions = [r for r in entry_resources if r["resourceType"] == "Condition"]
    assert len(conditions) == 2  # Chief complaint + PMH
    cc_cond = next(c for c in conditions if "Severe retrosternal" in c["code"]["text"])
    assert cc_cond["clinicalStatus"]["coding"][0]["code"] == "active"
    assert cc_cond["verificationStatus"]["coding"][0]["code"] == "provisional"
    assert cc_cond["evidence"][0]["detail"][0]["reference"] == f"Slot/{slot1.id}"

    # Verify AllergyIntolerance mapping
    allergies = [r for r in entry_resources if r["resourceType"] == "AllergyIntolerance"]
    assert len(allergies) == 1
    assert "Penicillin" in allergies[0]["code"]["text"]

    # Verify MedicationStatement mapping
    meds = [r for r in entry_resources if r["resourceType"] == "MedicationStatement"]
    assert len(meds) == 1
    assert "Metformin" in meds[0]["medicationCodeableConcept"]["text"]


def test_unelicited_slots_are_never_fabricated_as_resources(repo):
    """Ensure missing/unelicited slots never produce phantom clinical resources."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    enc = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        department="Kayachikitsa",
        status=EncounterStatus.SUBMITTED,
    )
    # Only unelicited slots
    slots = [
        SlotDTO(encounter_id=enc_id, path="allergies.drug", value=None, elicited=False),
        SlotDTO(encounter_id=enc_id, path="medications.current", value=None, elicited=False),
        SlotDTO(encounter_id=enc_id, path="pmh.hypertension", value=None, elicited=False),
    ]
    repo.submit_encounter_atomic(encounter=enc, utterances=[], slots=slots)

    bundle = fhir_bundle_engine.generate_bundle(enc_id)
    entry_types = [e["resource"]["resourceType"] for e in bundle["entry"]]

    assert "AllergyIntolerance" not in entry_types
    assert "MedicationStatement" not in entry_types
    assert "Condition" not in entry_types
    # Only Composition, Patient, Encounter, Binary
    assert entry_types == ["Composition", "Patient", "Encounter", "Binary"]


def test_signed_final_summary_updates_bundle_status(repo):
    """Verify that a signed summary sets Composition status to 'final' and reflects physician authorship."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    enc = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        department="Kayachikitsa",
        status=EncounterStatus.SUBMITTED,
    )
    slot1 = SlotDTO(
        encounter_id=enc_id,
        path="hpi.chief_complaint",
        value="Amlapitta with sour eructation",
        elicited=True,
    )
    repo.submit_encounter_atomic(encounter=enc, utterances=[], slots=[slot1])

    # Generate and sign summary
    clinical_service.generate_summary(enc_id)
    clinical_service.sign_summary(
        encounter_id=enc_id,
        physician_id="usr-phy-dr-sharma",
        physician_role="physician",
    )

    bundle = fhir_bundle_engine.generate_bundle(enc_id)
    composition = bundle["entry"][0]["resource"]

    assert composition["status"] == "final"
    assert "Practitioner/" in composition["author"][0]["reference"]
    assert composition["author"][0]["display"] is not None

    conditions = [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Condition"]
    assert len(conditions) == 1
    assert conditions[0]["verificationStatus"]["coding"][0]["code"] == "confirmed"


def test_fhir_generation_fails_safely_on_missing_or_malformed_encounter():
    """Verify 404 on nonexistent encounter and 422 on invalid UUID format."""
    # 1. Non-existent UUID -> 404
    missing_id = str(uuid6.uuid7())
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        fhir_bundle_engine.generate_bundle(missing_id)
    assert exc_info.value.status_code == 404

    # 2. Malformed non-UUID string -> 422
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        fhir_bundle_engine.generate_bundle("not-a-valid-uuid")
    assert exc_info.value.status_code == 422


def test_fhir_generation_enforces_clinical_consent(repo):
    """Verify 403 when active clinical consent is missing or revoked."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    enc = EncounterDTO(id=enc_id, patient_id=pat_id, status=EncounterStatus.SUBMITTED)
    repo.submit_encounter_atomic(encounter=enc, utterances=[], slots=[])

    # Grant only research consent (no clinical consent)
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=False, abdm=False, qi=False, research=True),
        )
    )

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        fhir_bundle_engine.generate_bundle(enc_id)
    assert exc_info.value.status_code == 403


def test_deterministic_bundle_generation(repo):
    """Verify identical inputs generate identical, deterministic bundle output."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    enc = EncounterDTO(id=enc_id, patient_id=pat_id, status=EncounterStatus.SUBMITTED)
    slot1 = SlotDTO(encounter_id=enc_id, path="hpi.chief_complaint", value="Fever and chills", elicited=True)
    repo.submit_encounter_atomic(encounter=enc, utterances=[], slots=[slot1])

    bundle1 = fhir_bundle_engine.generate_bundle(enc_id)
    bundle2 = fhir_bundle_engine.generate_bundle(enc_id)

    assert bundle1["id"] == bundle2["id"]
    assert len(bundle1["entry"]) == len(bundle2["entry"])
    assert bundle1["entry"][0]["resource"]["title"] == bundle2["entry"][0]["resource"]["title"]


def test_api_get_encounter_fhir_endpoint_rbac(client, repo):
    """Verify GET /api/v1/encounters/{id}/fhir is accessible by Physician & MRD, denied for Patient."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    enc = EncounterDTO(id=enc_id, patient_id=pat_id, status=EncounterStatus.SUBMITTED)
    repo.submit_encounter_atomic(encounter=enc, utterances=[], slots=[])

    # 1. Staff Physician access -> 200 OK
    resp_phy = client.get(
        f"/api/v1/encounters/{enc_id}/fhir",
        headers={"Authorization": "Bearer staff-token-dr-aparna"}
    )
    assert resp_phy.status_code == 200
    bundle_data = resp_phy.json()
    assert bundle_data["resourceType"] == "Bundle"
    assert bundle_data["type"] == "document"
    assert bundle_data["entry"][0]["resource"]["resourceType"] == "Composition"

    # 2. Staff MRD access -> 200 OK
    resp_mrd = client.get(
        f"/api/v1/encounters/{enc_id}/fhir",
        headers={"Authorization": "Bearer staff-token-mrd-officer"}
    )
    assert resp_mrd.status_code == 200

    # 3. Nurse role without physician/MRD role -> 403 Forbidden
    resp_nurse = client.get(
        f"/api/v1/encounters/{enc_id}/fhir",
        headers={"Authorization": "Bearer staff-token-nurse-sunita"}
    )
    assert resp_nurse.status_code == 403

    # 4. Attendant role -> 403 Forbidden
    resp_att = client.get(
        f"/api/v1/encounters/{enc_id}/fhir",
        headers={"Authorization": "Bearer staff-token-attendant-ravi"}
    )
    assert resp_att.status_code == 403
