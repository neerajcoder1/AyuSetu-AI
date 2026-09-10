"""
Session & Token Authentication Engine
======================================
Validates Redis-backed opaque 256-bit session tokens, staff SSO tokens,
and enforces 30-minute session TTL and revocation per PRD v2.0 §21.3 & §21.6.
"""

from typing import Any, Dict, Optional, Set
from ayusetu.common.config import settings
from ayusetu.common.session_cache import SessionCache, TOKEN_PREFIX
from ayusetu.gateway.auth.models import Principal, Role
from ayusetu.gateway.auth.device import DeviceAuthenticator
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError


# ==============================================================================
# Development-Only Staff Identity Adapter
# ==============================================================================
# Development-only staff identity adapter. Production deployment MUST replace
# this adapter with validation of Hospital OIDC/SSO-issued credentials.
# This in-memory directory and 'staff-token-*' scheme are strictly for
# development/demo/testing and will not be used in production.
# ==============================================================================
STAFF_DIRECTORY: Dict[str, Dict[str, Any]] = {
    "dr-aparna": {
        "actor_id": "usr-phy-001",
        "role": Role.PHYSICIAN,
        "department": "Kayachikitsa",
        "assigned_encounters": {"018f0000-0000-7000-8000-000000000011", "018f0000-0000-7000-8000-000000000012"},
    },
    "dr-verma": {
        "actor_id": "usr-phy-002",
        "role": Role.PHYSICIAN,
        "department": "Panchakarma",
        "assigned_encounters": {"018f0000-0000-7000-8000-000000000012"},
    },
    "nurse-sunita": {
        "actor_id": "usr-nur-001",
        "role": Role.NURSE,
        "department": "Kayachikitsa",
        "assigned_encounters": {"018f0000-0000-7000-8000-000000000011"},
    },
    "attendant-ravi": {
        "actor_id": "usr-att-001",
        "role": Role.ATTENDANT,
        "department": "Kayachikitsa",
        "assigned_encounters": {"018f0000-0000-7000-8000-000000000011", "018f0000-0000-7000-8000-000000000013"},
    },
    "mrd-officer": {
        "actor_id": "usr-mrd-001",
        "role": Role.MRD,
        "department": "MedicalRecords",
        "assigned_encounters": set(),
    },
    "admin-sys": {
        "actor_id": "usr-adm-001",
        "role": Role.ADMIN,
        "department": "IT",
        "assigned_encounters": set(),
    },
    "auditor-certin": {
        "actor_id": "usr-aud-001",
        "role": Role.AUDITOR,
        "department": "Audit",
        "assigned_encounters": set(),
    },
}


class SessionAuthenticator:
    """Authenticates requests via Redis session tokens or Staff Bearer credentials."""

    def __init__(self, session_cache: Optional[SessionCache] = None):
        self.session_cache = session_cache or SessionCache()

    def authenticate_token(
        self,
        auth_header: Optional[str],
        session_id_header: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
    ) -> Principal:
        """
        Resolve Principal from Bearer token or session token.
        Raises AyuSetuGatewayError on failure.
        """
        # 1. Check Device CRL Revocation first if fingerprint provided
        if device_fingerprint:
            try:
                DeviceAuthenticator.validate_device(device_fingerprint)
            except PermissionError as e:
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    "Access denied: client device certificate has been revoked",
                    403
                )

        # 2. Check Bearer Authorization Header
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            
            # Development-only staff identity adapter.
            # In production, this dev adapter is disabled and strictly fails closed.
            if settings.AYUSETU_ENV != "prod":
                for username, staff_data in STAFF_DIRECTORY.items():
                    if token == f"staff-token-{username}":
                        return Principal(
                            actor_id=staff_data["actor_id"],
                            role=staff_data["role"],
                            department=staff_data.get("department"),
                            assigned_encounter_ids=set(staff_data.get("assigned_encounters", set())),
                            device_fingerprint=device_fingerprint,
                            session_token=token,
                            is_authenticated=True,
                        )
            else:
                if token.startswith("staff-token-"):
                    raise AyuSetuGatewayError(
                        ErrorCode.POLICY_DENIED,
                        "Development staff tokens are forbidden in production environment. Hospital SSO/OIDC required.",
                        403,
                    )

            # Check if token is a Redis 256-bit session token
            # Look up session mapped to this token
            session_id = self._lookup_session_by_token(token) or session_id_header or token
            session = self.session_cache.get_session(session_id)
            if session and session.get("token") == token:
                return self._principal_from_session(session, device_fingerprint)

            raise AyuSetuGatewayError(
                ErrorCode.SESSION_EXPIRED,
                "Authentication credentials invalid or expired",
                401
            )


        # 3. Check Session ID Header / Kiosk session lookup
        if session_id_header:
            session = self.session_cache.get_session(session_id_header)
            if not session:
                raise AyuSetuGatewayError(
                    ErrorCode.SESSION_EXPIRED,
                    "Session expired or not found",
                    401
                )
            return self._principal_from_session(session, device_fingerprint)

        # 4. Anonymous caller
        raise AyuSetuGatewayError(
            ErrorCode.SESSION_EXPIRED,
            "Authentication required",
            401
        )

    def _lookup_session_by_token(self, token: str) -> Optional[str]:
        """Lookup session ID by 256-bit token from Redis."""
        try:
            from ayusetu.common.redis_client import get_redis_client
            client = get_redis_client()
            return client.get(f"{TOKEN_PREFIX}{token}")
        except Exception:
            from ayusetu.common.session_cache import _in_memory_tokens
            return _in_memory_tokens.get(token)

    def _principal_from_session(self, session: Dict[str, Any], device_fp: Optional[str]) -> Principal:
        channel = session.get("channel", "kiosk")
        is_companion = channel == "pwa_companion"
        role = Role.COMPANION if is_companion else Role.PATIENT

        return Principal(
            actor_id=session.get("patient_id") or session.get("session_id"),
            role=role,
            encounter_id=session.get("encounter_id"),
            patient_id=session.get("patient_id"),
            device_fingerprint=device_fp or session.get("device_fingerprint"),
            is_companion=is_companion,
            session_token=session.get("token"),
            is_authenticated=True,
        )

    def logout_session(self, token_or_session_id: str) -> bool:
        """Revoke active session and tokens."""
        session_id = self._lookup_session_by_token(token_or_session_id) or token_or_session_id
        return self.session_cache.panic_clear(session_id)
