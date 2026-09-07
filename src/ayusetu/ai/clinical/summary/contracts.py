"""
Internal data contracts for the structured clinical summary generator
(PRD §13). Sections mirror the table in §13.2; status transitions mirror
the `summary_version` / `summary_edit` tables in §22.3.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SummaryStatus(str, Enum):
    PRELIMINARY = "preliminary"
    FINAL = "final"


class RejectionReason(str, Enum):
    """PRD §13.3 — "Reasons are captured as a taxonomy"."""

    WRONG = "wrong"
    INCOMPLETE = "incomplete"
    IRRELEVANT = "irrelevant"
    UNSAFE = "unsafe"


class NarrativeClause(BaseModel):
    """One hoverable clause of generated narrative text, always traceable
    to the slot(s) it was built from (PRD §14.1 hover-to-source)."""

    text: str
    source_slots: List[str] = Field(default_factory=list)
    entailed: bool = True


class CodingCandidate(BaseModel):
    system: str  # "NAMASTE" | "ICD-11-TM2" | "ICD-11-MMS"
    code: str
    display: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class SummaryAlert(BaseModel):
    tier: int
    title: str
    acknowledged: bool = False


class HeaderSection(BaseModel):
    department: Optional[str] = None
    language_used: Optional[str] = None
    intake_channel: Optional[str] = None
    assisted: bool = False
    duration_seconds: Optional[int] = None


class StructuredField(BaseModel):
    """A single collapsible field in past/drug/allergy/family/personal/ROS,
    explicitly rendered "not elicited" rather than left null (Gate 5)."""

    label: str
    value: Optional[str] = None
    elicited: bool = True

    @property
    def display_value(self) -> str:
        return self.value if self.elicited and self.value else "not elicited"


class ClinicalSummary(BaseModel):
    encounter_id: str
    version: int = 1
    status: SummaryStatus = SummaryStatus.PRELIMINARY
    model_version: str = "rule-based-v1"

    header: HeaderSection = Field(default_factory=HeaderSection)
    alerts: List[SummaryAlert] = Field(default_factory=list)
    chief_complaint: Optional[str] = None
    hpi_narrative: List[NarrativeClause] = Field(default_factory=list)
    structured_history: Dict[str, StructuredField] = Field(default_factory=dict)
    suggested_coding: List[CodingCandidate] = Field(default_factory=list)

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    signed_by: Optional[str] = None
    signed_at: Optional[datetime] = None


class SummaryEdit(BaseModel):
    slot_path: str
    old_value: Optional[str]
    new_value: Optional[str]
    reason: Optional[str] = None
    edited_by: str
    edited_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SummaryRejection(BaseModel):
    reason: RejectionReason
    detail: Optional[str] = None
    rejected_by: str
    rejected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
