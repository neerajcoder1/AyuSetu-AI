"""
Internal data contracts for the Document AI module (PRD §11).

These are NOT in the top-level contracts/ package because, unlike
contracts/asr_output.py or contracts/extraction.py, nothing outside this
module (yet) consumes them across a team boundary. If/when the Physician
Cockpit or a shared persistence layer starts consuming document entities
directly, promote the relevant models to contracts/ under team agreement.
"""

from datetime import date as Date
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    DIAGNOSIS = "diagnosis"
    MEDICATION = "medication"
    LAB_RESULT = "lab_result"
    IMAGING = "imaging"
    ALLERGY = "allergy"
    VITAL_SIGN = "vital_sign"
    PROVIDER = "provider"


# PRD §11.2 — Entity -> FHIR resource mapping table.
FHIR_RESOURCE_FOR_ENTITY: Dict[EntityType, str] = {
    EntityType.DIAGNOSIS: "Condition",
    EntityType.MEDICATION: "MedicationStatement",
    EntityType.LAB_RESULT: "Observation",
    EntityType.IMAGING: "DiagnosticReport",
    EntityType.ALLERGY: "AllergyIntolerance",
    EntityType.VITAL_SIGN: "Observation",
    EntityType.PROVIDER: "Practitioner",
}

# Below this, the entity renders amber in the Physician Cockpit with the
# cropped source image inline (PRD §11.2 "Confidence discipline").
REVIEW_CONFIDENCE_THRESHOLD = 0.80


class BoundingBox(BaseModel):
    page_no: int = Field(..., ge=1)
    x: float
    y: float
    width: float
    height: float


class CaptureQualityScore(BaseModel):
    """Reject-before-accept scoring at capture time (PRD §11.1)."""

    blur_score: float = Field(..., ge=0.0, le=1.0, description="1.0 = perfectly sharp")
    glare_score: float = Field(..., ge=0.0, le=1.0, description="1.0 = no glare")
    skew_score: float = Field(..., ge=0.0, le=1.0, description="1.0 = no skew")
    accepted: bool
    rejection_reasons: List[str] = Field(default_factory=list)


class OCRResult(BaseModel):
    page_no: int = Field(..., ge=1)
    raw_text: str
    mean_confidence: float = Field(..., ge=0.0, le=1.0)


class ExtractedEntity(BaseModel):
    """One structured clinical fact pulled from a document page."""

    entity_type: EntityType
    raw_text: str = Field(..., description="Verbatim OCR span this entity was derived from.")
    normalised: Dict[str, object] = Field(
        default_factory=dict, description="Structured fields, per PRD §11.2 (e.g. dose, frequency, unit)."
    )
    code_system: Optional[str] = None
    code: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox: Optional[BoundingBox] = None
    page_no: int = Field(..., ge=1)
    doc_date: Optional[Date] = None
    needs_review: bool = False

    @property
    def fhir_resource_type(self) -> str:
        return FHIR_RESOURCE_FOR_ENTITY[self.entity_type]


class DocumentAIResult(BaseModel):
    document_id: str
    quality: Optional[CaptureQualityScore] = None
    ocr: List[OCRResult] = Field(default_factory=list)
    entities: List[ExtractedEntity] = Field(default_factory=list)
