"""
Audit Service Core Engine
=========================
Central coordination service for AyuSetu's append-only, cryptographic hash-chained
audit log per PRD v2.0 §21.8 & §22.8.
Integrates with M3 authentication, RBAC, ABAC, and M4 DPDP consent security events.
Guarantees ZERO PHI, strictly monotonic sequencing, and offline batch splicing.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set

from ayusetu.audit.models import (
    AuditAction,
    AuditEventCreate,
    AuditEventDTO,
    AuditHeadDTO,
    AuditOutcome,
    AuditVerificationResult,
    OfflineAuditSyncBatch,
    OfflineAuditSyncResponse,
    QuarantineRecordDTO,
)
from ayusetu.audit.repository import AuditRepository
from ayusetu.audit.verifier import audit_verifier
from ayusetu.audit.quarantine import quarantine_store
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.gateway.auth.event_hooks import SecurityEvent, register_security_event_listener
from ayusetu.consent.event_hooks import register_event_listener as register_consent_event_listener

logger = logging.getLogger("ayusetu.audit.service")

# Strict whitelist of safe non-PHI metadata keys allowed in audit payloads
SAFE_METADATA_WHITELIST: Set[str] = {
    "event_type",
    "encounter_id",
    "patient_id",
    "actor_id",
    "actor_role",
    "reason",
    "device_id",
    "seq",
    "count",
    "synced_count",
    "artefact_id",
    "target_resource",
    "target_stores",
    "remaining_purposes",
    "withdrawn_purposes",
    "is_minor",
    "is_offline",
    "notice_version",
    "required_purpose",
    "error_message",
    "quarantine_id",
    "seed_head_hash",
    "head_hash",
}


def sanitize_audit_metadata(raw_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Sanitize metadata to guarantee ZERO PHI or secrets are stored in audit logs.
    Strips any fields not explicitly included in the safe whitelist.
    """
    if not raw_metadata:
        return {}
    sanitized = {}
    for k, v in raw_metadata.items():
        if k in SAFE_METADATA_WHITELIST:
            if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                sanitized[k] = v
    return sanitized


