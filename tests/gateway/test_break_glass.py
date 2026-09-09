"""
Test Suite: Emergency Break-Glass Authorization
================================================
Validates break-glass emergency overrides, role restrictions, mandatory reasons,
and security event audit hooks per PRD v2.0 §21.4.
"""

import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.event_hooks import register_security_event_listener, SecurityEvent

client = TestClient(gateway_app)


def test_physician_break_glass_unassigned_encounter_succeeds():
    events_captured = []

    def capture_event(event: SecurityEvent):
        events_captured.append(event)

    register_security_event_listener(capture_event)

    unassigned_enc = "018f0000-0000-7000-8000-000000000099"
    headers = {
        "Authorization": "Bearer staff-token-dr-aparna",
        "X-Break-Glass-Reason": "Patient arrived in acute distress at Kayachikitsa OPD"
    }

    # With valid break-glass header, access is granted immediately
    response = client.get(f"/api/v1/encounters/{unassigned_enc}/summary", headers=headers)
    assert response.status_code == 200
    assert response.json()["encounter_id"] == unassigned_enc

    # Assert security event hook was dispatched
    assert len(events_captured) >= 1
    event = events_captured[-1]
    assert event.event_type == "BREAK_GLASS"
    assert event.actor_id == "usr-phy-001"
    assert event.actor_role == "physician"
    assert "acute distress" in event.reason


def test_nurse_break_glass_requires_valid_reason():
    unassigned_enc = "018f0000-0000-7000-8000-000000000099"
    # Empty break glass reason fails
    headers = {
        "Authorization": "Bearer staff-token-nurse-sunita",
        "X-Break-Glass-Reason": "   "
    }
    response = client.get(f"/api/v1/encounters/{unassigned_enc}/summary", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_DENIED"


def test_auditor_cannot_break_glass():
    unassigned_enc = "018f0000-0000-7000-8000-000000000099"
    headers = {
        "Authorization": "Bearer staff-token-auditor-certin",
        "X-Break-Glass-Reason": "Emergency audit inspection"
    }
    response = client.get(f"/api/v1/encounters/{unassigned_enc}/summary", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_DENIED"
