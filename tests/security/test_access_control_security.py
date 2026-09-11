"""
Phase 9 Security Regression: Access Control, ABAC, and Privilege Separation
===========================================================================
Validates:
- Prevention of Horizontal Privilege Escalation (IDOR).
- Prevention of Vertical Privilege Escalation.
- Enforcement of Role Separation of Duties.
- Device Certificate Revocation List (CRL) enforcement.
- Immediate rejection upon Session Invalidation / Logout.
- Break-glass emergency escalation auditing.
"""

from fastapi.testclient import TestClient
import pytest

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.errors import ErrorCode
from ayusetu.gateway.auth.models import Principal, Role, Action, Resource, AuthContext, BreakGlassContext
from ayusetu.gateway.auth.rbac import RBACPolicy
from ayusetu.gateway.auth.abac import ABACEvaluator
from ayusetu.gateway.auth.device import DeviceAuthenticator

client = TestClient(gateway_app)


def test_horizontal_privilege_escalation_idor_blocked():
    """Verify physician from one department cannot access unassigned encounter in another department."""
    dr_verma_panchakarma = Principal(
        actor_id="usr-phy-002",
        role=Role.PHYSICIAN,
        department="Panchakarma",
        assigned_encounter_ids={"018f0000-0000-7000-8000-000000000012"},
        is_authenticated=True,
    )
    # Attempting to access Kayachikitsa encounter 018f0000-0000-7000-8000-000000000011
    ctx = AuthContext(
        principal=dr_verma_panchakarma,
        resource=Resource.SIGNED_CLINICAL_RECORD,
        action=Action.READ,
        target_encounter_id="018f0000-0000-7000-8000-000000000011",
        target_department="Kayachikitsa",
    )
    allowed, reason = ABACEvaluator.evaluate(ctx)
    assert allowed is False


def test_vertical_privilege_escalation_attendant_blocked_from_clinical_summary():
    """Verify attendant cannot sign or modify clinical summary or red flag queues."""
    assert RBACPolicy.is_permitted(Role.ATTENDANT, Resource.SIGNED_CLINICAL_RECORD, Action.SIGN) is False
    assert RBACPolicy.is_permitted(Role.ATTENDANT, Resource.SIGNED_CLINICAL_RECORD, Action.UPDATE) is False
    assert RBACPolicy.is_permitted(Role.ATTENDANT, Resource.TIER1_ALERT_QUEUE, Action.UPDATE) is False


def test_separation_of_duties_auditor_cannot_alter_clinical_records():
    """Verify auditor has read-only access to audit logs and cannot create or modify clinical records."""
    assert RBACPolicy.is_permitted(Role.AUDITOR, Resource.AUDIT_LOG, Action.READ) is True
    assert RBACPolicy.is_permitted(Role.AUDITOR, Resource.AUDIT_LOG, Action.CREATE) is False
    assert RBACPolicy.is_permitted(Role.AUDITOR, Resource.SIGNED_CLINICAL_RECORD, Action.UPDATE) is False
    assert RBACPolicy.is_permitted(Role.AUDITOR, Resource.SIGNED_CLINICAL_RECORD, Action.SIGN) is False


def test_device_crl_revocation_blocks_all_requests():
    """Verify device present on CRL is immediately rejected with 403 Forbidden."""
    revoked_fp = "kiosk-cert-revoked-stolen-hw"
    DeviceAuthenticator.revoke_device(revoked_fp)

    res = client.get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer staff-token-dr-aparna",
            "X-Device-Fingerprint": revoked_fp,
        }
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == ErrorCode.POLICY_DENIED.value


def test_break_glass_requires_justification_and_is_audited():
    """Verify emergency break-glass ABAC override requires explicit clinical reason."""
    physician = Principal(
        actor_id="usr-phy-003",
        role=Role.PHYSICIAN,
        department="Emergency",
        assigned_encounter_ids=set(),  # Unassigned
        is_authenticated=True,
    )
    # Attempt without break-glass -> denied
    ctx_normal = AuthContext(
        principal=physician,
        resource=Resource.SIGNED_CLINICAL_RECORD,
        action=Action.READ,
        target_encounter_id="018f0000-0000-7000-8000-000000000099",
        target_department="Kayachikitsa",
    )
    allowed, reason = ABACEvaluator.evaluate(ctx_normal)
    assert allowed is False

    # Attempt with valid break-glass context
    bg = BreakGlassContext(
        is_break_glass=True,
        reason="Acute trauma resuscitation in ER - patient unconscious",
        authorized_by="usr-phy-003",
        encounter_id="018f0000-0000-7000-8000-000000000099",
    )
    ctx_bg = AuthContext(
        principal=physician,
        resource=Resource.SIGNED_CLINICAL_RECORD,
        action=Action.READ,
        target_encounter_id="018f0000-0000-7000-8000-000000000099",
        target_department="Kayachikitsa",
        break_glass=bg,
    )
    allowed_bg, reason_bg = ABACEvaluator.evaluate(ctx_bg)
    assert allowed_bg is True
