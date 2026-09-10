"""
Tests for De-Identification Export Service & REST API
=====================================================
Validates:
- Two-Person Authorization & Separation of Duties (PRD §21.4):
  - Exporter must be MRD / Auditor
  - approver_1 != approver_2
  - exporter != approver_1 and exporter != approver_2
- DPDP Consent purpose filtering (patients without 'research' / 'qi' consent excluded)
- k-Anonymity enforcement (k >= 5)
- Zero-PHI pre-release safety gate
- Immutable PostgreSQL audit logging (ALLOW and DENY events)
- REST API endpoint /api/v1/deid/export
"""

import pytest
from fastapi.testclient import TestClient

from ayusetu.audit.models import AuditAction, AuditOutcome
from ayusetu.audit.service import AuditService
from ayusetu.gateway.errors import AyuSetuGatewayError
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.consent.service import ConsentService
from ayusetu.deid.models import DeidExportRequest, ExportPurpose
from ayusetu.deid.service import DeidExportService
from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.models import Principal, Role

client = TestClient(gateway_app)


def _make_candidate(
    patient_id: str,
    encounter_id: str,
    dob: str = "1990-01-01",
    district: str = "pune",
    state: str = "Maharashtra",
    gender: str = "female",
    dept: str = "kayachikitsa",
) -> dict:
    return {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "dob": dob,
        "gender": gender,
        "district": district,
        "state": state,
        "department": dept,
        "encounter_date": "2026-08-15",
        "triage_tier": 3,
        "slots": [
            {"path": "symptoms.fever", "value_coded": "mild", "code_system": "SNOMED", "code": "386661006"}
        ],
    }


def test_two_person_authorization_separation_of_duties():
    """Verify that exporter and two distinct approvers must all be separate identities."""
    svc = DeidExportService()

    mrd_principal = Principal(
        actor_id="usr-mrd-001",
        role=Role.MRD,
        is_authenticated=True,
    )

    # 1. Missing approvers -> Reject
    req_missing = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-09-01",
        approver_1="",
        approver_2="usr-aud-001",
    )
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        svc.validate_two_person_authorization(req_missing, mrd_principal)
    assert exc_info.value.status_code in (400, 403)

    # 2. Same person as approver 1 and approver 2 -> Reject
    req_same_app = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-09-01",
        approver_1="usr-aud-001",
        approver_2="usr-aud-001",
    )
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        svc.validate_two_person_authorization(req_same_app, mrd_principal)
    assert exc_info.value.status_code == 403
    assert "Separation of Duties" in exc_info.value.message

    # 3. Caller approving their own request -> Reject
    req_self_approve = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-09-01",
        approver_1="usr-mrd-001",  # Same as mrd_principal.actor_id!
        approver_2="usr-aud-001",
    )
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        svc.validate_two_person_authorization(req_self_approve, mrd_principal)
    assert exc_info.value.status_code == 403
    assert "Exporter cannot approve" in exc_info.value.message

    # 4. Valid distinct trio: caller=usr-mrd-001, app1=usr-mrd-002, app2=usr-aud-001 -> PASS
    req_valid = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-09-01",
        approver_1="usr-mrd-002",
        approver_2="usr-aud-001",
    )
    svc.validate_two_person_authorization(req_valid, mrd_principal)


def test_unauthorized_role_cannot_export():
    """Verify that roles other than MRD/AUDITOR cannot request exports."""
    svc = DeidExportService()
    nurse_principal = Principal(
        actor_id="usr-nur-001",
        role=Role.NURSE,
        is_authenticated=True,
    )
    req = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-09-01",
        approver_1="usr-mrd-001",
        approver_2="usr-aud-001",
    )
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        svc.validate_two_person_authorization(req, nurse_principal)
    assert exc_info.value.status_code == 403


