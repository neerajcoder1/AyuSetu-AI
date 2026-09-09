"""
Red-Flag Engine REST API Tests
==============================
Tests HTTP endpoints on both Gateway (port 8080) and Standalone service (port 8105).
"""

from fastapi.testclient import TestClient
import pytest
import uuid6

from ayusetu.gateway.app import gateway_app
from ayusetu.redflag.app import redflag_app
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes

client = TestClient(gateway_app)
redflag_client = TestClient(redflag_app)


def test_evaluate_and_query_endpoints():
    """Verify evaluation and query via Gateway REST API."""
    enc_id = "018f0000-0000-7000-8000-000000000011"
    pat_id = "018f0000-0000-7000-8000-000000000022"

    # Grant clinical consent
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
            language="en",
        )
    )

    headers = {"Authorization": "Bearer staff-token-dr-aparna"}

    # 1. Evaluate
    payload = {
        "encounter_id": enc_id,
        "facts": [
            {"path": "symptoms.chest_pain", "value": True},
            {"path": "symptoms.radiation", "value": True},
        ]
    }
    resp = client.post("/api/v1/redflag/evaluate", json=payload, headers=headers)
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    event_id = events[0]["id"]
    assert events[0]["rule_id"] == "RF-CARD-001"
    assert events[0]["tier"] == 1

    # 2. Get Encounter Red Flags
    resp_get = client.get(f"/api/v1/redflag/encounter/{enc_id}", headers=headers)
    assert resp_get.status_code == 200
    assert len(resp_get.json()) == 1

    # 3. Get Tier 1 Queue
    resp_queue = client.get("/api/v1/redflag/tier1-queue", headers=headers)
    assert resp_queue.status_code == 200
    assert len(resp_queue.json()) == 1
    assert resp_queue.json()[0]["event"]["id"] == event_id

    # 4. Acknowledge
    resp_ack = client.post(
        f"/api/v1/redflag/{event_id}/acknowledge",
        json={"notes": "Triage nurse evaluated ECG"},
        headers={"Authorization": "Bearer staff-token-nurse-sunita"},
    )
    assert resp_ack.status_code == 200
    assert resp_ack.json()["status"] == "acknowledged"

    # 5. Escalate
    resp_esc = client.post(
        f"/api/v1/redflag/{event_id}/escalate",
        json={"target_role": "duty_medical_officer", "notes": "ECG shows ST elevation"},
        headers=headers,
    )
    assert resp_esc.status_code == 200
    assert resp_esc.json()["status"] == "escalated"

    # 6. Resolve
    resp_res = client.post(
        f"/api/v1/redflag/{event_id}/resolve",
        json={"outcome": "TRIAGED_TO_CARDIAC_ICU", "notes": "Transferred immediately"},
        headers=headers,
    )
    assert resp_res.status_code == 200
    assert resp_res.json()["status"] == "resolved"


def test_standalone_service_health():
    """Verify standalone Red-Flag service health endpoint on port 8105."""
    resp = redflag_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "redflag"
    assert resp.json()["port"] == 8105
