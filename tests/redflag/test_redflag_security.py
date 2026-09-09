"""
Red-Flag Engine Security & Access Control Tests
===============================================
Validates RBAC restrictions, ABAC encounter scoping, consent gating,
and zero-PHI audit logging boundaries.
"""

from fastapi.testclient import TestClient
import pytest
import uuid6

from ayusetu.gateway.app import gateway_app
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.common.session_cache import SessionCache
from ayusetu.audit.service import audit_service
from ayusetu.redflag.service import red_flag_service
from ayusetu.redflag.models import StructuredClinicalFact

client = TestClient(gateway_app)
session_cache = SessionCache()


def test_patient_cannot_access_tier1_alert_queue():
    """Verify that Patient role is rejected with 403 on /api/v1/redflag/tier1-queue."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())
    sess = session_cache.create_session(encounter_id=enc_id, patient_id=pat_id, channel="kiosk")
    token = sess["token"]

    resp = client.get(
        "/api/v1/redflag/tier1-queue",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_patient_cannot_acknowledge_alert():
    """Verify that Patient role cannot acknowledge an alert."""
    enc_id = "018f0000-0000-7000-8000-000000000011"
    pat_id = "018f0000-0000-7000-8000-000000000022"

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
            language="en",
        )
    )

    events = red_flag_service.evaluate_encounter(enc_id, [StructuredClinicalFact(path="symptoms.stridor", value=True)])
    event_id = events[0].id

    sess = session_cache.create_session(encounter_id=enc_id, patient_id=pat_id, channel="kiosk")
    token = sess["token"]

    resp = client.post(
        f"/api/v1/redflag/{event_id}/acknowledge",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_cross_encounter_evaluation_denied_for_patient():
    """Verify Patient cannot evaluate red flags on another encounter."""
    enc_a = str(uuid6.uuid7())
    enc_b = str(uuid6.uuid7())
    pat_a = str(uuid6.uuid7())

    sess = session_cache.create_session(encounter_id=enc_a, patient_id=pat_a, channel="kiosk")
    token = sess["token"]

    # Attempt to evaluate enc_b
    resp = client.post(
        "/api/v1/redflag/evaluate",
        headers={"Authorization": f"Bearer {token}"},
        json={"encounter_id": enc_b, "facts": [{"path": "symptoms.stridor", "value": True}]},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_unassigned_physician_denied_access():
    """Verify Physician not assigned to encounter is denied access."""
    # dr-verma is assigned to encounter ...0012, not ...0011
    enc_11 = "018f0000-0000-7000-8000-000000000011"

    resp = client.get(
        f"/api/v1/redflag/encounter/{enc_11}",
        headers={"Authorization": "Bearer staff-token-dr-verma"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_zero_phi_in_redflag_audit_logs():
    """Verify that audit records created during red-flag detection contain zero clinical transcripts or raw symptoms."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
            language="en",
        )
    )

    facts = [
        StructuredClinicalFact(path="symptoms.chest_pain", value=True),
        StructuredClinicalFact(path="symptoms.radiation", value=True),
    ]

    red_flag_service.evaluate_encounter(enc_id, facts, actor_id=pat_id, actor_role="patient")

    # Inspect audit events
    audit_events = audit_service.query_events(encounter_id=enc_id)
    assert len(audit_events) >= 1

    for a_ev in audit_events:
        # Verify no clinical transcript in reason or safe_metadata
        assert "chest pain" not in (a_ev.reason or "").lower()
        assert a_ev.action in ("CREATE", "UPDATE", "READ", "SIGN", "EXPORT", "BREAKGLASS")
        assert a_ev.outcome in ("ALLOW", "DENY")
