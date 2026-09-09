"""
AyuSetu Authentication & Authorization Package
=============================================
"""

from ayusetu.gateway.auth.models import (
    Action,
    AuthContext,
    BreakGlassContext,
    Principal,
    Resource,
    Role,
)
from ayusetu.gateway.auth.rbac import RBACPolicy, RBAC_MATRIX
from ayusetu.gateway.auth.abac import ABACEvaluator, BREAK_GLASS_ELIGIBLE_ROLES
from ayusetu.gateway.auth.device import DeviceAuthenticator, DeviceContext
from ayusetu.gateway.auth.session_auth import SessionAuthenticator, STAFF_DIRECTORY
from ayusetu.gateway.auth.dependencies import (
    get_current_principal,
    require_roles,
    require_permission,
)
from ayusetu.gateway.auth.event_hooks import (
    SecurityEvent,
    dispatch_security_event,
    register_security_event_listener,
)

__all__ = [
    "Role",
    "Action",
    "Resource",
    "Principal",
    "AuthContext",
    "BreakGlassContext",
    "RBACPolicy",
    "RBAC_MATRIX",
    "ABACEvaluator",
    "BREAK_GLASS_ELIGIBLE_ROLES",
    "DeviceAuthenticator",
    "DeviceContext",
    "SessionAuthenticator",
    "STAFF_DIRECTORY",
    "get_current_principal",
    "require_roles",
    "require_permission",
    "SecurityEvent",
    "dispatch_security_event",
    "register_security_event_listener",
]
