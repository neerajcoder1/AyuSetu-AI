"""
De-Identification Domain Models & Export Schemas
================================================
Authoritative Pydantic schemas for de-identified cohorts and export requests
per PRD v2.0 §21.4 and §21.9.
Guarantees ZERO raw PHI and strictly coded structured output.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ExportPurpose(str, Enum):
    RESEARCH = "research"
    QI = "qi"


class DeidExportRequest(BaseModel):
    """
    Two-person authorized request for de-identified dataset export.
    """
    date_from: str = Field(..., description="Start date (YYYY-MM-DD)")
    date_to: str = Field(..., description="End date (YYYY-MM-DD)")
    purpose: ExportPurpose = Field(default=ExportPurpose.RESEARCH, description="Export purpose: research or qi")
    approver_1: str = Field(..., description="First authorized staff approver ID")
    approver_2: str = Field(..., description="Second authorized staff approver ID (distinct from approver_1 and caller)")
    department: Optional[str] = Field(default=None, description="Optional department filter")

    model_config = ConfigDict(extra="forbid")


class DeidentifiedCodedSlot(BaseModel):
    """
    Strictly coded clinical fact representation (no narrative / free-text).
    """
    path: str = Field(..., description="Ontology path, e.g. 'symptoms.chest_pain'")
    value_coded: Optional[str] = Field(default=None, description="Standardized coded value")
    code_system: Optional[str] = Field(default=None, description="Coding system (SNOMED, ICD-10, LOINC)")
    code: Optional[str] = Field(default=None, description="Standard concept code")
    numeric_value: Optional[float] = Field(default=None, description="Non-identifying numeric measurement (e.g. SpO2)")
    boolean_value: Optional[bool] = Field(default=None, description="Boolean flag")

    model_config = ConfigDict(frozen=True, extra="forbid")


class DeidentifiedRecord(BaseModel):
    """
    De-identified encounter record compliant with PRD §21.9.
    Contains only quasi-identifiers and structured coded slots.
    """
    pseudonym_token: str = Field(..., description="Opaque pseudonymous research token (non-reversible)")
    age_band: str = Field(..., description="Age group (e.g. '20-29', '30-39', '90+')")
    sex: str = Field(..., description="Standardized sex ('male', 'female', 'other')")
    district_or_state: str = Field(..., description="District (if pop >= 20k) or Enclosing State")
    department: str = Field(..., description="Clinical department")
    visit_type: str = Field(..., description="Visit type ('new', 'followup_stable', etc.)")
    shifted_date_or_year: str = Field(..., description="Consistent shifted date (YYYY-MM-DD) or Year-Only (YYYY) if > 3 years old")
    triage_tier: Optional[int] = Field(default=None, description="RedFlag triage tier (1, 2, 3)")
    coded_slots: List[DeidentifiedCodedSlot] = Field(default_factory=list, description="Coded clinical facts")

    model_config = ConfigDict(frozen=True, extra="forbid")


class DeidExportResponse(BaseModel):
    """
    Complete de-identified dataset release payload.
    """
    export_id: str = Field(..., description="Unique export identifier UUID")
    status: str = Field(default="COMPLETED", description="Export execution status")
    purpose: str = Field(..., description="Authorized purpose ('research' or 'qi')")
    cohort_size: int = Field(..., description="Total de-identified records in dataset")
    k_anonymity_achieved: bool = Field(..., description="True if cohort satisfies k >= 5")
    min_class_size: int = Field(..., description="Size of smallest quasi-identifier equivalence class")
    records: List[DeidentifiedRecord] = Field(..., description="Cohort records")
    exported_at: str = Field(..., description="UTC ISO-8601 generation timestamp")

    model_config = ConfigDict(frozen=True)


class SafetyCheckResult(BaseModel):
    """
    Zero-PHI safety gate evaluation result.
    """
    passed: bool
    violations: List[str] = Field(default_factory=list)
    prohibited_matches: int = 0
