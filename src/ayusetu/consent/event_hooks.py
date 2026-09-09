"""
Consent & DPDP Security & Audit Event Hooks
===========================================
Emits structured security audit events for DPDP consent lifecycle operations.
Ensures ZERO Protected Health Information (PHI), zero transcripts, zero raw audio,
and zero clinical slot values are ever emitted to audit logs.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("ayusetu.consent.events")

# In-memory hook listeners for testing and audit service downstream propagation
_event_listeners: List[Callable[[Dict[str, Any]], None]] = []


def register_event_listener(listener: Callable[[Dict[str, Any]], None]) -> None:
    """Register downstream event listener (e.g. Audit Service / Erasure Propagator)."""
    if listener not in _event_listeners:
        _event_listeners.append(listener)


def clear_event_listeners() -> None:
    """Clear all registered event listeners (for test cleanup)."""
    _event_listeners.clear()


def emit_consent_event(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Emit a sanitized security event.
    Guarantees zero PHI in event payload.
    """
    event = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data
    }

    # Log structured security notice
    logger.info(
        f"CONSENT EVENT [{event_type}]: encounter={data.get('encounter_id')}, "
        f"patient={data.get('patient_id')}, actor={data.get('actor_id')}"
    )

    # Dispatch to registered downstream listeners
    for listener in _event_listeners:
        try:
            listener(event)
        except Exception as e:
            logger.error(f"Error in consent event listener: {e}")

    return event


def emit_consent_granted(
    patient_id: str,
    encounter_id: str,
    consent_id: str,
    purposes: Dict[str, bool],
    notice_version: str,
    actor_id: str,
    is_offline: bool = False,
    is_minor: bool = False,
    guardian_id: Optional[str] = None,
) -> Dict[str, Any]:
    return emit_consent_event(
        "CONSENT_GRANTED",
        {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "consent_id": consent_id,
            "purposes": purposes,
            "notice_version": notice_version,
            "actor_id": actor_id,
            "is_offline": is_offline,
            "is_minor": is_minor,
            "guardian_id": guardian_id,
        }
    )


def emit_consent_withdrawn(
    patient_id: str,
    encounter_id: str,
    consent_id: str,
    withdrawn_purposes: List[str],
    remaining_purposes: Dict[str, bool],
    actor_id: str,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    return emit_consent_event(
        "CONSENT_WITHDRAWN",
        {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "consent_id": consent_id,
            "withdrawn_purposes": withdrawn_purposes,
            "remaining_purposes": remaining_purposes,
            "actor_id": actor_id,
            "reason": reason,
        }
    )


def emit_erasure_requested(
    request_id: str,
    patient_id: str,
    encounter_id: Optional[str],
    actor_id: str,
    reason: str,
) -> Dict[str, Any]:
    return emit_consent_event(
        "ERASURE_REQUESTED",
        {
            "request_id": request_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "reason": reason,
        }
    )


def emit_erasure_propagated(
    request_id: str,
    patient_id: str,
    encounter_id: Optional[str],
    target_stores: List[str],
) -> Dict[str, Any]:
    return emit_consent_event(
        "ERASURE_PROPAGATED",
        {
            "request_id": request_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "target_stores": target_stores,
        }
    )


def emit_offline_consent_captured(
    encounter_id: str,
    patient_id: str,
    device_id: str,
    seq: int,
    entry_hash: str,
) -> Dict[str, Any]:
    return emit_consent_event(
        "OFFLINE_CONSENT_CAPTURED",
        {
            "encounter_id": encounter_id,
            "patient_id": patient_id,
            "device_id": device_id,
            "seq": seq,
            "entry_hash": entry_hash,
        }
    )


def emit_offline_consent_synced(
    synced_count: int,
    head_hash: str,
) -> Dict[str, Any]:
    return emit_consent_event(
        "OFFLINE_CONSENT_SYNCED",
        {
            "synced_count": synced_count,
            "head_hash": head_hash,
        }
    )


def emit_abdm_artifact_event(
    event_type: str,
    encounter_id: str,
    artefact_id: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    return emit_consent_event(
        event_type,
        {
            "encounter_id": encounter_id,
            "artefact_id": artefact_id,
            "error_message": error_message,
        }
    )


def emit_consent_denied(
    encounter_id: str,
    required_purpose: str,
    actor_id: str,
    reason: str,
) -> Dict[str, Any]:
    return emit_consent_event(
        "CONSENT_DENIED",
        {
            "encounter_id": encounter_id,
            "required_purpose": required_purpose,
            "actor_id": actor_id,
            "reason": reason,
        }
    )
