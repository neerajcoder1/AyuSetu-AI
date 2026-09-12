"""
Unit and Integration Tests for Mock ABDM HIU Longitudinal Record Adapter
========================================================================
Validates:
1. Parsing of synthetic FHIR R4 Bundle with Patient, Encounter, Condition, MedicationStatement, Observation
2. Ingestion and timeline integration of external CareContext records
3. Provenance tracking with external ABDM attribution
4. Idempotent deduplication (duplicate external imports skipped safely)
5. Rejection / fail-safe handling of malformed bundles
"""

import pytest
from fastapi.testclient import TestClient

from ayusetu.clinical.abdm_hiu_adapter import abdm_hiu_adapter
from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.errors import AyuSetuGatewayError


@pytest.fixture(autouse=True)
def reset_hiu_adapter():
    abdm_hiu_adapter.clear()
    yield
    abdm_hiu_adapter.clear()


@pytest.fixture
def client():
    return TestClient(gateway_app)


@pytest.fixture
def synthetic_fhir_bundle():
    return {
        "resourceType": "Bundle",
        "id": "bundle-ext-aiims-001",
        "type": "document",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "pat-aiims-991",
                    "name": [{"text": "Amitabh Sharma"}],
                }
            },
            {
                "resource": {
                    "resourceType": "Encounter",
                    "id": "enc-aiims-001",
                    "status": "finished",
                    "class": {"display": "Inpatient Discharge"},
                    "period": {"start": "2025-11-10T09:00:00Z"},
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "id": "cond-aiims-001",
                    "code": {
                        "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "I10", "display": "Essential Hypertension"}],
                        "text": "Essential Hypertension",
                    },
                    "recordedDate": "2025-11-10",
                }
            },
            {
                "resource": {
                    "resourceType": "MedicationStatement",
                    "id": "med-aiims-001",
                    "medicationCodeableConcept": {
                        "coding": [{"code": "TELMISARTAN-40", "display": "Telmisartan 40mg OD"}],
                        "text": "Telmisartan 40mg OD",
                    },
                    "status": "active",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-aiims-001",
                    "code": {
                        "coding": [{"code": "8480-6", "display": "Systolic Blood Pressure"}],
                        "text": "Systolic BP",
                    },
                    "valueQuantity": {"value": 138, "unit": "mmHg"},
                    "effectiveDateTime": "2025-11-10",
                }
            },
        ],
    }


def test_parse_synthetic_fhir_bundle(synthetic_fhir_bundle):
    """Verify parser extracts structured conditions, medications, observations from FHIR bundle."""
    parsed = abdm_hiu_adapter.parse_fhir_bundle(synthetic_fhir_bundle, facility_name="AIIMS New Delhi")
    assert parsed.facility_name == "AIIMS New Delhi"
    assert parsed.encounter_type == "Inpatient Discharge"
    assert parsed.encounter_date == "2025-11-10"
    assert len(parsed.entries) == 3

    types = {e.entry_type for e in parsed.entries}
    assert "condition" in types
    assert "medication" in types
    assert "observation" in types

    cond = next(e for e in parsed.entries if e.entry_type == "condition")
    assert cond.display == "Essential Hypertension"
    assert cond.code == "I10"
    assert cond.source == "abdm_hiu"
    assert cond.provenance_type == "external_abdm"


def test_import_external_bundle_end_to_end(client, synthetic_fhir_bundle):
    """Verify REST API endpoint imports external bundle and preserves provenance."""
    physician_headers = {"Authorization": "Bearer staff-token-dr-aparna"}
    patient_id = "018f0000-0000-7000-8000-000000000099"

    res = client.post(
        f"/api/v1/patients/{patient_id}/hiu/import?facility_name=AIIMS+New+Delhi",
        json=synthetic_fhir_bundle,
        headers=physician_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "imported"
    assert data["imported_entries"] == 3
    assert data["abdm_provenance"] == "PROVISIONAL_HIU_MOCK_VERIFIED"

    # Verify retrieval
    records = abdm_hiu_adapter.get_external_records_for_patient(patient_id)
    assert len(records) == 1
    assert records[0]["facility_name"] == "AIIMS New Delhi"


def test_duplicate_external_bundle_import_deduplicated(synthetic_fhir_bundle):
    """Verify importing identical external CareContext is deduplicated cleanly."""
    patient_id = "pat-dedup-001"
    
    # 1. First import
    res1 = abdm_hiu_adapter.import_external_bundle(patient_id, synthetic_fhir_bundle)
    assert res1["status"] == "imported"
    assert res1["imported_entries"] == 3

    # 2. Second import of same bundle -> deduplicated
    res2 = abdm_hiu_adapter.import_external_bundle(patient_id, synthetic_fhir_bundle)
    assert res2["status"] == "deduplicated"
    assert res2["imported_entries"] == 0


def test_malformed_fhir_bundle_rejected():
    """Verify invalid / non-bundle FHIR payloads are rejected with 422."""
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        abdm_hiu_adapter.parse_fhir_bundle({"resourceType": "Observation", "id": "single-obs"})
    assert exc_info.value.status_code == 422
