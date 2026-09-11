"""
Phase 9 Integration Test: Full Security Lifecycle
=================================================
Validates the complete 15-step end-to-end security lifecycle across AyuSetu:

AUTHENTICATION
  ↓
SESSION CREATION
  ↓
RBAC MATRIX EVALUATION
  ↓
ABAC CONTEXTUAL POLICY
  ↓
DPDP NOTICE & CONSENT RECORDING
  ↓
ENCOUNTER ACCESS
  ↓
CLINICAL INTAKE & RED-FLAG EVALUATION
  ↓
MONOTONIC AUDIT HASH CHAINING
  ↓
COHORT DE-IDENTIFICATION TRANSFORM
  ↓
K-ANONYMITY VALIDATION (k >= 5)
  ↓
ZERO-PHI SAFETY GATE INSPECTION
  ↓
TWO-PERSON EXPORT AUTHORIZATION (SoD)
  ↓
SECURE COHORT EXPORT
  ↓
AUDIT DECISION RECORDING
"""

import datetime
from typing import Any, Dict, List
import uuid6
import pytest
from fastapi.testclient import TestClient

from ayusetu.gateway.app import gateway_app
from ayusetu.gateway.auth.models import Principal, Role, Action, Resource, AuthContext
from ayusetu.gateway.auth.rbac import RBACPolicy
from ayusetu.gateway.auth.abac import ABACEvaluator
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.redflag.service import red_flag_service
from ayusetu.redflag.models import StructuredClinicalFact
from ayusetu.audit.service import audit_service
from ayusetu.audit.models import AuditAction, AuditOutcome
from ayusetu.deid.models import DeidExportRequest, ExportPurpose
from ayusetu.deid.service import deid_export_service

client = TestClient(gateway_app)


