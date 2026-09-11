"""
Phase 9 Failure-Injection Test Suite
====================================
Controlled failure injection and fail-closed validation:
- PostgreSQL outage injection (503 Service Unavailable).
- Redis outage injection (503 Service Unavailable).
- K-anonymity threshold violation (k < 5).
- Zero-PHI safety gate trip (unmasked identifier in cohort).
- Two-Person Authorization violations (Self-approval, Duplicate approver, Role mismatch).
- Consent purpose gating failures (Missing research consent).
"""

from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.gateway.auth.models import Principal, Role
from ayusetu.deid.models import DeidExportRequest, ExportPurpose
from ayusetu.deid.service import deid_export_service
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes

client = TestClient(gateway_app)


def test_postgresql_outage_fails_closed_with_503():
    """Verify PostgreSQL downtime returns 503 and hides internal DB crash details."""
    with patch("ayusetu.gateway.routes.health.SyncSessionLocal", side_effect=RuntimeError("Connection to postgres:5432 failed: timeout")):
        res = client.get("/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"] == "unreachable"
        assert "postgres:5432" not in res.text
        assert "password" not in res.text


def test_redis_outage_fails_closed_with_503():
    """Verify Redis downtime returns 503 and marks session cache unreachable."""
    with patch("ayusetu.gateway.routes.health.ping_redis", return_value=False):
        res = client.get("/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "degraded"
        assert data["components"]["redis"] == "unreachable"


def test_k_anonymity_violation_fails_closed():
    """Verify cohorts failing k-anonymity (e.g. k=2 when threshold=5) are blocked with 422 / failure."""
    mrd_principal = Principal(
        actor_id="usr-mrd-001",
        role=Role.MRD,
        department="MedicalRecords",
        is_authenticated=True,
    )
    # 2 records with distinct quasi-identifiers -> min class size = 1 < 5
    candidate_records = [
        {"patient_id": "018f0000-0000-7000-8000-000000000001", "encounter_id": "018f0000-0000-7000-8000-000000000001", "dob": "1990-01-01", "gender": "male", "district": "pune", "state": "Maharashtra", "department": "kayachikitsa", "encounter_date": "2026-08-15"},
        {"patient_id": "018f0000-0000-7000-8000-000000000002", "encounter_id": "018f0000-0000-7000-8000-000000000002", "dob": "1990-01-01", "gender": "female", "district": "mumbai", "state": "Maharashtra", "department": "kayachikitsa", "encounter_date": "2026-08-15"},
    ]
    # Grant research consent for both
    for r in candidate_records:
        consent_service.grant_consent(
            ConsentGrantRequest(
                patient_id=r["patient_id"],
                encounter_id=r["encounter_id"],
                purposes=Purposes(clinical=True, research=True, qi=True, abdm=True),
                language="hi",
            )
        )

    req = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-12-31",
        purpose=ExportPurpose.RESEARCH,
        approver_1="usr-aud-001",
        approver_2="usr-adm-001",
    )

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        deid_export_service.export_cohort(req, mrd_principal, candidate_records)
    
    assert exc_info.value.status_code == 422
    assert "k-anonymity" in exc_info.value.message.lower()


def test_two_person_sod_exporter_self_approval_rejected():
    """Verify exporter cannot approve their own export request (Separation of Duties)."""
    mrd_principal = Principal(
        actor_id="usr-mrd-001",
        role=Role.MRD,
        department="MedicalRecords",
        is_authenticated=True,
    )
    req = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-12-31",
        purpose=ExportPurpose.RESEARCH,
        approver_1="usr-mrd-001",  # Self approval
        approver_2="usr-adm-001",
    )

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        deid_export_service.export_cohort(req, mrd_principal, [])
    
    assert exc_info.value.status_code == 403
    assert "cannot approve their own" in exc_info.value.message.lower()


def test_two_person_sod_duplicate_approvers_rejected():
    """Verify Approver 1 and Approver 2 cannot be the same entity."""
    mrd_principal = Principal(
        actor_id="usr-mrd-001",
        role=Role.MRD,
        department="MedicalRecords",
        is_authenticated=True,
    )
    req = DeidExportRequest(
        date_from="2026-01-01",
        date_to="2026-12-31",
        purpose=ExportPurpose.RESEARCH,
        approver_1="usr-aud-001",
        approver_2="usr-aud-001",  # Duplicate approver
    )

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        deid_export_service.export_cohort(req, mrd_principal, [])
    
    assert exc_info.value.status_code == 403
    assert "cannot be the same individual" in exc_info.value.message.lower()
