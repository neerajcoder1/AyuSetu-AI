from fastapi.testclient import TestClient
import pytest

from ayusetu.gateway.app import gateway_app
from ayusetu.audit.app import audit_app
from ayusetu.audit.service import audit_service
from ayusetu.audit.models import AuditAction, AuditOutcome
from ayusetu.gateway.auth.event_hooks import dispatch_security_event
from ayusetu.consent.event_hooks import (
    emit_consent_granted,
    emit_consent_withdrawn,
    emit_erasure_requested,
)

client = TestClient(gateway_app)
audit_client = TestClient(audit_app)


def test_auditor_can_access_audit_endpoints():
    """Verify that Auditor role can access /api/v1/audit/head, /events, /verify."""
    # Seed an event
    audit_service.record_event(
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="Physician",
        action=AuditAction.READ,
        resource_type="Encounter",
        resource_id="018f0000-0000-7000-8000-000000000010",
    )

    headers = {"Authorization": "Bearer staff-token-auditor-certin"}

    # 1. Head
    resp_head = client.get("/api/v1/audit/head", headers=headers)
    assert resp_head.status_code == 200
    assert resp_head.json()["seq"] == 1

    # 2. Events
    resp_events = client.get("/api/v1/audit/events", headers=headers)
    assert resp_events.status_code == 200
    assert len(resp_events.json()) == 1

    # 3. Verify
    resp_verify = client.get("/api/v1/audit/verify", headers=headers)
    assert resp_verify.status_code == 200
    assert resp_verify.json()["valid"] is True


def test_patient_cannot_access_audit_endpoints():
    """Verify that Patient role is rejected with 403 on all audit query endpoints."""
    # Setup patient session
    sess_resp = client.post("/api/v1/sessions", json={"device_id": "test-kiosk-01"})
    session_id = sess_resp.json()["session_id"]
    headers = {"X-Session-ID": session_id}

    resp_head = client.get("/api/v1/audit/head", headers=headers)
    assert resp_head.status_code == 403

    resp_events = client.get("/api/v1/audit/events", headers=headers)
    assert resp_events.status_code == 403

    resp_verify = client.get("/api/v1/audit/verify", headers=headers)
    assert resp_verify.status_code == 403


def test_physician_cannot_access_audit_endpoints():
    """Verify that clinical staff (Physician) is blocked from audit query endpoints."""
    headers = {"Authorization": "Bearer staff-token-dr-aparna"}

    resp_head = client.get("/api/v1/audit/head", headers=headers)
    assert resp_head.status_code == 403

    resp_events = client.get("/api/v1/audit/events", headers=headers)
    assert resp_events.status_code == 403


def test_idor_attempt_automatically_audited():
    """Verify that triggering an IDOR attempt automatically appends a DENY audit record."""
    dispatch_security_event(
        event_type="IDOR_ATTEMPT",
        actor_id="018f0000-0000-7000-8000-000000000099",
        actor_role="patient",
        target_resource="Encounter",
        target_encounter_id="018f0000-0000-7000-8000-000000000011",
        reason="Cross-encounter access attempt",
    )

    events = audit_service.query_events(action="READ")
    assert len(events) >= 1
    idor_ev = events[-1]
    assert idor_ev.outcome == "DENY"
    assert "IDOR_ATTEMPT" in str(idor_ev.reason)


def test_break_glass_automatically_audited():
    """Verify that break-glass access dispatches an audit event with BREAKGLASS action."""
    dispatch_security_event(
        event_type="BREAK_GLASS",
        actor_id="018f0000-0000-7000-8000-000000000001",
        actor_role="physician",
        target_resource="Encounter",
        target_encounter_id="018f0000-0000-7000-8000-000000000011",
        reason="Patient unconscious in emergency room",
    )

    events = audit_service.query_events(action="BREAKGLASS")
    assert len(events) >= 1
    bg_ev = events[-1]
    assert bg_ev.action == "BREAKGLASS"
    assert bg_ev.outcome == "ALLOW"
    assert "Patient unconscious" in str(bg_ev.reason)


def test_consent_lifecycle_events_automatically_audited():
    """Verify M4 consent grant, withdrawal, and erasure automatically dispatch to audit chain."""
    enc_id = "018f0000-0000-7000-8000-000000000011"
    pat_id = "018f0000-0000-7000-8000-000000000022"

    # 1. Grant
    emit_consent_granted(
        patient_id=pat_id,
        encounter_id=enc_id,
        consent_id="018f0000-0000-7000-8000-000000000033",
        purposes={"clinical": True, "abdm": True, "qi": False, "research": False},
        notice_version="v2.0",
        actor_id=pat_id,
    )

    # 2. Withdraw
    emit_consent_withdrawn(
        patient_id=pat_id,
        encounter_id=enc_id,
        consent_id="018f0000-0000-7000-8000-000000000033",
        withdrawn_purposes=["abdm"],
        remaining_purposes={"clinical": True, "abdm": False, "qi": False, "research": False},
        actor_id=pat_id,
        reason="Patient revoked ABDM sharing",
    )

    # 3. Erasure
    emit_erasure_requested(
        request_id="018f0000-0000-7000-8000-000000000044",
        patient_id=pat_id,
        encounter_id=enc_id,
        actor_id=pat_id,
        reason="Right to be forgotten request",
    )

    # Query events
    all_events = audit_service.query_events()
    assert len(all_events) == 3

    # Verification must pass
    verif = audit_service.verify_global_chain()
    assert verif.valid is True
    assert verif.checked_events == 3


def test_audit_verifier_detects_server_side_tampering():
    """Verify that tampering with an in-memory or persisted audit record is detected by verifier."""
    # Record 3 events
    for i in range(3):
        audit_service.record_event(
            actor_id=f"018f0000-0000-7000-8000-00000000000{i}",
            actor_role="Physician",
            action=AuditAction.READ,
            resource_type="Encounter",
            resource_id="018f0000-0000-7000-8000-000000000010",
        )

    # Tamper with event 2 in the persisted database table
    repo = audit_service._repo
    with repo._session_factory() as db:
        from ayusetu.common.models import AuditEvent
        ev2 = db.query(AuditEvent).filter(AuditEvent.seq == 2).first()
        assert ev2 is not None
        ev2.outcome = "DENY"
        db.commit()

    # Run verification
    verif = audit_service.verify_global_chain()
    assert verif.valid is False
    assert verif.last_valid_sequence == 1
    assert verif.failure is not None
    assert verif.failure["code"] == "ENTRY_HASH_TAMPERED"
    assert verif.failure["sequence"] == 2


def test_offline_sync_cross_device_impersonation_rejected_at_api():
    """Verify that a device with fingerprint fp-station-01 cannot sync a batch claiming station-victim-02."""
    headers = {
        "Authorization": "Bearer staff-token-nurse-sunita",
        "X-Device-Fingerprint": "station-genuine-01",
    }
    payload = {
        "device_id": "station-victim-02",  # Mismatched claimed device
        "seed_head_hash": "0" * 64,
        "events": [],
    }
    resp = client.post("/api/v1/audit/offline/sync", json=payload, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_offline_sync_patient_role_rejected_at_api():
    """Verify that a patient session cannot submit an offline audit sync batch."""
    sess_resp = client.post("/api/v1/sessions", json={"device_id": "test-kiosk-01"})
    session_id = sess_resp.json()["session_id"]
    headers = {"X-Session-ID": session_id}

    payload = {
        "device_id": "test-kiosk-01",
        "seed_head_hash": "0" * 64,
        "events": [],
    }
    resp = client.post("/api/v1/audit/offline/sync", json=payload, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"

