"""
RBAC (Role-Based Access Control) Matrix
========================================
Authoritative RBAC permission engine per PRD v2.0 §21.4.
Enforces static role-to-resource permission sets with strict deny-by-default.
"""

from typing import Dict, Set
from ayusetu.gateway.auth.models import Role, Resource, Action

# Mapping: (Role, Resource) -> Set of permitted Actions (C, R, U, D, S, EXPORT)
RBAC_MATRIX: Dict[Role, Dict[Resource, Set[Action]]] = {
    Role.PATIENT: {
        Resource.OWN_DRAFT_SESSION: {Action.CREATE, Action.READ, Action.UPDATE},
        Resource.SIGNED_CLINICAL_RECORD: {Action.READ},
        Resource.UPLOADED_DOCUMENTS: {Action.CREATE, Action.READ},
        Resource.CONSENT_RECORD: {Action.CREATE, Action.READ, Action.UPDATE},
    },
    Role.COMPANION: {
        Resource.OWN_DRAFT_SESSION: {Action.CREATE, Action.READ, Action.UPDATE},
        Resource.UPLOADED_DOCUMENTS: {Action.CREATE, Action.READ},
        # Companion may NOT consent per PRD §21.3 & §23.5
    },
    Role.ATTENDANT: {
        Resource.OWN_DRAFT_SESSION: {Action.CREATE, Action.READ, Action.UPDATE},
        Resource.OTHER_PATIENT_SESSION: {Action.READ},
        Resource.UPLOADED_DOCUMENTS: {Action.CREATE, Action.READ},
        Resource.TIER1_ALERT_QUEUE: {Action.READ},
        Resource.CONSENT_RECORD: {Action.READ},
    },
    Role.NURSE: {
        Resource.OWN_DRAFT_SESSION: {Action.READ},
        Resource.OTHER_PATIENT_SESSION: {Action.READ},
        Resource.SIGNED_CLINICAL_RECORD: {Action.READ},
        Resource.UPLOADED_DOCUMENTS: {Action.READ},
        Resource.TIER1_ALERT_QUEUE: {Action.READ, Action.UPDATE},
        Resource.CONSENT_RECORD: {Action.READ},
    },
    Role.PHYSICIAN: {
        Resource.OWN_DRAFT_SESSION: {Action.READ},
        Resource.OTHER_PATIENT_SESSION: {Action.READ},
        Resource.SIGNED_CLINICAL_RECORD: {Action.READ, Action.UPDATE, Action.SIGN},
        Resource.UPLOADED_DOCUMENTS: {Action.READ},
        Resource.TIER1_ALERT_QUEUE: {Action.READ, Action.UPDATE},
        Resource.CONSENT_RECORD: {Action.READ},
        Resource.CLINICAL_CONTENT: {Action.READ},
    },
    Role.MRD: {
        Resource.SIGNED_CLINICAL_RECORD: {Action.READ},
        Resource.UPLOADED_DOCUMENTS: {Action.READ, Action.DELETE},
        Resource.CONSENT_RECORD: {Action.READ},
        Resource.DEID_EXPORT: {Action.READ, Action.EXPORT},
    },
    Role.ADMIN: {
        Resource.TIER1_ALERT_QUEUE: {Action.READ},
        Resource.CLINICAL_CONTENT: {Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE},
        Resource.USER_ADMINISTRATION: {Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE},
    },
    Role.AUDITOR: {
        Resource.TIER1_ALERT_QUEUE: {Action.READ},
        Resource.CONSENT_RECORD: {Action.READ},
        Resource.CLINICAL_CONTENT: {Action.READ},
        Resource.AUDIT_LOG: {Action.READ},
        Resource.DEID_EXPORT: {Action.READ},
        Resource.USER_ADMINISTRATION: {Action.READ},
        # Auditor has zero modification/write permissions across clinical records
    },
}


class RBACPolicy:
    """Evaluates role-based static permissions."""

    @classmethod
    def is_permitted(cls, role: Role, resource: Resource, action: Action) -> bool:
        """
        Check if role has permission for resource action.
        Returns False by default if not explicitly permitted.
        """
        role_perms = RBAC_MATRIX.get(role, {})
        allowed_actions = role_perms.get(resource, set())
        return action in allowed_actions
