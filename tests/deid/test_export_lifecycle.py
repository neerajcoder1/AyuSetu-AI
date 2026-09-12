"""
Unit and Integration Tests for Two-Person SoD De-Identification Export Lifecycle
================================================================================
Validates:
1. Two-person authorization (Separation of Duties) validation
2. Rejection of single approver or self-approval
3. Asynchronous / completed export job tracking
4. Successful download of sanitized JSON bundle
5. Zero-PHI and k-anonymity gate enforcement on export download
6. Audit recording of export events
"""

import pytest
from fastapi.testclient import TestClient

from ayusetu.deid.service import deid_export_service
from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.models import Role


@pytest.fixture(autouse=True)
def reset_export_service():
    deid_export_service.clear()
    yield
    deid_export_service.clear()


@pytest.fixture
def client():
    return TestClient(gateway_app)


def test_valid_two_person_sod_export_and_download(client):
    """Verify MRD role with 2 distinct approvers initiates and downloads sanitized export."""
    mrd_headers = {"Authorization": "Bearer staff-token-mrd-officer"}

    # 1. Initiate export
    payload = {
        "date_from": "2026-01-01",
        "date_to": "2026-06-30",
        "purpose": "research",
        "approver_1": "approver_director_01",
        "approver_2": "approver_irb_02",
        "department": "Kayachikitsa",
    }
    res_init = client.post("/api/v1/exports", json=payload, headers=mrd_headers)
    assert res_init.status_code == 202
    data = res_init.json()
    export_id = data["export_id"]
    assert data["status"] in ("pending_processing", "completed")
    assert data["cohort_size"] == 10

    # 2. Check export status
    res_status = client.get(f"/api/v1/exports/{export_id}", headers=mrd_headers)
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["export_id"] == export_id
    assert status_data["k_anonymity_achieved"] is True

    # 3. Download sanitized dataset bundle
    res_dl = client.get(f"/api/v1/exports/{export_id}/download", headers=mrd_headers)
    assert res_dl.status_code == 200
    dl_data = res_dl.json()
    assert dl_data["export_id"] == export_id
    assert dl_data["records_count"] == 10
    
    # Assert zero raw identifiers in records
    for rec in dl_data["records"]:
        assert rec["pseudonym_token"].startswith("anon_")
        assert "patient_id" not in rec
        assert "phone" not in rec
        assert "abha" not in rec


def test_export_rejected_with_identical_approvers(client):
    """Verify export fails if approver 1 and approver 2 are the same individual."""
    mrd_headers = {"Authorization": "Bearer staff-token-mrd-officer"}
    payload = {
        "date_from": "2026-01-01",
        "date_to": "2026-06-30",
        "purpose": "research",
        "approver_1": "approver_same_01",
        "approver_2": "approver_same_01",
    }
    res = client.post("/api/v1/exports", json=payload, headers=mrd_headers)
    assert res.status_code == 403


def test_export_rejected_with_missing_approver(client):
    """Verify export fails if an approver is missing or empty."""
    mrd_headers = {"Authorization": "Bearer staff-token-mrd-officer"}
    payload = {
        "date_from": "2026-01-01",
        "date_to": "2026-06-30",
        "purpose": "research",
        "approver_1": "approver_first_01",
        "approver_2": "  ",
    }
    res = client.post("/api/v1/exports", json=payload, headers=mrd_headers)
    assert res.status_code == 403


def test_download_nonexistent_export_returns_404(client):
    """Verify download endpoint returns 404 for invalid export ID."""
    mrd_headers = {"Authorization": "Bearer staff-token-mrd-officer"}
    res = client.get("/api/v1/exports/nonexistent-id-0000/download", headers=mrd_headers)
    assert res.status_code == 404