def test_full_security_lifecycle_e2e():
    """
    Executes and validates the uninterrupted 15-step security lifecycle using synthetic records.
    """
    # -------------------------------------------------------------------------
    # STEP 1 & 2: AUTHENTICATION & SESSION CREATION
    # -------------------------------------------------------------------------
    session_res = client.post(
        "/api/v1/sessions",
        json={
            "channel": "kiosk",
            "department": "Kayachikitsa",
            "visit_type": "new",
            "intake_depth": "full",
        },
        headers={"X-Device-Fingerprint": "kiosk-cert-sha256-valid"},
    )
    assert session_res.status_code == 201
    session_data = session_res.json()
    session_id = session_data["session_id"]
    encounter_id = session_data["encounter_id"]
    patient_id = str(uuid6.uuid7())
    physician_actor_id = "018f0000-0000-7000-8000-000000000010"

    # -------------------------------------------------------------------------
    # STEP 3 & 4: RBAC & ABAC EVALUATION
    # -------------------------------------------------------------------------
    physician_principal = Principal(
        actor_id=physician_actor_id,
        role=Role.PHYSICIAN,
        department="Kayachikitsa",
        assigned_encounter_ids={encounter_id},
        is_authenticated=True,
    )
    # Check RBAC
    assert RBACPolicy.is_permitted(Role.PHYSICIAN, Resource.SIGNED_CLINICAL_RECORD, Action.READ) is True
    
    # Check ABAC (same department, assigned encounter)
    auth_ctx = AuthContext(
        principal=physician_principal,
        resource=Resource.SIGNED_CLINICAL_RECORD,
        action=Action.READ,
        target_encounter_id=encounter_id,
        target_department="Kayachikitsa",
    )
    allowed, reason = ABACEvaluator.evaluate(auth_ctx)
    assert allowed is True

    # -------------------------------------------------------------------------
    # STEP 5: DPDP NOTICE & CONSENT RECORDING
    # -------------------------------------------------------------------------
    consent_rec = consent_service.grant_consent(
        ConsentGrantRequest(
            encounter_id=encounter_id,
            patient_id=patient_id,
            purposes=Purposes(clinical=True, abdm=True, research=True, qi=True),
            language="hi",
        )
    )
    assert consent_rec.purposes.get("clinical") is True
    assert consent_rec.status.value in ("active", "GRANTED")

    # Verify active consent via service
    assert consent_service.check_clinical_consent(encounter_id) is True
    assert consent_service.check_purpose_consent(encounter_id, "research") is True

    # -------------------------------------------------------------------------
    # STEP 6 & 7: CLINICAL INTAKE & DECLARATIVE RED-FLAG ENGINE
    # -------------------------------------------------------------------------
    facts = [
        StructuredClinicalFact(path="symptoms.chest_pain", value=True),
        StructuredClinicalFact(path="symptoms.sweating", value=True),
    ]
    detected_flags = red_flag_service.evaluate_encounter(
        encounter_id=encounter_id,
        facts=facts,
        actor_id=physician_principal.actor_id,
        actor_role=physician_principal.role.value,
    )
    assert len(detected_flags) > 0
    assert any(m.rule_id == "RF-CARD-001" for m in detected_flags)

    # -------------------------------------------------------------------------
    # STEP 8: MONOTONIC AUDIT HASH CHAINING
    # -------------------------------------------------------------------------
    audit_evt = audit_service.record_event(
        actor_id=physician_principal.actor_id,
        actor_role=physician_principal.role.value,
        action=AuditAction.CREATE,
        resource_type="encounter",
        resource_id=encounter_id,
        encounter_id=encounter_id,
        outcome=AuditOutcome.ALLOW,
        safe_metadata={"tier1_redflags": [m.rule_id for m in detected_flags]},
    )
    assert audit_evt.seq > 0
    assert audit_evt.entry_hash is not None
    assert audit_evt.prev_hash is not None

    # -------------------------------------------------------------------------
    # STEP 9, 10, 11, 12, 13: DE-IDENTIFICATION, K-ANONYMITY, SAFETY GATE,
    # TWO-PERSON AUTHORIZATION (SoD) & SECURE EXPORT
    # -------------------------------------------------------------------------
    # Construct synthetic research cohort of 5 identical quasi-identifier profiles (k=5)
    candidate_records: List[Dict[str, Any]] = []
    base_date = datetime.date(2025, 4, 15)
    for i in range(5):
        enc_id = f"018f0000-0000-7000-9000-{i:012d}"
        pat_id = f"018f0000-0000-7000-8000-{i:012d}"
        # Ensure consent exists for research purpose
        consent_service.grant_consent(
            ConsentGrantRequest(
                encounter_id=enc_id,
                patient_id=pat_id,
                purposes=Purposes(clinical=True, research=True, qi=True, abdm=True),
                language="hi",
            )
        )
        candidate_records.append({
            "patient_id": pat_id,
            "encounter_id": enc_id,
            "dob": "1980-05-12",
            "gender": "male",
            "district": "lucknow",
            "state": "Uttar Pradesh",
            "department": "kayachikitsa",
            "visit_type": "new",
            "encounter_date": base_date.isoformat(),
            "triage_tier": 2,
            "slots": [
                {
                    "path": "symptoms.chest_pain",
                    "value_coded": "exertional_angina",
                    "code_system": "ICD-10",
                    "code": "I20.0",
                }
            ],
        })

    mrd_exporter = Principal(
        actor_id="018f0000-0000-7000-8000-000000000050",
        role=Role.MRD,
        department="MedicalRecords",
        is_authenticated=True,
    )

    export_req = DeidExportRequest(
        date_from="2025-01-01",
        date_to="2025-12-31",
        purpose=ExportPurpose.RESEARCH,
        approver_1="018f0000-0000-7000-8000-000000000060",
        approver_2="018f0000-0000-7000-8000-000000000070",
        department="kayachikitsa",
    )

    export_response = deid_export_service.export_cohort(
        request=export_req,
        principal=mrd_exporter,
        candidate_records=candidate_records,
    )

    # -------------------------------------------------------------------------
    # STEP 14 & 15: VERIFY EXPORT INTEGRITY & AUDIT TRAIL
    # -------------------------------------------------------------------------
    assert export_response.status == "COMPLETED"
    assert export_response.cohort_size == 5
    assert export_response.k_anonymity_achieved is True
    assert export_response.min_class_size >= 5
    assert len(export_response.records) == 5

    # Verify zero PHI in exported records
    for rec in export_response.records:
        rec_dict = rec.model_dump()
        assert "patient_name" not in rec_dict
        assert "aadhaar" not in rec_dict
        assert "phone" not in rec_dict
        assert "pincode" not in rec_dict
        assert not rec_dict["pseudonym_token"].startswith("018f0000")  # pseudonymized
        assert rec_dict["sex"] == "male"
        assert len(rec_dict["coded_slots"]) == 1
        assert rec_dict["coded_slots"][0]["code"] == "I20.0"

    # Verify audit decision was immutably recorded
    all_events = audit_service._repo.get_all()
    export_audits = [e for e in all_events if e.action == "EXPORT"]
    assert len(export_audits) > 0
    assert export_audits[-1].actor_id == "018f0000-0000-7000-8000-000000000050"
    assert export_audits[-1].outcome == "ALLOW"
