from typing import List, Optional
from pydantic import BaseModel, Field
from contracts.dialogue import ClinicalSlot

class ExtractedSlot(BaseModel):
    """
    Represents a single piece of clinical information extracted from the patient's speech.
    """
    slot: ClinicalSlot
    value: str
    confidence: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Confidence that the transcribed text contains this clinical information. "
                    "(Distinct from ASR confidence, which measures audio transcription quality)."
    )
    evidence: Optional[str] = Field(
        None, 
        description="The exact substring or reasoning from the transcript supporting this extraction."
    )

class ExtractionResult(BaseModel):
    """
    The strict contract Sai's ClinicalExtractor must return.
    """
    extractions: List[ExtractedSlot] = Field(default_factory=list)
