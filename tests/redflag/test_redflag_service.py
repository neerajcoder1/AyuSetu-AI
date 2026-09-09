"""
Red-Flag Service Integration Tests
==================================
Tests M4 consent gating, idempotent deduplication, state machine transitions,
Tier-1 alert queue management, and M5 audit event dispatch.
"""

import pytest
import uuid6

from ayusetu.redflag.models import RedFlagStatus, StructuredClinicalFact
from ayusetu.redflag.service import red_flag_service
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentGrantRequest, Purposes
from ayusetu.audit.service import audit_service
from ayusetu.gateway.errors import AyuSetuGatewayError


def test_redflag_evaluation_fails_closed_without_clinical_consent():
    """Verify evaluating red flags without active clinical consent raises 403 CONSENT_REQUIRED."""
    enc_id = str(uuid6.uuid7())
    facts = [
        StructuredClinicalFact(path="symptoms.chest_pain", value=True),
        StructuredClinicalFact(path="symptoms.radiation", value=True),
    ]

    with pytest.raises(AyuSetuGatewayError) as exc_info:
        red_flag_service.evaluate_encounter(enc_id, facts)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "CONSENT_REQUIRED"


def test_redflag_evaluation_succeeds_with_granted_clinical_consent():
    """Verify evaluation succeeds and produces red-flag events when clinical consent is granted."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    # Grant clinical consent
    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True, abdm=False, qi=False, research=False),
            language="en",
        ),
    )

    facts = [
        StructuredClinicalFact(path="symptoms.chest_pain", value=True),
        StructuredClinicalFact(path="symptoms.radiation", value=True),
    ]

    events = red_flag_service.evaluate_encounter(enc_id, facts, actor_id=pat_id, actor_role="patient")
    assert len(events) == 1
    ev = events[0]
    assert ev.rule_id == "RF-CARD-001"
    assert ev.tier == 1
    assert ev.status == RedFlagStatus.DETECTED

    # Verify audit event was logged in M5 audit trail (zero PHI)
    audit_records = audit_service.query_events(encounter_id=enc_id)
    assert len(audit_records) >= 1
    assert any("REDFLAG_DETECTED: RF-CARD-001" in (r.reason or "") for r in audit_records)


def test_redflag_idempotent_deduplication():
    """Verify evaluating identical encounter facts repeatedly does not produce duplicate events."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
            language="en",
        ),
    )

    facts = [
        StructuredClinicalFact(path="symptoms.stridor", value=True),
    ]

    # First evaluation
    events_1 = red_flag_service.evaluate_encounter(enc_id, facts)
    assert len(events_1) == 1
    event_id_1 = events_1[0].id

    # Second evaluation with same facts
    events_2 = red_flag_service.evaluate_encounter(enc_id, facts)
    assert len(events_2) == 1
    assert events_2[0].id == event_id_1

    # Total events stored for encounter remains 1
    all_events = red_flag_service.get_encounter_events(enc_id)
    assert len(all_events) == 1


def test_redflag_lifecycle_transitions():
    """Verify alert transitions from DETECTED -> ACKNOWLEDGED -> RESOLVED."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
            language="en",
        ),
    )

    facts = [
        StructuredClinicalFact(path="vitals.sbp", value=195),
    ]
    events = red_flag_service.evaluate_encounter(enc_id, facts)
    event_id = events[0].id

    # 1. Acknowledge
    ack_ev = red_flag_service.acknowledge_event(
        event_id=event_id,
        clinician_id="usr-nur-001",
        clinician_role="nurse",
        notes="BP checked on manual sphygmomanometer",
    )
    assert ack_ev.status == RedFlagStatus.ACKNOWLEDGED
    assert ack_ev.acknowledged_by == "usr-nur-001"
    assert ack_ev.acknowledged_at is not None

    # 2. Resolve
    res_ev = red_flag_service.resolve_event(
        event_id=event_id,
        clinician_id="usr-phy-001",
        clinician_role="physician",
        outcome="STABILIZED_WITH_MEDICATION",
    )
    assert res_ev.status == RedFlagStatus.RESOLVED
    assert "STABILIZED_WITH_MEDICATION" in res_ev.outcome


def test_redflag_invalid_transition_rejected():
    """Verify that attempting an illegal transition (e.g. RESOLVED -> ACKNOWLEDGED) raises 422."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
            language="en",
        ),
    )

    facts = [StructuredClinicalFact(path="symptoms.fever", value=True), StructuredClinicalFact(path="symptoms.neck_stiffness", value=True)]
    events = red_flag_service.evaluate_encounter(enc_id, facts)
    event_id = events[0].id

    # Directly resolve
    red_flag_service.resolve_event(event_id, "usr-phy-001", "physician", "DISMISSED")

    # Attempt to acknowledge a resolved event -> fails closed
    with pytest.raises(AyuSetuGatewayError) as exc_info:
        red_flag_service.acknowledge_event(event_id, "usr-nur-001", "nurse")

    assert exc_info.value.status_code == 422
    assert "cannot transition" in str(exc_info.value.message).lower()


def test_tier1_queue_escalation():
    """Verify unresolved Tier 1 alerts appear in tier1 queue with escalation timing."""
    enc_id = str(uuid6.uuid7())
    pat_id = str(uuid6.uuid7())

    consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=Purposes(clinical=True),
            language="en",
        ),
    )

    facts = [StructuredClinicalFact(path="symptoms.stridor", value=True)]
    red_flag_service.evaluate_encounter(enc_id, facts)

    queue = red_flag_service.get_tier1_queue()
    assert len(queue) == 1
    assert queue[0].encounter_id == enc_id
    assert queue[0].event.rule_id == "RF-RESP-001"
