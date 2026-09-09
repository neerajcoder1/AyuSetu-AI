"""
Security Event Hooks Interface
==============================
Provides clean event dispatch boundaries for security & break-glass events.
Designed for seamless consumption by the future Milestone 5 Audit Service.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel

logger = logging.getLogger("ayusetu.security.events")


class SecurityEvent(BaseModel):
    """Structured security / break-glass event payload."""
    event_type: str  # "BREAK_GLASS" | "AUTH_FAILED" | "DEVICE_REVOKED" | "IDOR_ATTEMPT"
    actor_id: str
    actor_role: str
    target_resource: str
    target_encounter_id: Optional[str] = None
    target_patient_id: Optional[str] = None
    reason: Optional[str] = None
    timestamp: str
    metadata: Dict[str, Any] = {}


# Registered listeners for security events (Audit service hook point)
_event_listeners: List[Callable[[SecurityEvent], None]] = []


def register_security_event_listener(listener: Callable[[SecurityEvent], None]) -> None:
    """Register downstream listener (e.g. Audit service, SIEM, Ops Console)."""
    _event_listeners.append(listener)


def dispatch_security_event(
    event_type: str,
    actor_id: str,
    actor_role: str,
    target_resource: str,
    target_encounter_id: Optional[str] = None,
    target_patient_id: Optional[str] = None,
    reason: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SecurityEvent:
    """
    Dispatch security event to registered listeners and secure logs.
    Never logs sensitive patient medical data.
    """
    event = SecurityEvent(
        event_type=event_type,
        actor_id=actor_id,
        actor_role=actor_role,
        target_resource=target_resource,
        target_encounter_id=target_encounter_id,
        target_patient_id=target_patient_id,
        reason=reason,
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata=metadata or {},
    )

    logger.warning(
        "SECURITY EVENT [%s]: Actor %s (%s) on %s, encounter=%s. Reason: %s",
        event.event_type,
        event.actor_id,
        event.actor_role,
        event.target_resource,
        event.target_encounter_id,
        event.reason,
    )

    for listener in _event_listeners:
        try:
            listener(event)
        except Exception as e:
            logger.error("Failed to notify security event listener: %s", e)

    return event