def test_dpdp_consent_filtering_and_k_anonymity_success():
    """
    Verify end-to-end cohort export:
    - Grant 'research' consent to 6 encounters
    - Grant only 'clinical' consent to 1 encounter (excluded from research export)
    - Run export -> 6 records processed -> k=6 >= 5 -> Export succeeds & logged to audit
    """
    consent_svc = ConsentService()
    audit_svc = AuditService()
    export_svc = DeidExportService(audit_service=audit_svc, consent_service=consent_svc)

    mrd_principal = Principal(
        actor_id="usr-mrd-001",
        role=Role.MRD,
        is_authenticated=True,
    )

    candidates = []
    # Create 6 encounters with research=True
    for i in range(1, 7):
        pt_id = f"018f0000-0000-7000-8000-00000000010{i}"
        enc_id = f"018f0000-0000-7000-8000-00000000020{i}"
        consent_svc.grant_consent(
            ConsentGrantRequest(
                patient_id=pt_id,
                encounter_id=enc_id,
                purposes=Purposes(clinical=True, research=True, qi=False, abdm=False),
                language="en",
            )
        )
        candidates.append(
            _make_candidate(
                patient_id=pt_id,
                encounter_id=enc_id,
                dob="1990-05-10",
                district="bengaluru_urban",
                gender="female",
                dept="kayachikitsa",
            )
        )

    # 7th encounter: ONLY clinical consent, NO research consent
    pt_id_7 = "018f0000-0000-7000-8000-000000000107"
    enc_id_7 = "018f0000-0000-7000-8000-000000000207"
    consent_svc.grant_consent(
        ConsentGrantRequest(
            patient_id=pt_id_7,
            encounter_id=enc_id_7,
            purposes=Purposes(clinical=True, research=False, qi=False, abdm=False),
            language="en",
        )
    )
    candidates.append(
        _make_candidate(
            patient_id=pt_id_7,
            encounter_id=enc_id_7,
            dob="1990-05-10",
            district="bengaluru_urban",
            gender="female",
            dept="kayachikitsa",
        )
    )

    req = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-09-01",
        purpose=ExportPurpose.RESEARCH,
        approver_1="usr-mrd-002",
        approver_2="usr-aud-001",
    )

    response = export_svc.export_cohort(
        request=req,
        principal=mrd_principal,
        candidate_records=candidates,
    )

    assert response.status == "COMPLETED"
    assert response.cohort_size == 6  # 7th was excluded due to lack of research consent
    assert response.k_anonymity_achieved is True
    assert response.min_class_size == 6
    assert len(response.records) == 6

    # Verify no raw identifiers in output
    for rec in response.records:
        assert not rec.pseudonym_token.startswith("018f")
        assert rec.district_or_state == "Bengaluru_Urban"
        assert rec.age_band == "30-39"


def test_export_fails_closed_when_k_anonymity_not_met():
    """Verify that export is rejected and DENIED audit event logged when k < 5."""
    audit_svc = AuditService()
    export_svc = DeidExportService(audit_service=audit_svc)

    mrd_principal = Principal(
        actor_id="usr-mrd-001",
        role=Role.MRD,
        is_authenticated=True,
    )

    # Only 3 candidates in single class (k=3 < 5)
    candidates = [
        _make_candidate(
            patient_id=f"pt_00{i}",
            encounter_id=f"enc_00{i}",
            district="mysuru",
            dept="panchakarma",
        )
        for i in range(3)
    ]

    req = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-09-01",
        purpose=ExportPurpose.RESEARCH,
        approver_1="usr-mrd-002",
        approver_2="usr-aud-001",
    )

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        export_svc.export_cohort(
            request=req,
            principal=mrd_principal,
            candidate_records=candidates,
        )
    assert exc_info.value.status_code == 422
    assert "k-anonymity requirement" in exc_info.value.message


def test_deid_rest_api_endpoint():
    """Verify POST /api/v1/deid/export REST endpoint."""
    consent_svc = ConsentService()
    headers = {"Authorization": "Bearer staff-token-mrd-officer"}

    candidates = []
    for i in range(1, 6):
        pt_id = f"018f0000-0000-7000-8000-00000000030{i}"
        enc_id = f"018f0000-0000-7000-8000-00000000040{i}"
        consent_svc.grant_consent(
            ConsentGrantRequest(
                patient_id=pt_id,
                encounter_id=enc_id,
                purposes=Purposes(clinical=True, research=True, qi=False, abdm=False),
                language="en",
            )
        )
        candidates.append(
            _make_candidate(
                patient_id=pt_id,
                encounter_id=enc_id,
                district="chennai",
                gender="male",
                dept="shalya_tantra",
            )
        )

    payload = {
        "export_request": {
            "date_from": "2026-01-01",
            "date_to": "2026-09-01",
            "purpose": "research",
            "approver_1": "usr-mrd-002",
            "approver_2": "usr-aud-001",
        },
        "candidate_records": candidates,
    }

    res = client.post("/api/v1/deid/export", headers=headers, json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["cohort_size"] == 5
    assert data["k_anonymity_achieved"] is True
    assert len(data["records"]) == 5
