"""
Audit Service Domain Models & DTOs
==================================
Authoritative data models for the append-only, cryptographic hash-chained
audit log per PRD v2.0 §21.8 and packages/schemas/audit_event.json.
Guarantees ZERO PHI in all fields.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuditAction(str, Enum):
    """Authoritative audit action verbs per packages/schemas/audit_event.json."""
    READ = "READ"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    SIGN = "SIGN"
    EXPORT = "EXPORT"
    BREAKGLASS = "BREAKGLASS"


class AuditOutcome(str, Enum):
    """Authoritative audit outcome values."""
    ALLOW = "ALLOW"
    DENY = "DENY"


class AuditEventCreate(BaseModel):
    """
    Input schema for recording a new audit event.
    Callers supply only safe metadata; the audit service computes
    sequence numbers, timestamps, previous_hash, payload_hash, and entry_hash.
    """
    actor_id: str
    actor_role: str
    action: AuditAction
    resource_type: str
    resource_id: str
    patient_id: Optional[str] = None
    encounter_id: Optional[str] = None
    outcome: AuditOutcome = AuditOutcome.ALLOW
    reason: Optional[str] = None
    src_device: Optional[str] = None
    src_ip: Optional[str] = None
    safe_metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Safe non-PHI metadata used for payload_hash calculation"
    )

    @field_validator("actor_role", mode="before")
    def normalize_role(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value)
        return str(v)


class AuditEventDTO(BaseModel):
    """
    Immutable audit event representation matching packages/schemas/audit_event.json.
    """
    seq: int = Field(..., description="Monotonic gapless sequence number allocated by server")
    ts: str = Field(..., description="UTC ISO-8601 timestamp")
    actor_id: str = Field(..., description="UUID of actor or system principal")
    actor_role: str = Field(..., description="Role of the actor at event time")
    action: str = Field(..., description="Action verb: READ, CREATE, UPDATE, SIGN, EXPORT, BREAKGLASS")
    resource_type: str = Field(..., description="Type of target resource")
    resource_id: str = Field(..., description="UUID of target resource")
    patient_id: Optional[str] = Field(default=None, description="Patient UUID if applicable")
    encounter_id: Optional[str] = Field(default=None, description="Encounter UUID if applicable")
    outcome: str = Field(..., description="ALLOW or DENY")
    reason: Optional[str] = Field(default=None, description="Security event code or reason")
    src_device: Optional[str] = Field(default=None, description="Device identifier or fingerprint")
    src_ip: Optional[str] = Field(default=None, description="Source IP address")
    payload_hash: str = Field(..., description="SHA-256 hex of safe canonical metadata")
    prev_hash: str = Field(..., description="SHA-256 hex of previous entry in chain")
    entry_hash: str = Field(..., description="SHA-256 hex of this entry's canonical block")

    model_config = ConfigDict(frozen=True)


class AuditHeadDTO(BaseModel):
    """Represents the current tip/head of the global audit chain."""
    seq: int
    entry_hash: str
    ts: str


class OfflineAuditEventDTO(BaseModel):
    """
    Individual event recorded offline at a peripheral station/device.
    """
    local_seq: int = Field(..., description="Station-local sequence number (1, 2, ...)")
    ts: str = Field(..., description="Station UTC ISO-8601 timestamp")
    actor_id: str
    actor_role: str
    action: str
    resource_type: str
    resource_id: str
    patient_id: Optional[str] = None
    encounter_id: Optional[str] = None
    outcome: str
    reason: Optional[str] = None
    src_device: str = Field(..., description="Device ID of the recording station")
    payload_hash: str
    prev_hash: str
    entry_hash: str

    model_config = ConfigDict(frozen=True)


class OfflineAuditSyncBatch(BaseModel):
    """
    Batch payload submitted by an offline station upon reconnection.
    """
    device_id: str = Field(..., description="Authoritative device identifier")
    seed_head_hash: str = Field(..., description="Global server head hash known when station went offline")
    events: List[OfflineAuditEventDTO] = Field(..., description="Monotonically ordered offline events")


class OfflineAuditSyncResponse(BaseModel):
    """Confirmation response after successful offline batch verification and splicing."""
    status: str = "SYNCED"
    synced_count: int
    new_head: AuditHeadDTO


class AuditVerificationResult(BaseModel):
    """Structured audit log integrity verification report."""
    valid: bool
    checked_events: int
    last_valid_sequence: int
    head_hash: str
    failure: Optional[Dict[str, Any]] = None


class QuarantineRecordDTO(BaseModel):
    """Record of an invalid or tampered offline audit batch isolated in quarantine."""
    quarantine_id: str
    device_id: str
    seed_head_hash: str
    reason: str
    failure_code: str
    quarantined_at: str
    event_count: int
    safe_metadata: Dict[str, Any] = Field(default_factory=dict)
