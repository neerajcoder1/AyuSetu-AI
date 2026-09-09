"""
AyuSetu Authentication & Authorization Models
=============================================
Authoritative principal models, roles, resources, and action definitions per PRD v2.0 §21.3 & §21.4.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class Role(str, Enum):
    """The 8 authoritative roles specified in PRD §21.4."""
    PATIENT = "patient"
    COMPANION = "companion"
    ATTENDANT = "attendant"
    NURSE = "nurse"
    PHYSICIAN = "physician"
    MRD = "mrd"
    ADMIN = "admin"
    AUDITOR = "auditor"


class Action(str, Enum):
    """Actions mapped from RBAC matrix CRUD+S."""
    CREATE = "C"
    READ = "R"
    UPDATE = "U"
    DELETE = "D"
    SIGN = "S"
    EXPORT = "EXPORT"
    BREAKGLASS = "BREAKGLASS"


class Resource(str, Enum):
    """Protected resources from PRD §21.4 RBAC Matrix."""
    OWN_DRAFT_SESSION = "own_draft_session"
    OTHER_PATIENT_SESSION = "other_patient_session"
    SIGNED_CLINICAL_RECORD = "signed_clinical_record"
    UPLOADED_DOCUMENTS = "uploaded_documents"
    TIER1_ALERT_QUEUE = "tier1_alert_queue"
    CONSENT_RECORD = "consent_record"
    CLINICAL_CONTENT = "clinical_content"
    AUDIT_LOG = "audit_log"
    DEID_EXPORT = "deid_export"
    USER_ADMINISTRATION = "user_administration"


class Principal(BaseModel):
    """Authenticated caller identity."""
    actor_id: str
    role: Role
    is_authenticated: bool = True
    department: Optional[str] = None
    assigned_encounter_ids: Set[str] = Field(default_factory=set)
    device_fingerprint: Optional[str] = None
    encounter_id: Optional[str] = None
    patient_id: Optional[str] = None
    is_companion: bool = False
    session_token: Optional[str] = None


class BreakGlassContext(BaseModel):
    """Break-glass emergency authorization override context per PRD §21.4."""
    is_break_glass: bool = False
    reason: Optional[str] = None
    overridden_encounter_id: Optional[str] = None
    timestamp: Optional[str] = None


class AuthContext(BaseModel):
    """Complete authorization context evaluated by ABAC engine."""
    principal: Principal
    resource: Resource
    action: Action
    target_patient_id: Optional[str] = None
    target_encounter_id: Optional[str] = None
    target_department: Optional[str] = None
    encounter_age_hours: Optional[float] = None
    break_glass: Optional[BreakGlassContext] = None
    is_author: bool = False
