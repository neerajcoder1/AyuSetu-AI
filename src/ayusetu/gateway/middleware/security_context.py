"""
Security Context & Dependency Injection Boundaries
===================================================
Establishes clean extension points for subsequent milestones:
  - AuthN (Milestone 3)
  - RBAC / ABAC (Milestone 4)
  - DPDP Consent Gates (Milestone 4)
  - Hash-chained Audit Log (Milestone 5)
"""

from typing import Optional
from dataclasses import dataclass
from fastapi import Request, Depends


@dataclass
class Principal:
    """Represents an authenticated caller entity."""
    actor_id: str
    actor_role: str  # 'patient' | 'companion' | 'attendant' | 'nurse' | 'physician' | 'mrd' | 'admin' | 'auditor' | 'device' | 'anonymous'
    is_authenticated: bool = False
    device_fingerprint: Optional[str] = None
    encounter_id: Optional[str] = None


def get_current_principal(request: Request) -> Principal:
    """
    Dependency provider extracting caller principal from request state/headers.
    This provides the injection point for future AuthN/AuthZ middleware.
    """
    device_id = request.headers.get("X-Device-Fingerprint") or request.headers.get("X-Device-ID")
    session_id = request.headers.get("X-Session-ID")
    auth_header = request.headers.get("Authorization")

    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # Extension point for M3 token verification
        return Principal(
            actor_id="stub-user-id",
            actor_role="physician",
            is_authenticated=True,
            device_fingerprint=device_id
        )

    if device_id:
        return Principal(
            actor_id=device_id,
            actor_role="device",
            is_authenticated=True,
            device_fingerprint=device_id,
            encounter_id=session_id
        )

    return Principal(
        actor_id="anonymous",
        actor_role="anonymous",
        is_authenticated=False,
        device_fingerprint=None
    )
