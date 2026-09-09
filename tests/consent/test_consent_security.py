"""
Test Suite: Consent & DPDP Security & Authorization Controls
=============================================================
Validates IDOR prevention, purpose gating policies, unauthorized role restrictions,
guardian adapter trust boundaries, and cryptographic fail-closed enforcement.
"""

from fastapi import FastAPI, Depends, status
from fastapi.testclient import TestClient
import pytest
import uuid6

from ayusetu.gateway.app import gateway_app
from ayusetu.consent.service import consent_service
from ayusetu.consent.guardian import GuardianVerificationAdapter
from ayusetu.consent.models import Purposes, ConsentGrantRequest, GuardianContext, GuardianRelationship, OfflineConsentPayload
from ayusetu.consent.policy import require_clinical_consent, require_purpose_consent
from ayusetu.consent.offline_chain import station_consent_chain
from ayusetu.common.session_cache import SessionCache

gateway_client = TestClient(gateway_app)
session_cache = SessionCache()


@pytest.fixture(autouse=True)
def clean_state():
    consent_service.reset_state()
    yield
    consent_service.reset_state()


# Create small test sub-app for dependency unit testing
policy_app = FastAPI()

@policy_app.get("/test/clinical-gate/{id}")
def endpoint_clinical_gate(enc_id: str = Depends(require_clinical_consent)):
    return {"status": "clinical_capture_permitted", "encounter_id": enc_id}

@policy_app.get("/test/research-gate/{id}")
def endpoint_research_gate(enc_id: str = Depends(require_purpose_consent("research"))):
    return {"status": "research_export_permitted", "encounter_id": enc_id}

policy_client = TestClient(policy_app)


def test_clinical_gating_dependency_allowed_when_granted():
    enc_id = str(uuid6.uuid7())
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
        )
    )

    resp = policy_client.get(f"/test/clinical-gate/{enc_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "clinical_capture_permitted"


def test_clinical_gating_dependency_denied_when_missing():
    enc_id = str(uuid6.uuid7())
    resp = policy_client.get(f"/test/clinical-gate/{enc_id}")
    assert resp.status_code == 403
    assert "Clinical processing consent is required" in resp.json()["detail"]


def test_purpose_gating_dependency_enforces_specific_purpose():
    enc_id = str(uuid6.uuid7())
    # Grant clinical=True, research=False
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, research=False),
        )
    )

    # Clinical is allowed
    assert policy_client.get(f"/test/clinical-gate/{enc_id}").status_code == 200

    # Research is denied
    research_resp = policy_client.get(f"/test/research-gate/{enc_id}")
    assert research_resp.status_code == 403
    assert "Consent for purpose 'research' has not been granted" in research_resp.json()["detail"]


# --- IDOR & Authorization Tests ---

def test_patient_cross_encounter_idor_access_denied():
    enc_a = "018f0000-0000-7000-8000-000000000011"
    enc_b = "018f0000-0000-7000-8000-000000000012"
    pat_a = str(uuid6.uuid7())
    pat_b = str(uuid6.uuid7())

    # Create consent for encounter B
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_b,
            encounter_id=enc_b,
            purposes=Purposes(clinical=True),
        )
    )

    # Patient A session on Encounter A
    sess_a = session_cache.create_session(encounter_id=enc_a, patient_id=pat_a, channel="kiosk")
    token_a = sess_a["token"]

    # Patient A tries to access Encounter B's consent -> 403
    resp = gateway_client.get(
        f"/api/v1/consent/{enc_b}",
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_patient_cross_encounter_idor_withdrawal_denied():
    enc_a = "018f0000-0000-7000-8000-000000000011"
    enc_b = "018f0000-0000-7000-8000-000000000012"
    pat_a = str(uuid6.uuid7())
    pat_b = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_b,
            encounter_id=enc_b,
            purposes=Purposes(clinical=True),
        )
    )

    sess_a = session_cache.create_session(encounter_id=enc_a, patient_id=pat_a, channel="kiosk")
    token_a = sess_a["token"]

    # Patient A attempts to withdraw Encounter B's consent -> 403
    resp = gateway_client.post(
        "/api/v1/consent/withdraw",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "encounter_id": enc_b,
            "purposes_to_withdraw": ["all"]
        }
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_patient_cross_patient_erasure_denied():
    pat_a = str(uuid6.uuid7())
    pat_b = str(uuid6.uuid7())
    enc_a = str(uuid6.uuid7())

    sess_a = session_cache.create_session(encounter_id=enc_a, patient_id=pat_a, channel="kiosk")
    token_a = sess_a["token"]

    # Patient A attempts to request erasure for Patient B -> 403
    resp = gateway_client.post(
        "/api/v1/erasure",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "patient_id": pat_b,
            "reason": "malicious_erasure_attempt"
        }
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_unassigned_physician_access_denied():
    # Encounter 11 is assigned to dr-aparna (Kayachikitsa), NOT dr-verma (Panchakarma)
    enc_11 = "018f0000-0000-7000-8000-000000000011"
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_11,
            purposes=Purposes(clinical=True),
        )
    )

    # dr-verma attempts to view consent on encounter 11 -> 403
    resp = gateway_client.get(
        f"/api/v1/consent/{enc_11}",
        headers={"Authorization": "Bearer staff-token-dr-verma"}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_companion_cannot_grant_minor_consent_without_registered_guardian():
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    # Companion session on enc_id
    sess = session_cache.create_session(encounter_id=enc_id, patient_id=pat_id, channel="pwa_companion")
    token_comp = sess["token"]

    # Companion tries to set is_minor=True with unverified guardian
    resp = gateway_client.post(
        "/api/v1/consent",
        headers={"Authorization": f"Bearer {token_comp}"},
        json={
            "patient_id": pat_id,
            "encounter_id": enc_id,
            "purposes": {"clinical": True},
            "is_minor": True,
            "guardian_context": {
                "guardian_id": "comp-actor-001",
                "guardian_name": "Companion User",
                "relationship": "parent",
                "is_verified": True  # Untrusted client boolean!
            }
        }
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"


def test_tampered_offline_chain_fails_closed_on_sync():
    enc_id = str(uuid6.uuid7())
    consent_service.capture_offline_consent(
        OfflineConsentPayload(
            patient_id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=True),
            device_id="station-01",
        )
    )

    # Tamper with the offline chain
    station_consent_chain._entries[0].payload["purposes"]["research"] = True

    # Sync attempt must fail closed
    headers = {"Authorization": "Bearer staff-token-dr-aparna"}
    sync_resp = gateway_client.post("/api/v1/consent/sync", headers=headers)
    assert sync_resp.status_code == 400
    assert sync_resp.json()["error"]["code"] == "POLICY_DENIED"