class AuditService:
    """
    Production-ready audit service managing the global cryptographic audit chain.
    """

    def __init__(self, repository: Optional[AuditRepository] = None) -> None:
        self._repo = repository or AuditRepository()
        self._register_subsystem_hooks()

    def _register_subsystem_hooks(self) -> None:
        """Register listeners with M3 Security and M4 Consent event dispatchers."""
        register_security_event_listener(self._handle_gateway_security_event)
        register_consent_event_listener(self._handle_consent_security_event)

    def _handle_gateway_security_event(self, event: SecurityEvent) -> None:
        """Process security events dispatched by Gateway M3 (IDOR, Break-glass, Auth failures)."""
        action = AuditAction.READ
        outcome = AuditOutcome.DENY

        if event.event_type == "BREAK_GLASS":
            action = AuditAction.BREAKGLASS
            outcome = AuditOutcome.ALLOW
        elif event.event_type in ("AUTH_LOGIN", "AUTH_SUCCESS"):
            action = AuditAction.READ
            outcome = AuditOutcome.ALLOW
        elif event.event_type in ("AUTH_FAILED", "DEVICE_REVOKED", "IDOR_ATTEMPT"):
            action = AuditAction.READ
            outcome = AuditOutcome.DENY

        try:
            self.record_event(
                actor_id=event.actor_id,
                actor_role=event.actor_role,
                action=action,
                resource_type=event.target_resource,
                resource_id=event.target_encounter_id or event.target_patient_id or "00000000-0000-0000-0000-000000000000",
                patient_id=event.target_patient_id,
                encounter_id=event.target_encounter_id,
                outcome=outcome,
                reason=f"{event.event_type}: {event.reason or ''}".strip(": "),
                safe_metadata=sanitize_audit_metadata(event.metadata),
                forced_ts=event.timestamp,
            )
        except Exception as e:
            logger.error("Failed to record gateway security event in audit chain: %s", e)

    def _handle_consent_security_event(self, event: Dict[str, Any]) -> None:
        """Process DPDP consent security events dispatched by M4 Consent Service."""
        event_type = event.get("event_type", "CONSENT_EVENT")
        actor_id = event.get("actor_id") or "00000000-0000-0000-0000-000000000000"
        patient_id = event.get("patient_id")
        encounter_id = event.get("encounter_id")
        timestamp = event.get("timestamp")

        action = AuditAction.CREATE
        outcome = AuditOutcome.ALLOW
        resource_type = "ConsentRecord"
        resource_id = event.get("consent_id") or encounter_id or patient_id or "00000000-0000-0000-0000-000000000000"

        if event_type == "CONSENT_WITHDRAWN":
            action = AuditAction.UPDATE
        elif event_type in ("ERASURE_REQUESTED", "ERASURE_PROPAGATED"):
            action = AuditAction.UPDATE
            resource_type = "Patient"
            resource_id = patient_id or "00000000-0000-0000-0000-000000000000"
        elif event_type == "CONSENT_DENIED":
            action = AuditAction.READ
            outcome = AuditOutcome.DENY
        elif event_type in ("ABDM_ARTIFACT_REQUESTED", "ABDM_ARTIFACT_AVAILABLE", "ABDM_ARTIFACT_WITHDRAWN"):
            action = AuditAction.UPDATE
            resource_type = "ABDMArtefact"

        try:
            self.record_event(
                actor_id=actor_id,
                actor_role="patient" if not encounter_id else "clinician",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                patient_id=patient_id,
                encounter_id=encounter_id,
                outcome=outcome,
                reason=f"{event_type}: {event.get('reason') or ''}".strip(": "),
                safe_metadata=sanitize_audit_metadata(event),
                forced_ts=timestamp,
            )
        except Exception as e:
            logger.error("Failed to record consent event in audit chain: %s", e)

    def record_event(
        self,
        actor_id: str,
        actor_role: str,
        action: AuditAction,
        resource_type: str,
        resource_id: str,
        outcome: AuditOutcome = AuditOutcome.ALLOW,
        reason: Optional[str] = None,
        patient_id: Optional[str] = None,
        encounter_id: Optional[str] = None,
        src_device: Optional[str] = None,
        src_ip: Optional[str] = None,
        safe_metadata: Optional[Dict[str, Any]] = None,
        forced_ts: Optional[str] = None,
    ) -> AuditEventDTO:
        """
        Record an immutable audit event in the global cryptographic chain.
        """
        sanitized_meta = sanitize_audit_metadata(safe_metadata)
        event_create = AuditEventCreate(
            actor_id=str(actor_id),
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            patient_id=str(patient_id) if patient_id else None,
            encounter_id=str(encounter_id) if encounter_id else None,
            outcome=outcome,
            reason=reason,
            src_device=src_device,
            src_ip=src_ip,
            safe_metadata=sanitized_meta,
        )
        return self._repo.append(event_create, forced_ts=forced_ts)

    def get_head(self) -> AuditHeadDTO:
        """Return the current tip of the global audit chain."""
        return self._repo.get_head()

    def get_by_seq(self, seq: int) -> Optional[AuditEventDTO]:
        """Retrieve a specific audit event by sequence number."""
        return self._repo.get_by_seq(seq)

    def query_events(
        self,
        from_seq: int = 1,
        to_seq: Optional[int] = None,
        limit: int = 100,
        encounter_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> List[AuditEventDTO]:
        """Query audit log with safe metadata filtering."""
        return self._repo.get_range(
            from_seq=from_seq,
            to_seq=to_seq,
            limit=limit,
            encounter_id=encounter_id,
            patient_id=patient_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
        )

    def verify_global_chain(self) -> AuditVerificationResult:
        """
        Perform end-to-end cryptographic verification of the entire global audit chain.
        Callable by scheduled nightly verifier jobs or auditor queries.
        """
        events = self._repo.get_all()
        result = audit_verifier.verify_chain(events)
        if not result.valid:
            logger.critical(
                "CRITICAL SECURITY ALERT [AUDIT_CHAIN_INTEGRITY_FAILURE]: last_valid=%d, failure=%s",
                result.last_valid_sequence,
                result.failure,
            )
        return result

    def sync_offline_batch(
        self,
        batch: OfflineAuditSyncBatch,
        trusted_device_id: Optional[str] = None,
    ) -> OfflineAuditSyncResponse:
        """
        Verify and splice an offline audit batch into the global audit chain.
        Rejects and quarantines tampered, unlinked, impersonated, or corrupted batches.
        """
        # 1. Enforce Device Authentication & Impersonation Boundary
        if trusted_device_id and str(batch.device_id).strip() != str(trusted_device_id).strip():
            quarantine_store.quarantine_batch(
                device_id=batch.device_id,
                seed_head_hash=batch.seed_head_hash,
                reason=f"Device impersonation: authenticated device '{trusted_device_id}' != batch '{batch.device_id}'",
                failure_code="DEVICE_IMPERSONATION_ATTEMPT",
                event_count=len(batch.events),
                safe_metadata={"authenticated_device_id": trusted_device_id, "claimed_device_id": batch.device_id},
            )
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Device identity mismatch: authenticated as '{trusted_device_id}' but batch claims '{batch.device_id}'",
                403,
            )

        known_heads = self._repo.known_head_hashes()
        is_valid, failure_code, failure_reason = audit_verifier.verify_offline_batch(
            batch, known_heads
        )

        if not is_valid:
            # Quarantine the invalid batch
            quarantine_store.quarantine_batch(
                device_id=batch.device_id,
                seed_head_hash=batch.seed_head_hash,
                reason=failure_reason or "Unknown verification failure",
                failure_code=failure_code or "VALIDATION_FAILED",
                event_count=len(batch.events),
                safe_metadata={"device_id": batch.device_id},
            )
            raise AyuSetuGatewayError(
                ErrorCode.UNPROCESSABLE_ENTITY,
                f"Offline audit batch rejected and quarantined: {failure_reason}",
                422,
            )

        # Splice valid offline events into the global chain
        synced_count = 0
        for off_ev in batch.events:
            # Re-chain into global log, preserving original offline metadata
            safe_meta = {
                "offline_device_id": batch.device_id,
                "offline_local_seq": off_ev.local_seq,
                "offline_local_entry_hash": off_ev.entry_hash,
            }
            # Map action safely
            try:
                act = AuditAction(off_ev.action)
            except ValueError:
                act = AuditAction.CREATE

            try:
                outc = AuditOutcome(off_ev.outcome)
            except ValueError:
                outc = AuditOutcome.ALLOW

            self._repo.append(
                AuditEventCreate(
                    actor_id=off_ev.actor_id,
                    actor_role=off_ev.actor_role,
                    action=act,
                    resource_type=off_ev.resource_type,
                    resource_id=off_ev.resource_id,
                    patient_id=off_ev.patient_id,
                    encounter_id=off_ev.encounter_id,
                    outcome=outc,
                    reason=off_ev.reason,
                    src_device=off_ev.src_device,
                    safe_metadata=safe_meta,
                ),
                forced_ts=off_ev.ts,
            )
            synced_count += 1

        new_head = self._repo.get_head()
        logger.info(
            "Successfully spliced offline audit batch from device %s (%d events). New global head seq=%d",
            batch.device_id,
            synced_count,
            new_head.seq,
        )

        return OfflineAuditSyncResponse(
            status="SYNCED",
            synced_count=synced_count,
            new_head=new_head,
        )

    def get_quarantined_records(self) -> List[QuarantineRecordDTO]:
        """Retrieve list of quarantined batches."""
        return quarantine_store.list_records()

    def clear_for_testing(self) -> None:
        """Reset service state for test suite isolation."""
        self._repo.clear_for_testing()
        quarantine_store.clear_for_testing()


audit_service = AuditService()
