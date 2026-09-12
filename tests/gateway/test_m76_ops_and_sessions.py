"""
M7.6 Ops Console Alert Queue, Session QR Resumption, Companion Link, and Export Tests
=====================================================================================
Validates:
1. GET /api/v1/alerts: Ops Console alert queue query by authorized staff roles
2. POST /api/v1/alerts/{id}/acknowledge: Clinician acknowledgment with disposition
3. Role enforcement on alert acknowledgment (Physician/Nurse allowed, Attendant denied)
4. POST /api/v1/sessions/{id}/resume: Claiming incomplete PWA session with QR token
5. Session QR resume error handling (invalid token -> 403, nonexistent session -> 404)
6. POST /api/v1/sessions/{id}/companion-link: Scoped companion magic link generation
7. POST /api/v1/exports: Two-Person Separation-of-Duties (SoD) de-identified export
8. Two-Person SoD self-approval rejection (403 Forbidden)
"""

import uuid
import uuid6
import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.common.session_cache import SessionCache
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.redflag.service import red_flag_service
from ayusetu.redflag.models import StructuredClinicalFact
from ayusetu.clinical.repository import ClinicalRepository


@pytest.fixture
def client():
    return TestClient(gateway_app)


@pytest.fixture
def repo():
    r = ClinicalRepository()
    r.clear_for_testing()
    return r


@pytest.fixture
def cache():
    return SessionCache()


# ---------------------------------------------------------------------------
# 1. Ops Console Alert Queue
# ---------------------------------------------------------------------------
def test_ops_alerts_queue_authorized_staff(client, repo):
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    # Grant clinical consent so red flags can evaluate
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )

    # Trigger Tier 1 red flag (RF-CARD-001: chest_pain + radiation)
    events = red_flag_service.evaluate_encounter(
        encounter_id=enc_id,
        facts=[
            StructuredClinicalFact(path="symptoms.chest_pain", value=True),
            StructuredClinicalFact(path="symptoms.radiation", value=True),
        ],
    )
    assert len(events) >= 1

    # Physician token queries alerts -> 200 OK
    resp = client.get(
        "/api/v1/alerts?tier=1&status=all",
        headers={"Authorization": "Bearer staff-token-dr-aparna"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == 1
    assert len(data["alerts"]) >= 1
    assert any(a["encounter_id"] == enc_id for a in data["alerts"])


# ---------------------------------------------------------------------------
# 2. Alert Acknowledgment with Disposition
# ---------------------------------------------------------------------------
def test_alert_acknowledgment_by_clinician(client, repo):
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )

    events = red_flag_service.evaluate_encounter(
        encounter_id=enc_id,
        facts=[
            StructuredClinicalFact(path="symptoms.chest_pain", value=True),
            StructuredClinicalFact(path="symptoms.sweating", value=True),
        ],
    )
    assert len(events) >= 1
    event_id = events[0].id

    # Nurse acknowledges alert
    resp = client.post(
        f"/api/v1/alerts/{event_id}/acknowledge",
        json={"disposition": "patient_transferred_to_icu", "notes": "Immediate ECG performed"},
        headers={"Authorization": "Bearer staff-token-nurse-sunita"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["alert_id"] == event_id
    assert data["status"] == "acknowledged"
    assert "patient_transferred_to_icu" in data["disposition"]
    assert data["acknowledged_by"] == "usr-nur-001"


# ---------------------------------------------------------------------------
# 3. Role Enforcement on Alert Acknowledgment
# ---------------------------------------------------------------------------
def test_alert_acknowledgment_role_enforcement(client):
    event_id = str(uuid6.uuid7())

    # Attendant cannot acknowledge alert (403 Forbidden)
    resp = client.post(
        f"/api/v1/alerts/{event_id}/acknowledge",
        json={"disposition": "verified"},
        headers={"Authorization": "Bearer staff-token-attendant-ravi"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 4. Session Resume via QR Code
# ---------------------------------------------------------------------------
def test_session_resume_via_qr(client, cache):
    enc_id = uuid.uuid4()
    sess = cache.create_session(encounter_id=enc_id, channel="pwa_self")
    sess_id = sess["session_id"]
    token = sess["token"]

    resp = client.post(
        f"/api/v1/sessions/{sess_id}/resume",
        json={"token": token, "station_id": "station_ayush_01"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sess_id
    assert data["status"] == "resumed"
    assert data["claimed_by_station"] == "station_ayush_01"


# ---------------------------------------------------------------------------
# 5. Session Resume Error Handling
# ---------------------------------------------------------------------------
def test_session_resume_errors(client, cache):
    enc_id = uuid.uuid4()
    sess = cache.create_session(encounter_id=enc_id)
    sess_id = sess["session_id"]

    # Invalid QR token -> 403 Forbidden
    resp_invalid = client.post(
        f"/api/v1/sessions/{sess_id}/resume",
        json={"token": "invalid_wrong_token", "station_id": "station_01"},
    )
    assert resp_invalid.status_code == 403

    # Nonexistent session -> 404 Not Found
    resp_missing = client.post(
        f"/api/v1/sessions/{uuid.uuid4()}/resume",
        json={"token": "some_token"},
    )
    assert resp_missing.status_code == 404


# ---------------------------------------------------------------------------
# 6. Companion Link Issuance
# ---------------------------------------------------------------------------
def test_companion_link_issuance(client, cache):
    enc_id = uuid.uuid4()
    sess = cache.create_session(encounter_id=enc_id)
    sess_id = sess["session_id"]

    resp = client.post(
        f"/api/v1/sessions/{sess_id}/companion-link",
        json={"nominated_mobile": "+919876543210", "relationship": "spouse"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == sess_id
    assert data["nominated_mobile"] == "+919876543210"
    assert data["relationship"] == "spouse"
    assert "/pwa/companion/" in data["magic_link"]
    assert "token=" in data["magic_link"]


# ---------------------------------------------------------------------------
# 7. Two-Person SoD De-Identified Export
# ---------------------------------------------------------------------------
def test_deid_export_two_person_authorization(client):
    # Requester is staff-token-mrd-officer (usr-mrd-001)
    # Approver 1 is usr-adm-001, Approver 2 is usr-phy-001 (distinct from each other and requester)
    resp = client.post(
        "/api/v1/exports",
        json={
            "date_from": "2025-01-01",
            "date_to": "2025-12-31",
            "purpose": "research",
            "approver_1": "usr-adm-001",
            "approver_2": "usr-phy-001",
        },
        headers={"Authorization": "Bearer staff-token-mrd-officer"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "export_id" in data
    assert data["status"] in ("pending_processing", "completed")


# ---------------------------------------------------------------------------
# 8. Two-Person SoD Duplicate Approvers Rejection
# ---------------------------------------------------------------------------
def test_deid_export_duplicate_approvers_rejected(client):
    resp = client.post(
        "/api/v1/exports",
        json={
            "date_from": "2025-01-01",
            "date_to": "2025-12-31",
            "purpose": "research",
            "approver_1": "usr-adm-001",
            "approver_2": "usr-adm-001",  # Same approver -> SoD violation
        },
        headers={"Authorization": "Bearer staff-token-mrd-officer"},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["error"]["code"] == "POLICY_DENIED"
