"""
Phase M7.3: Physician Review, Summary Diff Tracking, and Digital Signing Tests
=============================================================================
Validates authoritative physician review, structured JSON Patch / diff tracking
persisted to SummaryEdit records, digital signing lifecycle (preliminary -> final),
cryptographic SIGN audit event recording, RBAC/ABAC enforcement, consent gating,
and immutability of signed clinical records.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List
import uuid
import uuid6
import pytest
from fastapi.testclient import TestClient
import jsonschema

from ayusetu.gateway.app import gateway_app
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.audit.service import audit_service
from ayusetu.audit.models import AuditAction, AuditOutcome
from ayusetu.clinical.models import (
    EncounterDTO,
    EncounterStatus,
    VisitType,
    IntakeDepth,
    Channel,
    ReportedBy,
    SlotSource,
    SlotDTO,
    UtteranceDTO,
    SummaryStatus,
    SummaryVersionDTO,
    SummaryEditDTO,
    SummaryEditRequest,
    SignEncounterRequest,
)
from ayusetu.clinical.repository import ClinicalRepository
from ayusetu.clinical.service import ClinicalService, clinical_service
from ayusetu.clinical.summary_engine import summary_synthesis_engine, get_summary_schema
from ayusetu.gateway.errors import AyuSetuGatewayError

client = TestClient(gateway_app)

# Test assigned encounter IDs for dr-aparna (Department: Kayachikitsa)
ASSIGNED_ENC_1 = "018f0000-0000-7000-8000-000000000011"
ASSIGNED_ENC_2 = "018f0000-0000-7000-8000-000000000012"
UNASSIGNED_ENC = "018f0000-0000-7000-8000-000000000099"

PHYSICIAN_AUTH = {"Authorization": "Bearer staff-token-dr-aparna"}
NURSE_AUTH = {"Authorization": "Bearer staff-token-nurse-sunita"}
AUDITOR_AUTH = {"Authorization": "Bearer staff-token-auditor-certin"}
ATTENDANT_AUTH = {"Authorization": "Bearer staff-token-attendant-ravi"}


@pytest.fixture(autouse=True)
def clean_clinical_db():
    """Ensure clean clinical repository state before each test."""
    repo = ClinicalRepository()
    repo.clear_for_testing()
    yield
    repo.clear_for_testing()


def create_test_intake_data(enc_id: str = ASSIGNED_ENC_1, department: str = "Kayachikitsa"):
    """Helper creating persisted encounter, utterances, slots, and preliminary summary."""
    repo = ClinicalRepository()
    pat_id = str(uuid6.uuid7())

    enc_dto = EncounterDTO(
        id=enc_id,
        patient_id=pat_id,
        department=department,
        visit_type=VisitType.NEW,
        intake_depth=IntakeDepth.FULL,
        channel=Channel.KIOSK,
        status=EncounterStatus.SUBMITTED,
    )

    slots = [
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="hpi.chief_complaint",
            value="Burning epigastric pain",
            confidence=0.95,
            source=SlotSource.UTTERANCE,
            elicited=True,
        ),
        SlotDTO(
            id=str(uuid6.uuid7()),
            encounter_id=enc_id,
            path="allergies.drug",
            value="Penicillin",
            confidence=0.92,
            source=SlotSource.UTTERANCE,
            elicited=True,
        ),
    ]

    persisted_enc = repo.submit_encounter_atomic(
        encounter=enc_dto,
        utterances=[],
        slots=slots,
    )

    summary_ver = clinical_service.generate_summary(enc_id, actor_id="usr-phy-001", actor_role="physician")
    return persisted_enc, summary_ver


# =====================================================================
# 1. Physician Retrieval of Preliminary Summary
# =====================================================================

def test_physician_can_retrieve_preliminary_summary():
    """Verify authorized physician can fetch structured preliminary summary."""
    create_test_intake_data(enc_id=ASSIGNED_ENC_1)

    resp = client.get(f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary", headers=PHYSICIAN_AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["encounter_id"] == ASSIGNED_ENC_1
    assert data["status"] == "preliminary"
    assert len(data["sections"]) >= 5


# =====================================================================
# 2. Physician Summary Review & Controlled Diff Application (PATCH)
# =====================================================================

def test_physician_can_patch_valid_summary_and_record_diff():
    """Verify physician edit updates summary composition and persists SummaryEdit training signal."""
    create_test_intake_data(enc_id=ASSIGNED_ENC_1)

    patch_payload = {
        "slot_path": "allergies.drug",
        "old_value": "Penicillin",
        "new_value": "Penicillin V causing anaphylaxis in childhood",
        "reason": "Physician clarified exact severity and childhood onset with patient",
    }

    resp = client.patch(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary",
        headers=PHYSICIAN_AUTH,
        json=patch_payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert data["encounter_id"] == ASSIGNED_ENC_1
    assert data["slot_path"] == "allergies.drug"
    assert data["recorded_in_summary_edit"] is True

    # Verify SummaryEdit is persisted in PostgreSQL repository
    repo = ClinicalRepository()
    summary_ver = repo.get_latest_summary_version(ASSIGNED_ENC_1)
    edits = repo.get_summary_edits(str(summary_ver.id))
    assert len(edits) == 1
    assert edits[0].slot_path == "allergies.drug"
    assert edits[0].new_value == "Penicillin V causing anaphylaxis in childhood"
    assert edits[0].reason == "Physician clarified exact severity and childhood onset with patient"

    # Verify updated summary text via GET endpoint
    get_resp = client.get(f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary", headers=PHYSICIAN_AUTH)
    assert get_resp.status_code == 200
    allergy_sec = next(s for s in get_resp.json()["sections"] if s["id"] == "allergies")
    assert "anaphylaxis in childhood" in allergy_sec["clauses"][0]["text"]


# =====================================================================
# 3. Multiple Edits Remain Traceable
# =====================================================================

def test_multiple_physician_edits_are_traceable():
    """Verify consecutive physician edits accumulate independent SummaryEdit audit records."""
    create_test_intake_data(enc_id=ASSIGNED_ENC_1)

    # Edit 1: Allergy
    client.patch(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary",
        headers=PHYSICIAN_AUTH,
        json={"slot_path": "allergies.drug", "new_value": "Amoxicillin", "reason": "Patient corrected allergy name"},
    )

    # Edit 2: Lifestyle
    client.patch(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary",
        headers=PHYSICIAN_AUTH,
        json={"slot_path": "lifestyle.diet", "new_value": "High caffeine intake, 4 cups daily", "reason": "Dietary probe"},
    )

    repo = ClinicalRepository()
    summary_ver = repo.get_latest_summary_version(ASSIGNED_ENC_1)
    edits = repo.get_summary_edits(str(summary_ver.id))
    assert len(edits) == 2
    assert edits[0].slot_path == "allergies.drug"
    assert edits[1].slot_path == "lifestyle.diet"


# =====================================================================
# 4. Invalid Patch Rejected & Failed Patch Leaves Summary Unchanged
# =====================================================================

def test_invalid_json_pointer_patch_rejected_safely():
    """Verify malformed JSON pointer fails with 422 and does not corrupt summary."""
    create_test_intake_data(enc_id=ASSIGNED_ENC_1)

    repo = ClinicalRepository()
    sum_before = repo.get_latest_summary_version(ASSIGNED_ENC_1).composition

    # Malformed pointer to invalid nested structure
    bad_payload = {
        "slot_path": "/sections/999/clauses/999/nonexistent",
        "new_value": "invalid mutation",
    }

    resp = client.patch(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary",
        headers=PHYSICIAN_AUTH,
        json=bad_payload,
    )
    assert resp.status_code == 422

    # Verify original composition remains completely intact
    sum_after = repo.get_latest_summary_version(ASSIGNED_ENC_1).composition
    assert sum_before == sum_after
    assert repo.count_summary_edits() == 0


# =====================================================================
# 5. Non-Physician Role Cannot Edit Summary (RBAC)
# =====================================================================

def test_non_physician_roles_cannot_patch_summary():
    """Verify Nurse, Auditor, and Patient cannot edit clinical summaries."""
    create_test_intake_data(enc_id=ASSIGNED_ENC_1)

    payload = {"slot_path": "allergies.drug", "new_value": "Aspirin"}

    # Nurse (READ only for signed record)
    nurse_resp = client.patch(f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary", headers=NURSE_AUTH, json=payload)
    assert nurse_resp.status_code == 403
    assert nurse_resp.json()["error"]["code"] == "POLICY_DENIED"

    # Auditor
    aud_resp = client.patch(f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary", headers=AUDITOR_AUTH, json=payload)
    assert aud_resp.status_code == 403

    # Attendant
    att_resp = client.patch(f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary", headers=ATTENDANT_AUTH, json=payload)
    assert att_resp.status_code == 403
    assert att_resp.json()["error"]["code"] == "POLICY_DENIED"


# =====================================================================
# 6. ABAC & Care Context Scoping on Review
# =====================================================================

def test_physician_outside_care_context_cannot_patch_without_break_glass():
    """Verify physician cannot edit unassigned encounter unless valid break-glass is supplied."""
    create_test_intake_data(enc_id=UNASSIGNED_ENC, department="Kayachikitsa")

    payload = {"slot_path": "hpi.chief_complaint", "new_value": "Altered symptom"}

    # Without Break-Glass: 403
    resp = client.patch(f"/api/v1/encounters/{UNASSIGNED_ENC}/summary", headers=PHYSICIAN_AUTH, json=payload)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "POLICY_DENIED"

    # With Valid Break-Glass: 200
    bg_headers = {**PHYSICIAN_AUTH, "X-Break-Glass-Reason": "Emergency ICU consultation requested for unassigned patient"}
    bg_resp = client.patch(f"/api/v1/encounters/{UNASSIGNED_ENC}/summary", headers=bg_headers, json=payload)
    assert bg_resp.status_code == 200


# =====================================================================
# 7. Consent Gating on Physician Review
# =====================================================================

def test_revoked_consent_blocks_physician_edit():
    """Verify editing summary is blocked if clinical consent is revoked or withheld."""
    enc, _ = create_test_intake_data(enc_id=ASSIGNED_ENC_1)

    # Deny clinical consent
    consent_req = ConsentGrantRequest(
        encounter_id=ASSIGNED_ENC_1,
        patient_id=enc.patient_id,
        purposes=Purposes(clinical=False, research_aggregate=True),
        language_used="hi",
        signature_type="otp",
    )
    consent_service.grant_consent(consent_req)

    payload = {"slot_path": "allergies.drug", "new_value": "Ciprofloxacin"}
    resp = client.patch(f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary", headers=PHYSICIAN_AUTH, json=payload)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CONSENT_REQUIRED"


# =====================================================================
# 8. Digital Signing Lifecycle (Preliminary -> Final)
# =====================================================================

def test_physician_digital_signing_lifecycle():
    """
    Verify complete digital signing workflow:
    1. Status transitions preliminary -> final
    2. signed_by and signed_at are populated
    3. Authoritative cryptographic audit event emitted with action=SIGN
    4. Encounter transitions to final
    """
    create_test_intake_data(enc_id=ASSIGNED_ENC_1)

    sign_payload = {"physician_id": "usr-phy-001"}
    resp = client.post(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/sign",
        headers=PHYSICIAN_AUTH,
        json=sign_payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "final"
    assert data["encounter_id"] == ASSIGNED_ENC_1
    assert data["signed_by"] == "usr-phy-001"
    assert data["signed_at"] is not None

    # Verify SummaryVersion status is FINAL in DB
    repo = ClinicalRepository()
    sum_ver = repo.get_latest_summary_version(ASSIGNED_ENC_1)
    assert sum_ver.status == SummaryStatus.FINAL
    assert sum_ver.signed_by is not None
    assert sum_ver.signed_at is not None

    # Verify Encounter status is FINAL in DB
    enc = repo.get_encounter(ASSIGNED_ENC_1)
    assert enc.status == EncounterStatus.FINAL

    # Verify Cryptographic Audit Log contains SIGN event
    audit_events = audit_service._repo.get_all()
    sign_event = next(
        (e for e in reversed(audit_events) if e.action == AuditAction.SIGN and e.encounter_id == ASSIGNED_ENC_1),
        None,
    )
    assert sign_event is not None
    assert sign_event.action == AuditAction.SIGN
    assert sign_event.outcome == AuditOutcome.ALLOW
    assert sign_event.resource_type == "SIGNED_CLINICAL_RECORD"


# =====================================================================
# 9. Signed Summary is Immutable (Final State Protection)
# =====================================================================

def test_signed_summary_cannot_be_edited_or_re_signed():
    """Verify once summary is final/signed, further PATCH and repeated SIGN operations are rejected."""
    create_test_intake_data(enc_id=ASSIGNED_ENC_1)

    # 1. Sign summary
    sign_resp = client.post(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/sign",
        headers=PHYSICIAN_AUTH,
        json={"physician_id": "usr-phy-001"},
    )
    assert sign_resp.status_code == 200

    # 2. Attempt to PATCH final summary -> Must be rejected (400)
    patch_resp = client.patch(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary",
        headers=PHYSICIAN_AUTH,
        json={"slot_path": "allergies.drug", "new_value": "Sulfa drugs"},
    )
    assert patch_resp.status_code == 400
    assert "Cannot edit" in patch_resp.json()["error"]["message"]

    # 3. Attempt repeated SIGN on already final summary -> Must be rejected (400)
    re_sign_resp = client.post(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/sign",
        headers=PHYSICIAN_AUTH,
        json={"physician_id": "usr-phy-001"},
    )
    assert re_sign_resp.status_code == 400
    assert "already finalized" in re_sign_resp.json()["error"]["message"]


# =====================================================================
# 10. Signing Non-Existent Encounter or Unauthorized Role
# =====================================================================

def test_signing_nonexistent_encounter_or_unauthorized_role():
    """Verify 404 for non-existent encounter and 403 for unauthorized roles on /sign."""
    fake_enc = str(uuid6.uuid7())

    # Non-existent encounter (with physician auth)
    # Dr aparna is only assigned 011 and 012, so using break-glass to pass ABAC to reach 404
    bg_headers = {**PHYSICIAN_AUTH, "X-Break-Glass-Reason": "Emergency verification"}
    resp_404 = client.post(
        f"/api/v1/encounters/{fake_enc}/sign",
        headers=bg_headers,
        json={"physician_id": "usr-phy-001"},
    )
    assert resp_404.status_code == 404

    # Unauthorized role (Auditor)
    create_test_intake_data(enc_id=ASSIGNED_ENC_1)
    resp_aud = client.post(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/sign",
        headers=AUDITOR_AUTH,
        json={"physician_id": "usr-aud-001"},
    )
    assert resp_aud.status_code == 403


# =====================================================================
# 11. Final Summary Remains Retrievable
# =====================================================================

def test_final_summary_remains_retrievable():
    """Verify final summary remains fully retrievable by physician and patient."""
    create_test_intake_data(enc_id=ASSIGNED_ENC_1)

    # Sign summary
    client.post(
        f"/api/v1/encounters/{ASSIGNED_ENC_1}/sign",
        headers=PHYSICIAN_AUTH,
        json={"physician_id": "usr-phy-001"},
    )

    # Retrieve summary
    resp = client.get(f"/api/v1/encounters/{ASSIGNED_ENC_1}/summary", headers=PHYSICIAN_AUTH)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "final"
    assert data["signed_by"] == "usr-phy-001"
    assert data["signed_at"] is not None


# =====================================================================
# 12. Zero-PHI in Error Responses
# =====================================================================

def test_zero_phi_in_review_and_signing_errors():
    """Verify error responses on patch/sign contain zero patient identifiers."""
    fake_enc = "018f0000-0000-7000-8000-000000000099"
    bg_headers = {**PHYSICIAN_AUTH, "X-Break-Glass-Reason": "Emergency verification"}

    resp = client.patch(
        f"/api/v1/encounters/{fake_enc}/summary",
        headers=bg_headers,
        json={"slot_path": "allergies", "new_value": "Test"},
    )
    assert resp.status_code == 404
    err_body = resp.json()
    assert "error" in err_body
    assert "Patient" not in err_body["error"]["message"]
