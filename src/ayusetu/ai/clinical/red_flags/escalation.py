"""
Tier behaviour on RedFlagEvent (PRD §12.3, §12.4).

Only Tier 1 interrupts a human. Tier 2 silently re-prioritises the queue.
Tier 3 is an inline flag only, attached to the summary. This is the
correction the PRD makes over its own v1 design (§Correction C3): treating
every flag as human-interrupting caused ~163 desk alerts/day and would have
led to alarm fatigue within a week.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from ayusetu.ai.clinical.red_flags.contracts import RedFlagEvent, Tier

TELE_MANAS_HELPLINE = "14416"

PATIENT_MESSAGES = {
    "calm_wait": {
        "en": "Thank you. Please stay seated — our staff will see you shortly.",
        "hi": "धन्यवाद। कृपया बैठे रहें — हमारा स्टाफ जल्द ही आपसे मिलेगा।",
    },
    "psychiatric_support": {
        "en": (
            "Thank you for telling us. You're not alone — a member of our team is "
            f"coming to speak with you now. You can also call {TELE_MANAS_HELPLINE} "
            "(Tele-MANAS) any time."
        ),
        "hi": (
            "हमें बताने के लिए धन्यवाद। आप अकेले नहीं हैं — हमारी टीम का एक सदस्य अभी आपसे "
            f"बात करने आ रहा है। आप कभी भी {TELE_MANAS_HELPLINE} (टेली-मानस) पर भी कॉल कर सकते हैं।"
        ),
    },
}

# PRD §12.3.5 — 90s to the nursing officer, 180s to the duty medical officer.
NURSE_ESCALATION_SECONDS = 90
DUTY_OFFICER_ESCALATION_SECONDS = 180


class EscalationLevel(str, Enum):
    NONE = "none"
    NURSING_OFFICER = "nursing_officer"
    DUTY_MEDICAL_OFFICER = "duty_medical_officer"


@dataclass
class EscalationAction:
    tier: Tier
    push_to_ops_console: bool
    queue_priority: Optional[str]
    patient_message: Optional[str]
    dispatch_staff_in_person: bool = False
    inline_flag_only: bool = False
    audit_log_entry: dict = field(default_factory=dict)


def _patient_message(key: Optional[str], language: str = "en") -> Optional[str]:
    if key is None:
        return None
    return PATIENT_MESSAGES.get(key, {}).get(language, PATIENT_MESSAGES.get(key, {}).get("en"))


def handle_tier1(event: RedFlagEvent, language: str = "en") -> EscalationAction:
    """
    Silent, immediate push to the Ops Console; queue priority escalated;
    the patient sees only a calm, non-alarming message and is never told an
    alarm was raised (PRD §12.3, steps 1-3).
    """
    return EscalationAction(
        tier=event.tier,
        push_to_ops_console=True,
        queue_priority="immediate",
        patient_message=_patient_message("calm_wait", language),
        audit_log_entry=_audit_entry(event),
    )


def handle_psychiatric_disclosure(event: RedFlagEvent, language: str = "en") -> EscalationAction:
    """
    PRD §12.4: a self-harm disclosure must never be routed as an impersonal
    queue alert alone. A supportive message naming the Tele-MANAS helpline
    is shown, and a staff member is dispatched to the patient in person.
    """
    return EscalationAction(
        tier=event.tier,
        push_to_ops_console=True,
        queue_priority="immediate",
        patient_message=_patient_message("psychiatric_support", language),
        dispatch_staff_in_person=True,
        audit_log_entry=_audit_entry(event),
    )


def handle_tier2(event: RedFlagEvent) -> EscalationAction:
    """Silent queue re-prioritisation only — no human interrupt, no patient-facing change."""
    return EscalationAction(
        tier=event.tier,
        push_to_ops_console=False,
        queue_priority="elevated",
        patient_message=None,
        audit_log_entry=_audit_entry(event),
    )


def handle_tier3(event: RedFlagEvent) -> EscalationAction:
    """Inline flag only, surfaced on the physician's summary — no escalation action at all."""
    return EscalationAction(
        tier=event.tier,
        push_to_ops_console=False,
        queue_priority=None,
        patient_message=None,
        inline_flag_only=True,
        audit_log_entry=_audit_entry(event),
    )


def dispatch(event: RedFlagEvent, language: str = "en") -> EscalationAction:
    """Routes a RedFlagEvent to the correct tier behaviour, including the
    psychiatric special case, which supersedes the generic Tier 1 path."""
    if event.tier == Tier.TIER_1:
        if event.category == "psychiatric":
            return handle_psychiatric_disclosure(event, language)
        return handle_tier1(event, language)
    if event.tier == Tier.TIER_2:
        return handle_tier2(event)
    return handle_tier3(event)


def _audit_entry(event: RedFlagEvent) -> dict:
    """PRD §12.3.6 — the full event is written to the immutable audit log."""
    return {
        "encounter_id": event.encounter_id,
        "rule_id": event.rule_id,
        "tier": int(event.tier),
        "category": event.category,
        "detected_at": event.detected_at.isoformat(),
        "detection_layer": event.detection_layer,
    }


def current_escalation_level(
    event: RedFlagEvent,
    now: Optional[datetime] = None,
    nurse_seconds: int = NURSE_ESCALATION_SECONDS,
    duty_officer_seconds: int = DUTY_OFFICER_ESCALATION_SECONDS,
) -> EscalationLevel:
    """
    PRD §12.3.5: an unacknowledged Tier 1 alert escalates to the nursing
    officer at 90s and the duty medical officer at 180s. Acknowledged
    events, or non-Tier-1 events, never escalate this way.
    """
    if event.tier != Tier.TIER_1 or event.acknowledged_at is not None:
        return EscalationLevel.NONE

    now = now or datetime.now(timezone.utc)
    elapsed = (now - event.detected_at).total_seconds()

    if elapsed >= duty_officer_seconds:
        return EscalationLevel.DUTY_MEDICAL_OFFICER
    if elapsed >= nurse_seconds:
        return EscalationLevel.NURSING_OFFICER
    return EscalationLevel.NONE
