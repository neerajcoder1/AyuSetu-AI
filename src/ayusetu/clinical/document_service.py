"""
Document AI Processing Service
==============================
Authoritative service coordinating capture-time quality scoring (PRD §11.1),
OCR provider execution, and structured clinical entity extraction (PRD §11.2).
"""

from typing import Any, Dict, List, Optional
import uuid6

import os
from ayusetu.ai.clinical.document_ai.capture_quality import score_capture, CaptureQualityScore
from ayusetu.ai.clinical.document_ai.contracts import (
    DocumentAIResult,
    ExtractedEntity,
    OCRResult,
    REVIEW_CONFIDENCE_THRESHOLD,
)
from ayusetu.ai.clinical.document_ai.entity_extractor import extract_entities, detect_prompt_injections
from ayusetu.ai.clinical.document_ai.ocr import MockOCRProvider, OCRProvider, TesseractOCRProvider
from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode


def validate_magic_bytes(data: bytes, filename: Optional[str] = None) -> str:
    """
    Validate file format and magic bytes per PRD §21.11 / SEC-T-09.
    Rejects malformed files, polyglot executables (MZ, ELF), and embedded scripts.
    Returns detected format ('pdf', 'png', 'jpeg', 'webp').
    """
    if not data or len(data) < 4:
        raise AyuSetuGatewayError(
            ErrorCode.DOC_QUALITY_REJECTED,
            "Document rejected: file is empty or too short for valid magic bytes",
            422,
        )

    # 1. Polyglot / Executable inspection (Fail-closed)
    if data.startswith(b"MZ") or data.startswith(b"\x7fELF"):
        raise AyuSetuGatewayError(
            ErrorCode.DOC_QUALITY_REJECTED,
            "Document rejected: executable polyglot payload detected",
            422,
        )

    # Check for script injection in initial header bytes
    initial_header = data[:256].lower()
    if b"<script" in initial_header or b"<?php" in initial_header or b"<%" in initial_header:
        raise AyuSetuGatewayError(
            ErrorCode.DOC_QUALITY_REJECTED,
            "Document rejected: embedded script tags detected in file header",
            422,
        )

    # 2. Magic byte matching
    if data.startswith(b"%PDF-"):
        return "pdf"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    elif data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    elif data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp"

    raise AyuSetuGatewayError(
        ErrorCode.DOC_QUALITY_REJECTED,
        "Document rejected: unsupported or malformed file format (magic bytes mismatch)",
        422,
    )


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
        raw_bytes: Optional[bytes] = None,
        page_no: int = 1,
    ) -> DocumentAIResult:
        """
        Process a physical document page:
        1. Magic byte & polyglot validation (PRD §21.11 / SEC-T-09).
        2. Capture quality scoring ("reject before accept" per PRD §11.1).
        3. OCR text extraction.
        4. Structured clinical entity extraction with prompt-injection isolation (PRD §11.2, §21.10).
        5. In-memory session registry persistence.
        """
        # 0. Validate magic bytes if raw bytes or image path provided
        if raw_bytes is not None:
            try:
                validate_magic_bytes(raw_bytes)
            except AyuSetuGatewayError as err:
                try:
                    from ayusetu.gateway.auth.event_hooks import dispatch_security_event
                    dispatch_security_event(
                        event_type="MALFORMED_DOCUMENT_REJECTED",
                        actor_id="document_validator",
                        actor_role="system",
                        target_resource=f"session_{session_id}",
                        reason=str(err.detail),
                    )
                except Exception:
                    pass
                raise

        if image_path and os.path.exists(image_path):
            try:
                with open(image_path, "rb") as f:
                    header = f.read(512)
                validate_magic_bytes(header, filename=image_path)
            except AyuSetuGatewayError as err:
                try:
                    from ayusetu.gateway.auth.event_hooks import dispatch_security_event
                    dispatch_security_event(
                        event_type="MALFORMED_DOCUMENT_REJECTED",
                        actor_id="document_validator",
                        actor_role="system",
                        target_resource=image_path,
                        reason=str(err.detail),
                    )
                except Exception:
                    pass
                raise

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

        # Automatically integrate extracted entities into session slot candidates
        if session_id:
            try:
                self.integrate_document_entities_into_session(session_id=session_id, document_id=doc_id)
            except Exception as e:
                import logging
                logging.getLogger("ayusetu.document_service").warning("Slot integration warning: %s", e)

        return result

    def integrate_document_entities_into_session(
        self,
        session_id: str,
        document_id: str,
        overwrite_patient: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Integrate extracted document entities into Socrates session slot state per PRD v3 §11.3:
        - Retains provenance link (source='document', source_ref=doc_id).
        - Preserves needs_review flag.
        - NEVER overwrites explicit patient-elicited answers unless explicitly instructed.
        - Never turns unextracted fields into negatives.
        """
        from ayusetu.common.session_cache import SessionCache
        cache = SessionCache()
        session_data = cache.get_session(session_id)
        if not session_data:
            return []

        doc = self.get_document(document_id)
        if not doc or not doc.entities:
            return []

        current_slots = session_data.get("slots", [])
        # Convert slots dict to list format if necessary
        slots_list: List[Dict[str, Any]] = []
        if isinstance(current_slots, dict):
            for k, v in current_slots.items():
                slots_list.append({
                    "path": k,
                    "value": v,
                    "source": "utterance",
                    "reported_by": "patient",
                    "elicited": True,
                })
        elif isinstance(current_slots, list):
            slots_list = list(current_slots)

        existing_paths = {s.get("path") for s in slots_list if isinstance(s, dict)}
        patient_elicited_paths = {
            s.get("path") for s in slots_list
            if isinstance(s, dict) and s.get("source") in ("utterance", "touch") and s.get("reported_by") == "patient"
        }

        integrated_slots: List[Dict[str, Any]] = []

        for entity in doc.entities:
            etype = entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type)

            # Map entity to canonical clinical slot path
            if etype == "medication":
                slot_path = f"medications.{entity.normalised or entity.raw_text}"
            elif etype == "allergy":
                slot_path = f"allergies.{entity.normalised or entity.raw_text}"
            elif etype == "vital":
                slot_path = f"vitals.{entity.normalised or entity.raw_text}"
            elif etype in ("condition", "diagnosis"):
                slot_path = f"past_medical_history.{entity.normalised or entity.raw_text}"
            elif etype == "lab":
                slot_path = f"labs.{entity.normalised or entity.raw_text}"
            else:
                slot_path = f"document.{etype}.{entity.normalised or entity.raw_text}"

            # Check if patient already answered this slot
            if slot_path in patient_elicited_paths and not overwrite_patient:
                # Retain patient's explicit answer as authoritative; do not overwrite
                continue

            slot_entry = {
                "id": str(uuid6.uuid7()),
                "path": slot_path,
                "value": entity.normalised or entity.raw_text,
                "value_coded": entity.code,
                "confidence": entity.confidence,
                "source": "document",
                "source_ref": document_id,
                "reported_by": "patient",
                "elicited": True,
                "needs_review": entity.needs_review,
                "code_system": entity.code_system,
                "page_no": entity.page_no,
            }

            # Update existing slot if present or append new slot
            found_idx = next((i for i, s in enumerate(slots_list) if isinstance(s, dict) and s.get("path") == slot_path), None)
            if found_idx is not None:
                if overwrite_patient or slots_list[found_idx].get("source") == "document":
                    slots_list[found_idx] = slot_entry
            else:
                slots_list.append(slot_entry)

            integrated_slots.append(slot_entry)

        cache.update_session(session_id, {"slots": slots_list})
        return integrated_slots

    def get_document(self, document_id: str) -> Optional[DocumentAIResult]:
        """Retrieve stored DocumentAIResult by document ID."""
        return self._document_store.get(document_id)

    def clear(self) -> None:
        """Clear document store (for testing)."""
        self._document_store.clear()


document_service = DocumentService()
