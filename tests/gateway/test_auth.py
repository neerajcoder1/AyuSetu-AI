"""
Test Suite: Authentication & Session Validation
================================================
Validates token authentication, session lookup, revocation, device CRL, and logout.
"""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.device import DeviceAuthenticator
from ayusetu.gateway.auth.models import Role

client = TestClient(gateway_app)


def test_staff_login_and_auth_me():
    # 1. Login as Physician
    login_resp = client.post("/api/v1/auth/token", json={"username": "dr-aparna"})
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert token_data["role"] == "physician"
    assert token_data["token_type"] == "bearer"
    token = token_data["access_token"]

    # 2. Introspect profile using Bearer token
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["actor_id"] == "usr-phy-001"
    assert me_data["role"] == "physician"
    assert me_data["department"] == "Kayachikitsa"


def test_invalid_bearer_token():
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-tampered-token"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


def test_missing_credentials_on_protected_endpoint():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


def test_device_revocation_denies_access():
    device_fp = "kiosk-stolen-cert-fingerprint-999"
    DeviceAuthenticator.revoke_device(device_fp)

    try:
        response = client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": "Bearer staff-token-dr-aparna",
                "X-Device-Fingerprint": device_fp
            }
        )
        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "POLICY_DENIED"
        assert "revoked" in data["error"]["message"]
    finally:
        DeviceAuthenticator.unrevoke_device(device_fp)


def test_logout_and_session_invalidation():
    # 1. Create a kiosk session
    create_resp = client.post("/api/v1/sessions", json={"channel": "kiosk"})
    assert create_resp.status_code == 201
    sess = create_resp.json()
    token = sess["token"]
    sess_id = sess["session_id"]

    # 2. Authenticate with session token
    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "patient"

    # 3. Panic clear / logout session
    logout_resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200

    # 4. Subsequent call fails as expired
    subsequent_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert subsequent_resp.status_code == 401
    assert subsequent_resp.json()["error"]["code"] == "SESSION_EXPIRED"


def test_username_only_authentication_rejected():
    """Verify username-as-token is rejected and prevents regression."""
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer dr-aparna"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


def test_staff_token_authentication_succeeds():
    """Verify staff-token-{username} format authenticates expected physician."""
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer staff-token-dr-aparna"}
    )
    assert response.status_code == 200
    me_data = response.json()
    assert me_data["actor_id"] == "usr-phy-001"
    assert me_data["role"] == "physician"
    assert me_data["department"] == "Kayachikitsa"


def test_invalid_staff_login_credentials_rejected():
    """Verify invalid staff login username is rejected."""
    login_resp = client.post("/api/v1/auth/token", json={"username": "unknown-nonexistent-user"})
    assert login_resp.status_code == 401
    assert login_resp.json()["error"]["code"] == "POLICY_DENIED"


def test_non_revoked_device_fingerprint_allowed():
    """Verify non-revoked device fingerprint is accepted."""
    response = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer staff-token-dr-aparna",
            "X-Device-Fingerprint": "valid-kiosk-station-001"
        }
    )
    assert response.status_code == 200
    assert response.json()["actor_id"] == "usr-phy-001"

