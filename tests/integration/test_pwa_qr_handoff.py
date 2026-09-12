"""
Integration Tests for PWA -> Kiosk Cryptographic QR Hand-off (PRD §3.2)
========================================================================
Validates:
1. Valid HMAC-SHA256 signed QR hand-off payload migration (pwa_self -> kiosk)
2. Expiration window enforcement (15-minute hand-off TTL)
3. Cryptographic signature tampering rejection
4. Cross-station replay & reuse prevention
5. Finalized / submitted session resumption rejection
6. Security and audit logging of hand-off transitions
"""

import hashlib
import hmac
import time
import pytest
from fastapi.testclient import TestClient

from ayusetu.common.config import settings
from ayusetu.common.session_cache import SessionCache
from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.event_hooks import register_security_event_listener, SecurityEvent


@pytest.fixture
def client():
    return TestClient(gateway_app)


@pytest.fixture
def recorded_events():
    events = []
    def listener(event: SecurityEvent):
        events.append(event)
    register_security_event_listener(listener)
    return events


def _generate_qr_signature(session_id: str, station_id: str, token: str, expires_at: float) -> str:
    secret = settings.JWT_SECRET_KEY.encode("utf-8")
    msg = f"{session_id}:{station_id}:{token}:{expires_at}".encode("utf-8")
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def test_valid_pwa_to_kiosk_qr_handoff(client, recorded_events):
    """Verify valid PWA self-intake session transfers cleanly to kiosk station via QR."""
    # 1. Initialize PWA self session
    res_init = client.post("/api/v1/sessions", json={"channel": "pwa_self"})
    assert res_init.status_code == 201
    sess_data = res_init.json()
    session_id = sess_data["session_id"]
    token = sess_data["token"]

    # Populate partial intake data
    cache = SessionCache()
    cache.update_session(session_id, {
        "slots": [{"path": "chief_complaint", "value": "Joint stiffness in morning"}],
    })

    # 2. Generate signed QR hand-off payload
    now = time.time()
    expires_at = now + 600.0  # 10 minutes in future (<15 min limit)
    station_id = "kiosk-pancha-01"
    signature = _generate_qr_signature(session_id, station_id, token, expires_at)

    qr_payload = {
        "session_id": session_id,
        "token": token,
        "station_id": station_id,
        "issued_at": now,
        "expires_at": expires_at,
        "signature": signature,
    }

    # 3. Resume at target kiosk station
    res_resume = client.post(f"/api/v1/sessions/{session_id}/resume", json=qr_payload)
    assert res_resume.status_code == 200
    data = res_resume.json()
    assert data["status"] == "resumed"
    assert data["channel"] == "kiosk"
    assert data["claimed_by_station"] == station_id

    # Verify session slots and state preserved
    updated_session = cache.get_session(session_id)
    assert updated_session["channel"] == "kiosk"
    assert updated_session["claimed_by_station"] == station_id
    assert updated_session["slots"][0]["value"] == "Joint stiffness in morning"

    assert any(ev.event_type == "SESSION_HANDOFF_COMPLETED" for ev in recorded_events)


def test_expired_qr_handoff_rejected(client, recorded_events):
    """Verify expired QR hand-off payload (>15m) is rejected."""
    res_init = client.post("/api/v1/sessions", json={"channel": "pwa_self"})
    sess_data = res_init.json()
    session_id = sess_data["session_id"]
    token = sess_data["token"]

    past_time = time.time() - 1000.0  # Expired
    station_id = "kiosk-pancha-01"
    signature = _generate_qr_signature(session_id, station_id, token, past_time)

    qr_payload = {
        "session_id": session_id,
        "token": token,
        "station_id": station_id,
        "expires_at": past_time,
        "signature": signature,
    }

    res_resume = client.post(f"/api/v1/sessions/{session_id}/resume", json=qr_payload)
    assert res_resume.status_code == 401
    assert any(ev.event_type == "QR_HANDOFF_EXPIRED" for ev in recorded_events)


def test_tampered_qr_signature_rejected(client, recorded_events):
    """Verify tampered cryptographic QR signature is rejected."""
    res_init = client.post("/api/v1/sessions", json={"channel": "pwa_self"})
    sess_data = res_init.json()
    session_id = sess_data["session_id"]
    token = sess_data["token"]

    expires_at = time.time() + 600.0
    station_id = "kiosk-kaya-01"

    qr_payload = {
        "session_id": session_id,
        "token": token,
        "station_id": station_id,
        "expires_at": expires_at,
        "signature": "bad_tampered_signature_hex_1234567890abcdef",
    }

    res_resume = client.post(f"/api/v1/sessions/{session_id}/resume", json=qr_payload)
    assert res_resume.status_code == 403
    assert any(ev.event_type == "QR_HANDOFF_SIGNATURE_INVALID" for ev in recorded_events)


def test_cross_station_reuse_rejected(client, recorded_events):
    """Verify session already claimed by station A cannot be re-claimed by station B."""
    res_init = client.post("/api/v1/sessions", json={"channel": "pwa_self"})
    sess_data = res_init.json()
    session_id = sess_data["session_id"]
    token = sess_data["token"]

    expires_at = time.time() + 600.0

    # 1. Claim at Station Alpha
    sig_alpha = _generate_qr_signature(session_id, "station-alpha", token, expires_at)
    res_alpha = client.post(
        f"/api/v1/sessions/{session_id}/resume",
        json={"session_id": session_id, "token": token, "station_id": "station-alpha", "expires_at": expires_at, "signature": sig_alpha}
    )
    assert res_alpha.status_code == 200

    # 2. Attempt replay at Station Beta -> Rejected 403
    sig_beta = _generate_qr_signature(session_id, "station-beta", token, expires_at)
    res_beta = client.post(
        f"/api/v1/sessions/{session_id}/resume",
        json={"session_id": session_id, "token": token, "station_id": "station-beta", "expires_at": expires_at, "signature": sig_beta}
    )
    assert res_beta.status_code == 403
    assert any(ev.event_type == "QR_HANDOFF_CROSS_STATION_REUSE" for ev in recorded_events)


def test_resume_submitted_session_rejected(client):
    """Verify completed/submitted session cannot be resumed."""
    res_init = client.post("/api/v1/sessions", json={"channel": "pwa_self"})
    session_id = res_init.json()["session_id"]

    # Submit session
    client.post(f"/api/v1/sessions/{session_id}/submit", json={"confirmed_by": "patient", "readback_accepted": True})

    # Attempt resume
    res_resume = client.post(
        f"/api/v1/sessions/{session_id}/resume",
        json={"session_id": session_id, "station_id": "kiosk-kaya-01"}
    )
    assert res_resume.status_code in (403, 404)
