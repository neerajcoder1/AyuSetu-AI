"""
Test Suite: Gateway Core Functionality
=======================================
Validates /api/v1 routing, health probes, request IDs, and session stubs.
"""

import uuid
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app

client = TestClient(gateway_app)


def test_gateway_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "AyuSetu API Gateway"
    assert data["port"] == 8080
    assert data["prefix"] == "/api/v1"


def test_gateway_liveness():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ayusetu-gateway"


def test_gateway_readiness():
    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_session.execute.return_value = None

    with patch("ayusetu.gateway.routes.health.SyncSessionLocal", return_value=mock_session), \
         patch("ayusetu.gateway.routes.health.ping_redis", return_value=True):
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

        # Also test /api/v1/health alias
        response_v1 = client.get("/api/v1/health")
        assert response_v1.status_code == 200
        assert response_v1.json()["status"] == "ready"


def test_request_id_generated_when_missing():
    response = client.get("/")
    assert response.status_code == 200
    req_id = response.headers.get("X-Request-ID")
    assert req_id is not None
    assert len(req_id) >= 16


def test_request_id_propagated_when_valid():
    valid_id = "test-custom-req-id-12345678"
    response = client.get("/", headers={"X-Request-ID": valid_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == valid_id


def test_request_id_replaced_when_malformed():
    malformed_id = "bad id with spaces and <script>alert(1)</script>"
    response = client.get("/", headers={"X-Request-ID": malformed_id})
    assert response.status_code == 200
    req_id = response.headers.get("X-Request-ID")
    assert req_id != malformed_id
    assert "<script>" not in req_id


def test_session_lifecycle_stubs():
    # 1. Create session
    create_resp = client.post("/api/v1/sessions", json={
        "channel": "kiosk",
        "department": "Kayachikitsa",
        "visit_type": "new",
        "intake_depth": "full"
    })
    assert create_resp.status_code == 201
    sess_data = create_resp.json()
    assert "session_id" in sess_data
    assert "token" in sess_data
    session_id = sess_data["session_id"]

    # 2. Identify
    id_resp = client.post(f"/api/v1/sessions/{session_id}/identify", json={
        "auth_type": "provisional",
        "name": "Test Patient"
    })
    assert id_resp.status_code == 200
    assert id_resp.json()["status"] == "matched"

    # 3. Consent
    consent_resp = client.post(f"/api/v1/sessions/{session_id}/consent", json={
        "purposes": {"clinical": True, "abdm": True, "qi": False, "research": False},
        "language": "hi",
        "notice_version": "dpdp-v1.0"
    })
    assert consent_resp.status_code == 200
    assert consent_resp.json()["status"] == "recorded"

    # 4. Submit
    submit_resp = client.post(f"/api/v1/sessions/{session_id}/submit", json={
        "confirmed_by": "patient",
        "readback_accepted": True
    })
    assert submit_resp.status_code == 202
    assert submit_resp.json()["summary_status"] == "generating"


def test_panic_clear():
    # Create session
    create_resp = client.post("/api/v1/sessions", json={})
    assert create_resp.status_code == 201
    session_id = create_resp.json()["session_id"]

    # Trigger panic clear (<2s target)
    panic_resp = client.post(f"/api/v1/sessions/{session_id}/panic-clear")
    assert panic_resp.status_code == 200
    assert panic_resp.json()["purged"] is True

    # Subsequent access with cleared session returns 401 SESSION_EXPIRED
    subsequent_resp = client.post(f"/api/v1/sessions/{session_id}/identify", json={
        "auth_type": "provisional"
    })
    assert subsequent_resp.status_code == 401
    assert subsequent_resp.json()["error"]["code"] == "SESSION_EXPIRED"
