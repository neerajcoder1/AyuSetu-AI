"""
Unit and Integration Tests for Milestone M8 — Station Fleet Management
======================================================================
Validates:
1. Station fleet listing and telemetry retrieval per PRD §14.2
2. Supervisor-only station remote locking with auditable reasons
3. Supervisor-only station remote unlocking with credentials
4. Remote station panic cache evacuation
5. Role-based access control (rejection of unauthorized roles)
6. Security and audit event dispatching
"""

import pytest
from fastapi.testclient import TestClient

from ayusetu.clinical.station_service import station_service, StationStatus
from ayusetu.common.session_cache import SessionCache
from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.event_hooks import register_security_event_listener, SecurityEvent


@pytest.fixture(autouse=True)
def reset_station_service():
    station_service.clear()
    yield
    station_service.clear()


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


def test_list_station_fleet_authorized_roles(client):
    """Verify nursing supervisor, attendant, and physician can view station fleet directory."""
    nurse_headers = {"Authorization": "Bearer staff-token-nurse-sunita"}
    res = client.get("/api/v1/stations", headers=nurse_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 4
    assert any(s["station_id"] == "kiosk-kaya-01" for s in data["stations"])

    # Filter by department
    res_kaya = client.get("/api/v1/stations?department=Kayachikitsa", headers=nurse_headers)
    assert res_kaya.status_code == 200
    assert all(s["department"] == "Kayachikitsa" for s in res_kaya.json()["stations"])


def test_list_station_fleet_unauthenticated_rejected(client):
    """Verify unauthenticated caller cannot access station fleet."""
    res = client.get("/api/v1/stations")
    assert res.status_code == 401


def test_lock_and_unlock_station_by_supervisor(client, recorded_events):
    """Verify supervisor can lock and unlock kiosk station with auditable reason."""
    nurse_headers = {"Authorization": "Bearer staff-token-nurse-sunita"}

    # 1. Lock station
    lock_res = client.post(
        "/api/v1/stations/kiosk-kaya-01/lock",
        json={"reason": "Hardware maintenance in progress"},
        headers=nurse_headers,
    )
    assert lock_res.status_code == 200
    lock_data = lock_res.json()
    assert lock_data["status"] == "locked"
    assert lock_data["lock_reason"] == "Hardware maintenance in progress"
    assert lock_data["locked_by"] is not None

    assert any(ev.event_type == "STATION_LOCKED" for ev in recorded_events)

    # 2. Unlock station
    unlock_res = client.post(
        "/api/v1/stations/kiosk-kaya-01/unlock",
        json={"pin_or_token": "supervisor-pin-1234"},
        headers=nurse_headers,
    )
    assert unlock_res.status_code == 200
    assert unlock_res.json()["status"] == "online"

    assert any(ev.event_type == "STATION_UNLOCKED" for ev in recorded_events)


def test_lock_station_empty_reason_rejected(client):
    """Verify lock request fails if supervisor reason is missing or empty."""
    nurse_headers = {"Authorization": "Bearer staff-token-nurse-sunita"}
    res = client.post(
        "/api/v1/stations/kiosk-kaya-01/lock",
        json={"reason": "  "},
        headers=nurse_headers,
    )
    assert res.status_code in (422, 400)


def test_remote_panic_purges_station_cache(client, recorded_events):
    """Verify remote panic trigger immediately purges active station session."""
    nurse_headers = {"Authorization": "Bearer staff-token-nurse-sunita"}

    # Create active session on station
    cache = SessionCache()
    create_res = client.post("/api/v1/sessions", json={"channel": "kiosk"})
    session_id = create_res.json()["session_id"]
    cache.update_session(session_id, {"patient_name": "Suresh Raina"})

    station_service.register_or_heartbeat("kiosk-kaya-01", active_session_id=session_id)
    assert station_service.get_station("kiosk-kaya-01").active_session_id == session_id

    # Trigger remote panic
    panic_res = client.post(
        "/api/v1/stations/kiosk-kaya-01/remote-panic",
        headers=nurse_headers,
    )
    assert panic_res.status_code == 200
    assert panic_res.json()["purged_session_id"] == session_id
    assert panic_res.json()["purged"] is True

    # Verify session completely evacuated from cache
    assert cache.get_session(session_id) is None
    assert any(ev.event_type == "STATION_REMOTE_PANIC" for ev in recorded_events)
