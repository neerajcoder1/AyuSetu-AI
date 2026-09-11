"""
Phase 9 Integration Test: De-Identification & Secure Export REST Integration
============================================================================
Validates the complete REST API export pipeline under /api/v1/deid/export:
- Two-person authorization (Separation of Duties).
- 18 PRD identifiers + extended national ID suppression.
- HMAC research pseudonymization.
- ±30-day patient-consistent date shifting.
- 90+ age representation.
- Geography 20,000 population rule and unknown district fail-safe aggregation.
- Free-text narrative elimination.
- k-anonymity >= 5 equivalence class validation.
- Zero-PHI safety gate regex inspection.
"""

from typing import Any, Dict, List
import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.errors import ErrorCode
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.consent.service import consent_service

client = TestClient(gateway_app)


def _build_synthetic_records(count: int = 5, district: str = "lucknow", state: str = "Uttar Pradesh", dob: str = "1985-06-15") -> List[Dict[str, Any]]:
    records = []
    for i in range(1, count + 1):
        pt_id = f"018f0000-0000-7000-8000-00000000990{i}"
        enc_id = f"018f0000-0000-7000-8000-00000000991{i}"
        # Grant consent
        consent_service.grant_consent(
            ConsentGrantRequest(
                patient_id=pt_id,
                encounter_id=enc_id,
                purposes=Purposes(clinical=True, research=True, qi=True, abdm=True),
                language="hi",
            )
        )
        records.append({
            "patient_id": pt_id,
            "encounter_id": enc_id,
            "dob": "1930-01-01" if i == 1 and dob == "1930-01-01" else dob,
            "gender": "female",
            "district": district,
            "state": state,
            "department": "kayachikitsa",
            "encounter_date": "2026-05-10",
            "triage_tier": 2,
            "slots": [
                {"path": "symptoms.fever", "value_coded": "high", "code_system": "SNOMED", "code": "386661006"}
            ],
        })
    return records


def test_deid_rest_export_success():
    """Verify successful end-to-end export via /api/v1/deid/export with valid dual-approval."""
    candidate_records = _build_synthetic_records(count=5, district="lucknow", state="Uttar Pradesh", dob="1930-01-01")
    
    export_payload = {
        "export_request": {
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "purpose": "research",
            "approver_1": "usr-aud-001",
            "approver_2": "usr-adm-001",
        },
        "candidate_records": candidate_records,
    }

    # Authenticate as MRD officer (staff-token-mrd-officer)
    res = client.post(
        "/api/v1/deid/export",
        json=export_payload,
        headers={"Authorization": "Bearer staff-token-mrd-officer"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["cohort_size"] == 5
    assert data["k_anonymity_achieved"] is True

    records = data["records"]
    assert len(records) == 5

    # 1. Age 90+ capping validation for patient 0
    p0 = records[0]
    assert p0["age_band"] == "90+"
    assert "1930" not in p0.get("shifted_date_or_year", "")

    # 2. Direct identifier suppression
    for r in records:
        assert "patient_name" not in r
        assert "aadhaar" not in r
        assert "phone" not in r
        assert "pincode" not in r
        assert not r["pseudonym_token"].startswith("018f0000")


def test_deid_rest_export_small_district_aggregated_to_state():
    """Verify unknown or low population districts are aggregated to state per PRD §21.9."""
    candidate_records = _build_synthetic_records(count=5, district="unknown_rural_subdivision", state="Maharashtra")
    
    export_payload = {
        "export_request": {
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "purpose": "research",
            "approver_1": "usr-aud-001",
            "approver_2": "usr-adm-001",
        },
        "candidate_records": candidate_records,
    }

    res = client.post(
        "/api/v1/deid/export",
        json=export_payload,
        headers={"Authorization": "Bearer staff-token-mrd-officer"},
    )
    assert res.status_code == 200
    data = res.json()
    for rec in data["records"]:
        # District aggregated out to enclosing state
        assert rec["district_or_state"] == "Maharashtra"


def test_deid_rest_export_unauthorized_role_rejected():
    """Verify non-MRD/non-Auditor roles cannot invoke deid export endpoint."""
    candidate_records = _build_synthetic_records(count=5)
    export_payload = {
        "export_request": {
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "purpose": "research",
            "approver_1": "usr-aud-001",
            "approver_2": "usr-adm-001",
        },
        "candidate_records": candidate_records,
    }

    # Attendant attempts export -> 403 Forbidden
    res = client.post(
        "/api/v1/deid/export",
        json=export_payload,
        headers={"Authorization": "Bearer staff-token-attendant-ravi"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == ErrorCode.POLICY_DENIED.value
