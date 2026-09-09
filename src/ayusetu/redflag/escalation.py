"""
Red-Flag Lifecycle & Escalation State Machine
=============================================
Manages state transitions and tier-based escalation policies per PRD v2.0 §12 & §22.9.
Validates state transitions and prevents unauthorized or contradictory lifecycle jumps.
"""

from typing import Dict, Set
from ayusetu.redflag.models import RedFlagStatus
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError


class RedFlagLifecycle:
    """Explicit state machine governing red-flag alert lifecycles."""

    VALID_TRANSITIONS: Dict[RedFlagStatus, Set[RedFlagStatus]] = {
        RedFlagStatus.DETECTED: {
            RedFlagStatus.ACKNOWLEDGED,
            RedFlagStatus.ESCALATED,
            RedFlagStatus.RESOLVED,
        },
        RedFlagStatus.ACKNOWLEDGED: {
            RedFlagStatus.ESCALATED,
            RedFlagStatus.RESOLVED,
        },
        RedFlagStatus.ESCALATED: {
            RedFlagStatus.ACKNOWLEDGED,
            RedFlagStatus.RESOLVED,
        },
        RedFlagStatus.RESOLVED: set(),  # Terminal state: resolved alerts cannot be reopened
    }

    @classmethod
    def validate_transition(cls, current: RedFlagStatus, target: RedFlagStatus) -> None:
        """
        Validate that the requested state transition is legally permissible.
        Raises 422 UNPROCESSABLE_ENTITY on invalid transition attempts.
        """
        if current == target:
            return  # Idempotent no-op

        allowed = cls.VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise AyuSetuGatewayError(
                ErrorCode.UNPROCESSABLE_ENTITY,
                f"Invalid red-flag transition: cannot transition alert from '{current.value}' to '{target.value}'",
                422,
            )


red_flag_lifecycle = RedFlagLifecycle()
