"""
AyuSetu Clinical Domain Models & DTOs
=====================================
Authoritative schemas for Encounter, Slot, and Utterance lifecycle per PRD v2.0 §10, §14, §22.3 & §22.5.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
import uuid6
from pydantic import BaseModel, ConfigDict, Field


class EncounterStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PRELIMINARY = "preliminary"
    FINAL = "final"
    ABANDONED = "abandoned"


class VisitType(str, Enum):
    NEW = "new"
    FOLLOWUP_STABLE = "followup_stable"
    FOLLOWUP_NEW = "followup_new"
    WALKIN = "walkin"


class IntakeDepth(str, Enum):
    FAST = "fast"
    INTERVAL = "interval"
    DELTA = "delta"
    FULL = "full"


class Channel(str, Enum):
    KIOSK = "kiosk"
    PWA_SELF = "pwa_self"
    PWA_COMPANION = "pwa_companion"
    ASSISTED = "assisted"


class ReportedBy(str, Enum):
    PATIENT = "patient"
    COMPANION = "companion"
    ATTENDANT = "attendant"
    CLINICIAN = "clinician"


class SlotSource(str, Enum):
    UTTERANCE = "utterance"
    TOUCH = "touch"
    DOCUMENT = "document"
    DERIVED = "derived"
    CLINICIAN = "clinician"


class EncounterDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid6.uuid7()))
    patient_id: str
    department: str = Field(default="Kayachikitsa")
    visit_type: VisitType = Field(default=VisitType.NEW)
    intake_depth: IntakeDepth = Field(default=IntakeDepth.FULL)
    channel: Channel = Field(default=Channel.KIOSK)
    reported_by: Optional[ReportedBy] = Field(default=ReportedBy.PATIENT)
    language: Optional[str] = Field(default="hi")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: Optional[datetime] = None
    status: EncounterStatus = Field(default=EncounterStatus.DRAFT)


class UtteranceDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid6.uuid7()))
    encounter_id: str
    seq: int = Field(..., ge=1)
    speaker: str = Field(..., description="'patient' or 'system'")
    text: str
    lang: str = Field(default="hi")
    asr_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    audio_uri: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SlotDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid6.uuid7()))
    encounter_id: str
    path: str = Field(..., description="Ontology path, e.g. 'hpi.severity', 'allergies.drug'")
    value: Any = None
    value_coded: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source: SlotSource = Field(default=SlotSource.UTTERANCE)
    source_ref: Optional[str] = None
    reported_by: ReportedBy = Field(default=ReportedBy.PATIENT)
    elicited: bool = Field(default=True, description="False indicates explicit absence/unelicited, never assumed negative")


class SessionSubmissionRequest(BaseModel):
    confirmed_by: ReportedBy = Field(default=ReportedBy.PATIENT)
    readback_accepted: bool = Field(default=True)


class SessionSubmissionResponse(BaseModel):
    encounter_id: str
    status: str = "submitted"
    summary_status: str = "generating"
    poll_after_ms: int = 1500
    session_purged: bool = True
    slots_persisted: int = 0
    utterances_persisted: int = 0
    redflags_detected: int = 0
