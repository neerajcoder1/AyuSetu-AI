"""
Internal data contracts for patient history/timeline building.

Mirrors the provenance discipline of the PRD §22.3 `slot` table: every
TimelineEvent carries `source` + `source_ref` so the Physician Cockpit's
hover-to-source behaviour (§14.1) works for history, not just the live
summary. `elicited` distinguishes "the patient said no" from "we never
asked" for the same reason Gate 5 needs it in Module C (§13.1).
"""

from datetime import date as Date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TimelineEventType(str, Enum):
    ENCOUNTER = "encounter"
    CHIEF_COMPLAINT = "chief_complaint"
    SYMPTOM = "symptom"
    DIAGNOSIS = "diagnosis"
    MEDICATION = "medication"
    LAB_RESULT = "lab_result"
    ALLERGY = "allergy"
    VITAL_SIGN = "vital_sign"
    RED_FLAG = "red_flag"


class SourceKind(str, Enum):
    UTTERANCE = "utterance"
    DOCUMENT = "document"
    DERIVED = "derived"
    CLINICIAN = "clinician"


class TimelineEvent(BaseModel):
    encounter_id: str
    date: Optional[Date] = None
    event_type: TimelineEventType
    title: str
    detail: str
    source: SourceKind
    source_ref: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    elicited: bool = True


class EncounterSnapshot(BaseModel):
    """
    One encounter's worth of clinical facts, already extracted by upstream
    modules (dialogue engine's DialogueState + Document AI's ExtractedEntity
    list), ready to fold into the longitudinal patient timeline.
    """

    encounter_id: str
    date: Optional[Date] = None
    collected_info: dict = Field(default_factory=dict, description="ClinicalSlot -> value, from DialogueState.")
    missing_slots: list = Field(default_factory=list)
    document_entities: list = Field(default_factory=list, description="List[ExtractedEntity]")
    red_flag_titles: list = Field(default_factory=list)
