"""
Test Suite: RBAC Matrix Verification
====================================
Validates all 8 PRD roles, permission matrix mapping, and deny-by-default.
"""

import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.rbac import RBACPolicy
from ayusetu.gateway.auth.models import Role, Resource, Action

client = TestClient(gateway_app)


def test_all_8_prd_roles_exist():
    expected_roles = {
        "patient", "companion", "attendant", "nurse",
        "physician", "mrd", "admin", "auditor"
    }
    actual_roles = {r.value for r in Role}
    assert actual_roles == expected_roles


def test_rbac_matrix_static_evaluations():
    # Physician can read, update, and sign clinical records
    assert RBACPolicy.is_permitted(Role.PHYSICIAN, Resource.SIGNED_CLINICAL_RECORD, Action.READ)
    assert RBACPolicy.is_permitted(Role.PHYSICIAN, Resource.SIGNED_CLINICAL_RECORD, Action.UPDATE)
    assert RBACPolicy.is_permitted(Role.PHYSICIAN, Resource.SIGNED_CLINICAL_RECORD, Action.SIGN)

    # Nurse can read but cannot sign clinical records
    assert RBACPolicy.is_permitted(Role.NURSE, Resource.SIGNED_CLINICAL_RECORD, Action.READ)
    assert not RBACPolicy.is_permitted(Role.NURSE, Resource.SIGNED_CLINICAL_RECORD, Action.SIGN)

    # Auditor cannot modify or sign any clinical record
    assert not RBACPolicy.is_permitted(Role.AUDITOR, Resource.SIGNED_CLINICAL_RECORD, Action.UPDATE)
    assert not RBACPolicy.is_permitted(Role.AUDITOR, Resource.SIGNED_CLINICAL_RECORD, Action.SIGN)
    assert not RBACPolicy.is_permitted(Role.AUDITOR, Resource.CLINICAL_CONTENT, Action.UPDATE)
    # Auditor can read audit log
    assert RBACPolicy.is_permitted(Role.AUDITOR, Resource.AUDIT_LOG, Action.READ)

    # Patient can only read/update own draft and consent
    assert RBACPolicy.is_permitted(Role.PATIENT, Resource.CONSENT_RECORD, Action.CREATE)
    assert not RBACPolicy.is_permitted(Role.PATIENT, Resource.TIER1_ALERT_QUEUE, Action.READ)

    # Companion cannot create consent record alone per PRD §21.4
    assert not RBACPolicy.is_permitted(Role.COMPANION, Resource.CONSENT_RECORD, Action.CREATE)


def test_physician_can_access_summary():
    headers = {"Authorization": "Bearer staff-token-dr-aparna"}
    # Assigned encounter
    enc_id = "018f0000-0000-7000-8000-000000000011"
    response = client.get(f"/api/v1/encounters/{enc_id}/summary", headers=headers)
    assert response.status_code == 200
    assert response.json()["encounter_id"] == enc_id


def test_auditor_cannot_sign_summary():
    headers = {"Authorization": "Bearer staff-token-auditor-certin"}
    enc_id = "018f0000-0000-7000-8000-000000000011"
    response = client.post(
        f"/api/v1/encounters/{enc_id}/sign",
        headers=headers,
        json={"physician_id": "usr-aud-001"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_DENIED"


def test_mrd_can_request_export():
    headers = {"Authorization": "Bearer staff-token-mrd-officer"}
    response = client.post("/api/v1/exports", headers=headers, json={
        "date_from": "2026-01-01",
        "date_to": "2026-09-01",
        "approver_1": "usr-mrd-001",
        "approver_2": "usr-aud-001"
    })
    assert response.status_code == 202
    assert response.json()["k_anonymity_threshold"] == 5


def test_nurse_cannot_request_export():
    headers = {"Authorization": "Bearer staff-token-nurse-sunita"}
    response = client.post("/api/v1/exports", headers=headers, json={
        "date_from": "2026-01-01",
        "date_to": "2026-09-01",
        "approver_1": "usr-nur-001",
        "approver_2": "usr-nur-002"
    })
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_DENIED"
