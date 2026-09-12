"""
Replay Protection & Nonce Verification Guard
=============================================
Authoritative replay defense module per PRD v3 §21.4 and SEC-T-05.
Enforces:
1. 90-second freshness window for timestamped requests.
2. Unique nonce validation with TTL tracking to prevent replay attacks.
"""

import time
from datetime import datetime, timezone
from typing import Dict, Optional, Set
from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode
from ayusetu.gateway.auth.event_hooks import dispatch_security_event

REPLAY_WINDOW_SECONDS: float = 90.0


class ReplayGuard:
    """In-memory nonce tracker and timestamp freshness validator."""

    def __init__(self, window_seconds: float = REPLAY_WINDOW_SECONDS) -> None:
        self.window_seconds = window_seconds
        self._nonces: Dict[str, float] = {}  # nonce -> expiry_timestamp

    def _purge_expired(self, now: float) -> None:
        """Purge nonces that are past their freshness window."""
        expired = [nonce for nonce, exp in self._nonces.items() if exp < now]
        for nonce in expired:
            self._nonces.pop(nonce, None)

    def validate_request(
        self,
        nonce: Optional[str] = None,
        timestamp: Optional[float] = None,
        actor_id: str = "anonymous",
        actor_role: str = "caller",
        endpoint: str = "api",
    ) -> bool:
        """
        Validate request freshness and nonce uniqueness.
        Raises AyuSetuGatewayError (401) on replay or expired window.
        """
        now = time.time()
        self._purge_expired(now)

        # 1. Timestamp freshness check
        if timestamp is not None:
            skew = abs(now - timestamp)
            if skew > self.window_seconds:
                dispatch_security_event(
                    event_type="REPLAY_ATTACK_DETECTED",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    target_resource=endpoint,
                    reason=f"Request timestamp outside allowed replay window: skew={skew:.2f}s > {self.window_seconds}s",
                    metadata={"timestamp": timestamp, "skew_seconds": skew, "nonce": nonce},
                )
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    f"Request timestamp expired (clock skew {skew:.1f}s exceeds {self.window_seconds}s replay window)",
                    401,
                )

        # 2. Nonce reuse check
        if nonce:
            if nonce in self._nonces:
                dispatch_security_event(
                    event_type="REPLAY_ATTACK_DETECTED",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    target_resource=endpoint,
                    reason=f"Duplicate nonce detected within replay window: {nonce}",
                    metadata={"nonce": nonce, "actor_id": actor_id},
                )
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    f"Nonce reuse detected: request nonce '{nonce}' has already been processed within replay window",
                    401,
                )
            self._nonces[nonce] = now + self.window_seconds

        return True

    def clear(self) -> None:
        """Clear nonce cache (for testing)."""
        self._nonces.clear()


replay_guard = ReplayGuard()
