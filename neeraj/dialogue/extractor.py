from typing import Protocol
from contracts.dialogue import ClinicalSlot
from contracts.extraction import ExtractionResult, ExtractedSlot

class ClinicalExtractor(Protocol):
    """
    Interface for extracting structured clinical information from patient speech.
    Sai will implement a concrete version of this using Document AI / NLP.
    """
    def extract(self, text: str) -> ExtractionResult:
        ...

class DeterministicPlaceholderExtractor(ClinicalExtractor):
    """
    PLACEHOLDER ONLY.
    Uses hardcoded deterministic fixtures to mock extraction for testing the state machine.
    This ensures the state machine is tested completely independently of an LLM.
    """
    def extract(self, text: str) -> ExtractionResult:
        text_lower = text.lower()
        extractions = []
        
        # Mock Rule 1: "मुझे दो दिन से पेट में दर्द है"
        if "पेट में दर्द" in text_lower or "stomach" in text_lower or "pain" in text_lower:
            extractions.append(ExtractedSlot(
                slot=ClinicalSlot.CHIEF_COMPLAINT,
                value="Stomach pain (पेट में दर्द)",
                confidence=0.95,
                evidence="stomach/pain/पेट में दर्द"
            ))
            
        if "दो दिन" in text_lower or "2 days" in text_lower or "do din" in text_lower:
            extractions.append(ExtractedSlot(
                slot=ClinicalSlot.DURATION,
                value="2 days",
                confidence=0.91,
                evidence="2 days/दो दिन"
            ))
            
        # Mock Rule 2: Associated symptoms
        if "fever" in text_lower or "बुखार" in text_lower:
            extractions.append(ExtractedSlot(
                slot=ClinicalSlot.ASSOCIATED_SYMPTOMS,
                value="Fever",
                confidence=0.88,
                evidence="fever"
            ))
            
        # Mock Rule 3: Lifestyle
        if "smoking" in text_lower or "smoke" in text_lower:
            extractions.append(ExtractedSlot(
                slot=ClinicalSlot.LIFESTYLE,
                value="Smokes occasionally",
                confidence=0.99,
                evidence="smoke"
            ))
            
        return ExtractionResult(extractions=extractions)
