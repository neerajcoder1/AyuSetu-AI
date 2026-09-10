from enum import Enum
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class ClinicalSlot(str, Enum):
    CHIEF_COMPLAINT = "chief_complaint"
    ONSET = "onset"
    DURATION = "duration"
    LOCATION = "location"
    SEVERITY = "severity"
    ASSOCIATED_SYMPTOMS = "associated_symptoms"
    AGGRAVATING_RELIEVING = "aggravating_relieving"
    PAST_MEDICAL_HISTORY = "past_medical_history"
    MEDICATIONS = "medications"
    ALLERGIES = "allergies"
    FAMILY_HISTORY = "family_history"
    LIFESTYLE = "lifestyle"

class DialogueTurn(BaseModel):
    speaker: str  # "patient" or "system"
    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None

class SlotCorrection(BaseModel):
    slot: ClinicalSlot
    previous_value: str
    updated_value: str
    update_reason: str = "patient_correction"

class DialogueState(BaseModel):
    collected_info: Dict[ClinicalSlot, str] = Field(default_factory=dict)
    corrections: List[SlotCorrection] = Field(default_factory=list)
    missing_slots: List[ClinicalSlot] = Field(default_factory=list)
    history: List[DialogueTurn] = Field(default_factory=list)
    needs_clarification: bool = False
    is_complete: bool = False
    preferred_language: str = "hinglish"

class PlannerAction(BaseModel):
    next_slot: Optional[ClinicalSlot] = None
    question_intent: Optional[str] = None
    is_complete: bool = False
    needs_clarification: bool = False
