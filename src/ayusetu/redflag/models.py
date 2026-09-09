"""
Red-Flag Engine Domain Models & DTOs
====================================
Authoritative models for clinical red-flag detection, tiered severity escalation,
and lifecycle management per PRD v2.0 and packages/schemas/red_flag_event.json.
Guarantees deterministic non-diagnostic execution and zero PHI.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RedFlagTier(int, Enum):
    """Authoritative 3-tier severity classification per PRD v2.0."""
    TIER_1 = 1  # Emergency / Life-threatening (90s Nursing, 180s DMO escalation)
    TIER_2 = 2  # Urgent / High Priority (Physician Cockpit queue priority flag)
    TIER_3 = 3  # Clinical Warning / Cautionary (EHR preview caution badge)


class RedFlagStatus(str, Enum):
    """Lifecycle status of a red-flag event."""
    DETECTED = "detected"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class StructuredClinicalFact(BaseModel):
    """
    Structured clinical slot or parameter supplied by authoritative intake sources.
    Does NOT accept unverified or free-form LLM text.
    """
    path: str = Field(..., description="Ontology slot path, e.g. 'symptoms.chest_pain', 'vitals.spo2'")
    value: Any = Field(..., description="Typed structured value: bool, number, or standard coded string")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Extraction confidence score")
    elicited: bool = Field(default=True, description="False indicates not elicited, never a negative assumption")


class RedFlagEvaluateRequest(BaseModel):
    """Input payload for evaluating red-flag rules against encounter facts."""
    encounter_id: str = Field(..., description="Target encounter UUID")
    facts: List[StructuredClinicalFact] = Field(..., description="List of structured clinical facts to evaluate")


class RedFlagEventDTO(BaseModel):
    """
    Immutable representation matching packages/schemas/red_flag_event.json.
    trigger_text contains ONLY deterministic rule descriptions, never raw patient transcripts.
    """
    id: str = Field(..., description="Event UUID v7")
    encounter_id: str = Field(..., description="Encounter UUID")
    rule_id: str = Field(..., description="Clinical rule identifier, e.g. 'RF-CARD-001'")
    tier: int = Field(..., ge=1, le=3, description="Severity tier: 1, 2, or 3")
    trigger_text: str = Field(..., description="Deterministic non-PHI rule description template")
    detected_at: str = Field(..., description="UTC ISO-8601 detection timestamp")
    acknowledged_by: Optional[str] = Field(default=None, description="UUID of clinician who acknowledged")
    acknowledged_at: Optional[str] = Field(default=None, description="UTC ISO-8601 acknowledgement timestamp")
    outcome: Optional[str] = Field(default=None, description="Resolution outcome description or action taken")
    status: RedFlagStatus = Field(default=RedFlagStatus.DETECTED, description="Current lifecycle state")

    model_config = ConfigDict(frozen=True)


class AcknowledgeRequest(BaseModel):
    """Clinician acknowledgement payload."""
    notes: Optional[str] = Field(default=None, description="Optional non-PHI acknowledgement note")


class EscalateRequest(BaseModel):
    """Clinician escalation payload."""
    target_role: Optional[str] = Field(default="duty_medical_officer", description="Target escalation tier role")
    notes: Optional[str] = Field(default=None, description="Optional non-PHI escalation rationale")


class ResolveRequest(BaseModel):
    """Clinician resolution payload."""
    outcome: str = Field(..., description="Action taken or outcome, e.g. 'TRIAGED_TO_ER', 'STABILIZED', 'DISMISSED_FALSE_POSITIVE'")
    notes: Optional[str] = Field(default=None, description="Optional resolution note")


class Tier1AlertQueueItem(BaseModel):
    """Real-time item in the Tier-1 Emergency Alert Queue."""
    event: RedFlagEventDTO
    encounter_id: str
    detected_at: str
    seconds_since_detection: int
    escalation_level: int = Field(default=0, description="0=Nursing, 1=DMO (90s), 2=Senior (180s)")
    is_overdue: bool = False
