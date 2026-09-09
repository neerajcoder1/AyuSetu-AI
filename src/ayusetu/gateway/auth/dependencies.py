"""
FastAPI Authentication & Authorization Dependencies
===================================================
Provides declarative route protection dependencies:
  - get_current_principal
  - require_roles
  - require_permission
  - require_encounter_access
"""

from typing import Callable, List, Optional
from fastapi import Depends, Header, HTTPException, Request, status

from ayusetu.gateway.auth.models import (
    Action,
    AuthContext,
    BreakGlassContext,
    Principal,
    Resource,
    Role,
)
from ayusetu.gateway.auth.session_auth import SessionAuthenticator
from ayusetu.gateway.auth.abac import ABACEvaluator
from ayusetu.gateway.auth.event_hooks import dispatch_security_event
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError

authenticator = SessionAuthenticator()


def get_current_principal(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_session_id: Optional[str] = Header(None),
    x_device_fingerprint: Optional[str] = Header(None),
) -> Principal:
    """
    Dependency extracting authenticated Principal from request credentials.
    """
    # Also check cookie if header missing
    session_id = x_session_id or request.cookies.get("session_id")
    
    # Check if session ID is in path (e.g. /api/v1/sessions/{id}/...)
    path_parts = request.url.path.strip("/").split("/")
    if len(path_parts) >= 3 and path_parts[1] == "sessions":
        session_id = session_id or path_parts[2]

    principal = authenticator.authenticate_token(
        auth_header=authorization,
        session_id_header=session_id,
        device_fingerprint=x_device_fingerprint,
    )
    request.state.principal = principal
    return principal


def require_roles(*allowed_roles: Role) -> Callable:
    """
    Dependency factory enforcing RBAC role membership.
    """
    def _role_checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in allowed_roles:
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Access denied: insufficient role privileges",
                403
            )
        return principal

    return _role_checker


def require_permission(resource: Resource, action: Action) -> Callable:
    """
    Dependency factory checking static RBAC and contextual ABAC policy.
    """
    def _perm_checker(
        request: Request,
        principal: Principal = Depends(get_current_principal),
        x_break_glass_reason: Optional[str] = Header(None),
    ) -> Principal:
        # Extract target encounter / patient from path if present
        path_params = request.path_params
        target_enc = path_params.get("id") or path_params.get("encounter_id")
        target_pat = path_params.get("patient_id")

        break_glass = None
        if x_break_glass_reason:
            break_glass = BreakGlassContext(
                is_break_glass=True,
                reason=x_break_glass_reason,
                overridden_encounter_id=target_enc
            )

        auth_ctx = AuthContext(
            principal=principal,
            resource=resource,
            action=action,
            target_encounter_id=target_enc,
            target_patient_id=target_pat,
            break_glass=break_glass
        )

        allowed, reason = ABACEvaluator.evaluate(auth_ctx)

        # If break-glass was used, dispatch audit/security event
        if break_glass and break_glass.is_break_glass and allowed:
            dispatch_security_event(
                event_type="BREAK_GLASS",
                actor_id=principal.actor_id,
                actor_role=principal.role.value,
                target_resource=resource.value,
                target_encounter_id=target_enc,
                reason=x_break_glass_reason,
            )

        if not allowed:
            # If IDOR attempt detected on another patient's record, log security event
            if "foreign" in reason.lower():
                dispatch_security_event(
                    event_type="IDOR_ATTEMPT",
                    actor_id=principal.actor_id,
                    actor_role=principal.role.value,
                    target_resource=resource.value,
                    target_encounter_id=target_enc,
                    reason="Attempted unauthorized cross-patient resource access"
                )

            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Access denied by security policy",
                403
            )

        return principal

    return _perm_checker
