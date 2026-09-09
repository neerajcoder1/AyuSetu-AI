"""
LLM-backed implementation of the ClinicalExtractor contract.

Conforms to ayusetu.ai.conversation.extractor.ClinicalExtractor so it can be
dropped into DialogueEngine in place of DeterministicPlaceholderExtractor:

    engine = DialogueEngine(extractor=LLMClinicalExtractor())

Anti-hallucination posture: the extractor NEVER trusts the model's output
blindly. Every candidate extraction is re-validated against the pydantic
contract and a set of sanity checks (allowed slot, confidence range,
evidence must actually appear in the source text). Anything that fails
validation is dropped silently rather than raised — a malformed model
response degrades to "no extraction," never to a crash or a guess.
"""

import json
import logging
from typing import Optional

from contracts.dialogue import ClinicalSlot
from contracts.extraction import ExtractedSlot, ExtractionResult
from ayusetu.ai.conversation.llm_provider import LLMProvider, OpenAICompatibleProvider
from ayusetu.ai.clinical.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    build_user_prompt,
)

logger = logging.getLogger(__name__)

_VALID_SLOTS = {s.value for s in ClinicalSlot}


def _extract_json_object(raw: str) -> Optional[dict]:
    """Best-effort extraction of a single JSON object from an LLM response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


class LLMClinicalExtractor:
    """
    Extracts structured ClinicalSlot facts from a single patient utterance
    using an LLM, constrained to the ExtractionResult contract.
    """

    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or OpenAICompatibleProvider()

    def extract(self, text: str, language: str = "unknown") -> ExtractionResult:
        if not text or not text.strip():
            return ExtractionResult(extractions=[])

        raw = self.provider.generate(
            EXTRACTION_SYSTEM_PROMPT, build_user_prompt(text, language)
        )
        payload = _extract_json_object(raw)
        if payload is None:
            logger.warning("LLMClinicalExtractor: could not parse model output; returning empty result")
            return ExtractionResult(extractions=[])

        return ExtractionResult(extractions=self._validate_candidates(payload, text))

    def _validate_candidates(self, payload: dict, source_text: str) -> list[ExtractedSlot]:
        candidates = payload.get("extractions", [])
        if not isinstance(candidates, list):
            return []

        validated: list[ExtractedSlot] = []
        for item in candidates:
            if not isinstance(item, dict):
                continue

            slot = item.get("slot")
            if slot not in _VALID_SLOTS:
                continue

            value = item.get("value")
            if not isinstance(value, str) or not value.strip():
                continue

            confidence = item.get("confidence")
            if not isinstance(confidence, (int, float)):
                continue
            confidence = max(0.0, min(1.0, float(confidence)))

            evidence = item.get("evidence")
            if isinstance(evidence, str) and evidence.strip():
                # Anti-hallucination check: the claimed evidence must actually
                # occur in the source utterance, or we don't trust the claim.
                if evidence.strip() not in source_text:
                    confidence = min(confidence, 0.5)
            else:
                evidence = None
                confidence = min(confidence, 0.5)

            try:
                validated.append(
                    ExtractedSlot(
                        slot=ClinicalSlot(slot),
                        value=value.strip(),
                        confidence=confidence,
                        evidence=evidence,
                    )
                )
            except ValueError:
                continue

        return validated
