from datetime import datetime, timedelta, timezone

from ayusetu.ai.clinical.red_flags.contracts import RedFlagEvent, Tier
from ayusetu.ai.clinical.red_flags import escalation


def _event(tier=Tier.TIER_1, category="cardiac", detected_at=None):
    return RedFlagEvent(
        encounter_id="enc-1",
        rule_id="RF-CARD-01",
        tier=tier,
        category=category,
        title="Possible acute coronary syndrome",
        trigger_text="chest pain",
        detected_at=detected_at or datetime.now(timezone.utc),
        detection_layer="rule",
    )


def test_tier1_pushes_to_ops_console_with_calm_patient_message():
    action = escalation.dispatch(_event(tier=Tier.TIER_1, category="cardiac"))
    assert action.push_to_ops_console is True
    assert action.queue_priority == "immediate"
    assert "stay seated" in action.patient_message
    assert action.dispatch_staff_in_person is False


def test_tier2_silently_reprioritises_without_patient_facing_change():
    action = escalation.dispatch(_event(tier=Tier.TIER_2, category="metabolic"))
    assert action.push_to_ops_console is False
    assert action.queue_priority == "elevated"
    assert action.patient_message is None


def test_tier3_is_inline_flag_only():
    action = escalation.dispatch(_event(tier=Tier.TIER_3, category="lab_abnormal"))
    assert action.push_to_ops_console is False
    assert action.inline_flag_only is True
    assert action.patient_message is None


def test_psychiatric_disclosure_never_a_generic_alert():
    action = escalation.dispatch(_event(tier=Tier.TIER_1, category="psychiatric"))
    assert action.dispatch_staff_in_person is True
    assert "14416" in action.patient_message
    # It still reaches the ops console / queue (not silence), just never AS an
    # impersonal alert alone.
    assert action.push_to_ops_console is True


def test_escalation_level_none_before_90_seconds():
    event = _event(detected_at=datetime.now(timezone.utc) - timedelta(seconds=30))
    assert escalation.current_escalation_level(event) == escalation.EscalationLevel.NONE


def test_escalation_level_nursing_officer_after_90_seconds():
    event = _event(detected_at=datetime.now(timezone.utc) - timedelta(seconds=91))
    assert escalation.current_escalation_level(event) == escalation.EscalationLevel.NURSING_OFFICER


def test_escalation_level_duty_officer_after_180_seconds():
    event = _event(detected_at=datetime.now(timezone.utc) - timedelta(seconds=181))
    assert escalation.current_escalation_level(event) == escalation.EscalationLevel.DUTY_MEDICAL_OFFICER


def test_acknowledged_event_never_escalates():
    event = _event(detected_at=datetime.now(timezone.utc) - timedelta(seconds=300))
    event.acknowledge(by="nurse-1")
    assert escalation.current_escalation_level(event) == escalation.EscalationLevel.NONE


def test_tier2_event_never_escalates_via_the_timer():
    event = _event(tier=Tier.TIER_2, detected_at=datetime.now(timezone.utc) - timedelta(seconds=300))
    assert escalation.current_escalation_level(event) == escalation.EscalationLevel.NONE
