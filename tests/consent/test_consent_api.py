"""
Test Suite: Consent & DPDP REST API Endpoints
==============================================
Validates HTTP REST endpoints on both the API Gateway (port 8080) and
the standalone Consent Service application (port 8108).
"""

from fastapi.testclient import TestClient
import pytest
import uuid6

from ayusetu.gateway.app import gateway_app
from ayusetu.consent.app import consent_app
from ayusetu.consent.service import consent_service
from ayusetu.consent.abdm_adapter import abdm_manager

gateway_client = TestClient(gateway_app)
consent_client = TestClient(consent_app)


@pytest.fixture(autouse=True)
def clean_state():
    consent_service.reset_state()
    yield
    consent_service.reset_state()


def test_standalone_consent_app_health():
    resp = consent_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "consent"
    assert data["port"] == 8108


def test_grant_consent_api_success():
    enc_id = "018f0000-0000-7000-8000-000000000011"
    pat_id = str(uuid6.uuid7())

    resp = gateway_client.post(
        "/api/v1/consent",
        headers={"Authorization": "Bearer staff-token-dr-aparna"},
        json={
            "patient_id": pat_id,
            "encounter_id": enc_id,
            "purposes": {"clinical": True, "abdm": True, "qi": False, "research": False},
            "language": "hi",
            "notice_version": "dpdp-v1.0",
        }
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["encounter_id"] == enc_id
    assert data["version"] == 1
    assert data["status"] == "active"
    assert data["purposes"]["clinical"] is True
    assert data["purposes"]["abdm"] is True


def test_get_encounter_consent_api():
    enc_id = "018f0000-0000-7000-8000-000000000011"
    pat_id = str(uuid6.uuid7())

    # Create consent first
    gateway_client.post(
        "/api/v1/consent",
        headers={"Authorization": "Bearer staff-token-dr-aparna"},
        json={
            "patient_id": pat_id,
            "encounter_id": enc_id,
            "purposes": {"clinical": True},
        }
    )

    # Retrieve consent
    get_resp = gateway_client.get(
        f"/api/v1/consent/{enc_id}",
        headers={"Authorization": "Bearer staff-token-dr-aparna"}
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["encounter_id"] == enc_id


def test_get_consent_history_api():
    enc_id = "018f0000-0000-7000-8000-000000000011"
    pat_id = str(uuid6.uuid7())

    headers = {"Authorization": "Bearer staff-token-dr-aparna"}
    # Version 1
    gateway_client.post(
        "/api/v1/consent",
        headers=headers,
        json={
            "patient_id": pat_id,
            "encounter_id": enc_id,
            "purposes": {"clinical": True, "research": True},
        }
    )

    # Version 2 (withdrawal)
    gateway_client.post(
        "/api/v1/consent/withdraw",
        headers=headers,
        json={
            "encounter_id": enc_id,
            "purposes_to_withdraw": ["research"]
        }
    )

    history_resp = gateway_client.get(f"/api/v1/consent/{enc_id}/history", headers=headers)
    assert history_resp.status_code == 200
    versions = history_resp.json()
    assert len(versions) == 2
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2


def test_erasure_request_and_status_api():
    pat_id = str(uuid6.uuid7())
    enc_id = "018f0000-0000-7000-8000-000000000011"
    headers = {"Authorization": "Bearer staff-token-dr-aparna"}

    # Submit erasure request
    post_resp = gateway_client.post(
        "/api/v1/erasure",
        headers=headers,
        json={
            "patient_id": pat_id,
            "encounter_id": enc_id,
            "reason": "patient_revoked_all_data",
        }
    )
    assert post_resp.status_code == 202
    res_data = post_resp.json()
    req_id = res_data["request_id"]
    assert res_data["status"] == "propagated"

    # Query erasure status
    get_resp = gateway_client.get(f"/api/v1/erasure/{req_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["request_id"] == req_id


def test_offline_consent_and_sync_api():
    enc_id = "018f0000-0000-7000-8000-000000000011"
    pat_id = str(uuid6.uuid7())
    headers = {"Authorization": "Bearer staff-token-dr-aparna"}

    # Record offline consent
    offline_resp = gateway_client.post(
        "/api/v1/consent/offline",
        headers=headers,
        json={
            "patient_id": pat_id,
            "encounter_id": enc_id,
            "purposes": {"clinical": True, "abdm": True},
            "device_id": "station-kiosk-99",
        }
    )
    assert offline_resp.status_code == 201
    assert offline_resp.json()["is_offline"] is True

    # Check ABDM status before sync (must be PENDING)
    abdm_before = gateway_client.get(f"/api/v1/abdm/{enc_id}/status", headers=headers)
    assert abdm_before.status_code == 200
    assert abdm_before.json()["status"] == "PENDING"
    assert abdm_before.json()["is_external_sharing_permitted"] is False

    # Sync offline consent
    sync_resp = gateway_client.post("/api/v1/consent/sync", headers=headers)
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()
    assert sync_data["synced_count"] == 1
    assert sync_data["chain_verified"] is True

    # Check ABDM status after sync (must still be PENDING awaiting external CM callback)
    abdm_after_sync = gateway_client.get(f"/api/v1/abdm/{enc_id}/status", headers=headers)
    assert abdm_after_sync.status_code == 200
    assert abdm_after_sync.json()["status"] == "PENDING"
    assert abdm_after_sync.json()["is_external_sharing_permitted"] is False

    # Authoritative CM callback receives external artefact
    abdm_manager.handle_authoritative_artefact_callback(enc_id, "abdm-art-auth-001")
    abdm_after_cb = gateway_client.get(f"/api/v1/abdm/{enc_id}/status", headers=headers)
    assert abdm_after_cb.status_code == 200
    assert abdm_after_cb.json()["status"] == "AVAILABLE"
    assert abdm_after_cb.json()["is_external_sharing_permitted"] is True
