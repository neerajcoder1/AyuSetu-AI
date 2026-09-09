"""
Test Suite: ABAC Encounter Scoping & IDOR Protection
=====================================================
Validates encounter-level authorization, cross-patient IDOR blocking, and temporal scoping.
"""

import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.abac import ABACEvaluator
from ayusetu.gateway.auth.models import (
    Action,
    AuthContext,
    Principal,
    Resource,
    Role,
)

client = TestClient(gateway_app)


def test_physician_unassigned_encounter_denied():
    # Dr. Aparna has assigned encounter 018f...0011 and 0012, but NOT 0013
    headers = {"Authorization": "Bearer staff-token-dr-aparna"}
    unassigned_enc = "018f0000-0000-7000-8000-000000000099"
    response = client.get(f"/api/v1/encounters/{unassigned_enc}/summary", headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "POLICY_DENIED"


def test_patient_cross_encounter_idor_prevention():
    # Patient A with encounter 1
    p_a = Principal(
        actor_id="pat-a",
        role=Role.PATIENT,
        patient_id="pat-a",
        encounter_id="018f0000-0000-7000-8000-000000000001"
    )

    # Patient A attempts to read Patient B's encounter (018f...0002)
    ctx_idor = AuthContext(
        principal=p_a,
        resource=Resource.OWN_DRAFT_SESSION,
        action=Action.READ,
        target_encounter_id="018f0000-0000-7000-8000-000000000002"
    )

    allowed, reason = ABACEvaluator.evaluate(ctx_idor)
    assert allowed is False
    assert "foreign encounter" in reason.lower()


def test_temporal_scope_expiration():
    # Physician reading signed record past 72-hour window
    phy = Principal(
        actor_id="usr-phy-001",
        role=Role.PHYSICIAN,
        assigned_encounter_ids={"018f0000-0000-7000-8000-000000000011"}
    )

    # Encounter is 80 hours old (>72h)
    ctx_expired = AuthContext(
        principal=phy,
        resource=Resource.SIGNED_CLINICAL_RECORD,
        action=Action.READ,
        target_encounter_id="018f0000-0000-7000-8000-000000000011",
        encounter_age_hours=80.0
    )

    allowed, reason = ABACEvaluator.evaluate(ctx_expired)
    assert allowed is False
    assert "72 hours" in reason

    # MRD role is exempt from 72h temporal limit per PRD §21.4
    mrd = Principal(actor_id="usr-mrd-001", role=Role.MRD)
    ctx_mrd = AuthContext(
        principal=mrd,
        resource=Resource.SIGNED_CLINICAL_RECORD,
        action=Action.READ,
        target_encounter_id="018f0000-0000-7000-8000-000000000011",
        encounter_age_hours=80.0
    )
    mrd_allowed, _ = ABACEvaluator.evaluate(ctx_mrd)
    assert mrd_allowed is True


def test_separation_of_duties_clinical_content():
    # Admin who authors content cannot self-approve per PRD §21.4
    admin = Principal(actor_id="usr-adm-001", role=Role.ADMIN)
    ctx_self_approve = AuthContext(
        principal=admin,
        resource=Resource.CLINICAL_CONTENT,
        action=Action.UPDATE,
        is_author=True
    )

    allowed, reason = ABACEvaluator.evaluate(ctx_self_approve)
    assert allowed is False
    assert "author cannot approve" in reason.lower()
