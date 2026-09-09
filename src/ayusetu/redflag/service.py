"""
Red-Flag Engine Central Service
===============================
Coordinates deterministic rule evaluation, M4 DPDP consent gating,
idempotent deduplication, tier-1 alert queues, M5 audit logging, and clinician lifecycle actions.
Authoritative state is persisted in PostgreSQL via RedFlagRepository.
"""

from datetime import datetime, timezone
import logging
from typing import List, Optional
import uuid6

from ayusetu.redflag.models import (
    RedFlagEventDTO,
    RedFlagStatus,
    RedFlagTier,
    StructuredClinicalFact,
    Tier1AlertQueueItem,
)
from ayusetu.redflag.engine import red_flag_engine
from ayusetu.redflag.escalation import red_flag_lifecycle
from ayusetu.redflag.repository import RedFlagRepository, to_valid_uuid_str
from ayusetu.consent.service import ConsentService, consent_service
from ayusetu.audit.service import audit_service
from ayusetu.audit.models import AuditAction, AuditOutcome
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.gateway.auth.event_hooks import dispatch_security_event

logger = logging.getLogger("ayusetu.redflag.service")


class RedFlagService:
    """
    Central orchestration service for AyuSetu's Red-Flag Engine.
    Authoritative state is persisted in PostgreSQL.
    """

    def __init__(
        self,
        repository: Optional[RedFlagRepository] = None,
        consent_svc: Optional[ConsentService] = None,
    ) -> None:
        self._repo = repository or RedFlagRepository()
        self._consent_svc = consent_svc or consent_service

    def evaluate_encounter(
        self,
        encounter_id: str,
        facts: List[StructuredClinicalFact],
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> List[RedFlagEventDTO]:
        """
        Evaluate structured facts against red-flag rules under strict consent gating.
        Persists newly detected safety events into PostgreSQL.
        """
        # 1. Enforce M4 Clinical Consent Gating
        if not self._consent_svc.check_clinical_consent(encounter_id):
            logger.warning("Red-flag evaluation blocked: encounter %s lacks active clinical consent", encounter_id)
            raise AyuSetuGatewayError(
                ErrorCode.CONSENT_REQUIRED,
                f"Clinical consent required before evaluating clinical safety rules for encounter {encounter_id}",
                403,
            )

        # 2. Deterministic Rule Evaluation
        matched = red_flag_engine.evaluate(facts)
        now_iso = datetime.now(timezone.utc).isoformat()
        results: List[RedFlagEventDTO] = []

        existing_events = self._repo.get_encounter_events(encounter_id)
        active_events = [ev for ev in existing_events if ev.status != RedFlagStatus.RESOLVED]
        active_rules = {ev.rule_id: ev for ev in active_events}

        for rule, trigger_text in matched:
            # 3. Idempotent Deduplication
            if rule.rule_id in active_rules:
                results.append(active_rules[rule.rule_id])
                continue

            event_id = str(uuid6.uuid7())
            dto = RedFlagEventDTO(
                id=event_id,
                encounter_id=encounter_id,
                rule_id=rule.rule_id,
                tier=rule.tier.value,
                trigger_text=trigger_text,
                detected_at=now_iso,
                acknowledged_by=None,
                acknowledged_at=None,
                outcome=None,
                status=RedFlagStatus.DETECTED,
            )

            # Persist to PostgreSQL (fail-closed)
            saved_dto = self._repo.create_event(dto)
            results.append(saved_dto)
            active_rules[rule.rule_id] = saved_dto

            # 4. Tier 1 Alert Notification
            if rule.tier == RedFlagTier.TIER_1:
                logger.critical(
                    "TIER 1 EMERGENCY ALERT [REDFLAG]: encounter=%s, rule=%s, desc=%s",
                    encounter_id,
                    rule.rule_id,
                    rule.description,
                )
                try:
                    dispatch_security_event(
                        event_type="TIER1_REDFLAG_TRIGGERED",
                        actor_id=actor_id or "system-evaluator",
                        actor_role=actor_role or "system",
                        target_resource="red_flag_event",
                        target_encounter_id=encounter_id,
                        reason=f"Tier 1 Emergency Triggered: {rule.rule_id}",
                        metadata={"rule_id": rule.rule_id, "tier": 1},
                    )
                except Exception as e:
                    logger.error("Failed to dispatch security event for Tier 1 alert: %s", e)

            # 5. Audit Logging with ZERO PHI
            try:
                audit_actor = to_valid_uuid_str(actor_id) or "00000000-0000-0000-0000-000000000000"
                audit_service.record_event(
                    actor_id=audit_actor,
                    actor_role=actor_role or "system",
                    action=AuditAction.CREATE,
                    resource_type="RedFlagEvent",
                    resource_id=event_id,
                    encounter_id=encounter_id,
                    outcome=AuditOutcome.ALLOW,
                    reason=f"REDFLAG_DETECTED: {rule.rule_id} (Tier {rule.tier.value})",
                    safe_metadata={"rule_id": rule.rule_id, "tier": rule.tier.value},
                )
            except Exception as e:
                logger.error("Failed to record audit log for red flag event: %s", e)

        return results

    def get_encounter_events(self, encounter_id: str) -> List[RedFlagEventDTO]:
        """Retrieve all red-flag events associated with an encounter from PostgreSQL."""
        return self._repo.get_encounter_events(encounter_id)

    def get_tier1_queue(self) -> List[Tier1AlertQueueItem]:
        """Retrieve all active (unresolved) Tier 1 alerts with escalation timing from PostgreSQL."""
        return self._repo.get_tier1_queue()

    def get_event_by_id(self, event_id: str) -> Optional[RedFlagEventDTO]:
        """Look up single red-flag event by UUID from PostgreSQL."""
        return self._repo.get_event_by_id(event_id)

    def acknowledge_event(
        self,
        event_id: str,
        clinician_id: str,
        clinician_role: str,
        notes: Optional[str] = None,
    ) -> RedFlagEventDTO:
        """Acknowledge a detected red-flag alert in PostgreSQL."""
        ev = self._repo.get_event_by_id(event_id)
        if not ev:
            raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Red-flag event {event_id} not found", 404)

        red_flag_lifecycle.validate_transition(ev.status, RedFlagStatus.ACKNOWLEDGED)

        now = datetime.now(timezone.utc)
        outcome_str = f"ACKNOWLEDGED: {notes}" if notes else "ACKNOWLEDGED"

        updated = self._repo.update_event_state(
            event_id=event_id,
            acknowledged_by=clinician_id,
            acknowledged_at=now,
            outcome=outcome_str,
        )
        if not updated:
            raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Red-flag event {event_id} not found", 404)

        # Audit Event (Zero PHI)
        try:
            audit_actor = to_valid_uuid_str(clinician_id) or "00000000-0000-0000-0000-000000000000"
            audit_service.record_event(
                actor_id=audit_actor,
                actor_role=clinician_role,
                action=AuditAction.UPDATE,
                resource_type="RedFlagEvent",
                resource_id=event_id,
                encounter_id=ev.encounter_id,
                outcome=AuditOutcome.ALLOW,
                reason=f"REDFLAG_ACKNOWLEDGED: {ev.rule_id}",
                safe_metadata={"rule_id": ev.rule_id, "status": "acknowledged"},
            )
        except Exception as e:
            logger.error("Failed to record audit event for acknowledgement: %s", e)

        return updated

    def escalate_event(
        self,
        event_id: str,
        clinician_id: str,
        clinician_role: str,
        target_role: Optional[str] = "duty_medical_officer",
        notes: Optional[str] = None,
    ) -> RedFlagEventDTO:
        """Escalate an alert to senior emergency clinician / DMO in PostgreSQL."""
        ev = self._repo.get_event_by_id(event_id)
        if not ev:
            raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Red-flag event {event_id} not found", 404)

        red_flag_lifecycle.validate_transition(ev.status, RedFlagStatus.ESCALATED)

        outcome_str = f"ESCALATED_TO_{target_role.upper() if target_role else 'DMO'}: {notes or ''}".strip(": ")
        updated = self._repo.update_event_state(
            event_id=event_id,
            outcome=outcome_str,
        )
        if not updated:
            raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Red-flag event {event_id} not found", 404)

        # Audit Event (Zero PHI)
        try:
            audit_actor = to_valid_uuid_str(clinician_id) or "00000000-0000-0000-0000-000000000000"
            audit_service.record_event(
                actor_id=audit_actor,
                actor_role=clinician_role,
                action=AuditAction.UPDATE,
                resource_type="RedFlagEvent",
                resource_id=event_id,
                encounter_id=ev.encounter_id,
                outcome=AuditOutcome.ALLOW,
                reason=f"REDFLAG_ESCALATED: {ev.rule_id} -> {target_role}",
                safe_metadata={"rule_id": ev.rule_id, "status": "escalated"},
            )
        except Exception as e:
            logger.error("Failed to record audit event for escalation: %s", e)

        return updated

    def resolve_event(
        self,
        event_id: str,
        clinician_id: str,
        clinician_role: str,
        outcome: str,
        notes: Optional[str] = None,
    ) -> RedFlagEventDTO:
        """Resolve a red-flag alert with documented outcome in PostgreSQL."""
        ev = self._repo.get_event_by_id(event_id)
        if not ev:
            raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Red-flag event {event_id} not found", 404)

        red_flag_lifecycle.validate_transition(ev.status, RedFlagStatus.RESOLVED)

        outcome_str = f"{outcome}: {notes}" if notes else outcome
        updated = self._repo.update_event_state(
            event_id=event_id,
            outcome=outcome_str,
        )
        if not updated:
            raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Red-flag event {event_id} not found", 404)

        # Audit Event (Zero PHI)
        try:
            audit_actor = to_valid_uuid_str(clinician_id) or "00000000-0000-0000-0000-000000000000"
            audit_service.record_event(
                actor_id=audit_actor,
                actor_role=clinician_role,
                action=AuditAction.UPDATE,
                resource_type="RedFlagEvent",
                resource_id=event_id,
                encounter_id=ev.encounter_id,
                outcome=AuditOutcome.ALLOW,
                reason=f"REDFLAG_RESOLVED: {ev.rule_id}",
                safe_metadata={"rule_id": ev.rule_id, "status": "resolved"},
            )
        except Exception as e:
            logger.error("Failed to record audit event for resolution: %s", e)

        return updated

    def clear_for_testing(self) -> None:
        """Reset repository state for isolated test execution."""
        self._repo.clear_for_testing()


# Authoritative singleton instance
red_flag_service = RedFlagService()
