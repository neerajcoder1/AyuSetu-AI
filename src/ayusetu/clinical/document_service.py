"""
Document AI Processing Service
==============================
Authoritative service coordinating capture-time quality scoring (PRD §11.1),
OCR provider execution, and structured clinical entity extraction (PRD §11.2).
"""

from typing import Any, Dict, List, Optional
import uuid6

from ayusetu.ai.clinical.document_ai.capture_quality import score_capture, CaptureQualityScore
from ayusetu.ai.clinical.document_ai.contracts import (
    DocumentAIResult,
    ExtractedEntity,
    OCRResult,
    REVIEW_CONFIDENCE_THRESHOLD,
)
from ayusetu.ai.clinical.document_ai.entity_extractor import extract_entities
from ayusetu.ai.clinical.document_ai.ocr import MockOCRProvider, OCRProvider, TesseractOCRProvider
from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode


class DocumentService:
    """Authoritative coordinator for physical document processing."""

    def __init__(self, ocr_provider: Optional[OCRProvider] = None) -> None:
        self._ocr_provider = ocr_provider or MockOCRProvider(fixtures={})
        self._document_store: Dict[str, DocumentAIResult] = {}

    def set_ocr_provider(self, provider: OCRProvider) -> None:
        """Set or swap the active OCR provider."""
        self._ocr_provider = provider

    def process_document(
        self,
        session_id: str,
        grid: Optional[List[List[int]]] = None,
        image_path: Optional[str] = None,
        raw_text: Optional[str] = None,
        page_no: int = 1,
    ) -> DocumentAIResult:
        """
        Process a physical document page:
        1. Capture quality scoring ("reject before accept" per PRD §11.1).
        2. OCR text extraction.
        3. Structured clinical entity extraction (PRD §11.2).
        4. In-memory session registry persistence.
        """
        quality: Optional[CaptureQualityScore] = None

        # 1. Quality scoring if pixel grid is supplied
        if grid is not None:
            quality = score_capture(grid)
            if not quality.accepted:
                raise AyuSetuGatewayError(
                    ErrorCode.DOC_QUALITY_REJECTED,
                    f"Document capture quality rejected: {', '.join(quality.rejection_reasons)}",
                    422,
                )

        else:
            # Default sharp score when uploading pre-extracted / processed text
            quality = CaptureQualityScore(
                blur_score=0.95,
                glare_score=0.98,
                skew_score=0.95,
                accepted=True,
                rejection_reasons=[],
            )

        # 2. OCR text resolution
        ocr_result: OCRResult
        if raw_text is not None and raw_text.strip():
            ocr_result = OCRResult(
                page_no=page_no,
                raw_text=raw_text.strip(),
                mean_confidence=0.92,
            )
        elif image_path:
            ocr_result = self._ocr_provider.run(image_path=image_path, page_no=page_no)
        else:
            ocr_result = OCRResult(
                page_no=page_no,
                raw_text="",
                mean_confidence=0.0,
            )

        # 3. Structured entity extraction
        entities: List[ExtractedEntity] = []
        if ocr_result.raw_text:
            entities = extract_entities(ocr_result.raw_text, page_no=ocr_result.page_no)

        doc_id = str(uuid6.uuid7())
        result = DocumentAIResult(
            document_id=doc_id,
            quality=quality,
            ocr=[ocr_result] if ocr_result.raw_text else [],
            entities=entities,
        )

        self._document_store[doc_id] = result
        return result

    def get_document(self, document_id: str) -> Optional[DocumentAIResult]:
        """Retrieve stored DocumentAIResult by document ID."""
        return self._document_store.get(document_id)

    def clear(self) -> None:
        """Clear document store (for testing)."""
        self._document_store.clear()


document_service = DocumentService()
