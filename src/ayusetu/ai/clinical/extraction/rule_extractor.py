"""
Deterministic, LLM-free clinical extractor.

Used as:
  - an offline fallback when no LLM provider is configured/reachable,
  - a fast pre-filter that never needs a network call,
  - a source of deterministic ground truth for tests.

Coverage is intentionally broader than
ayusetu.ai.conversation.extractor.DeterministicPlaceholderExtractor, which is
a narrow test fixture for the dialogue state machine. This one is meant to be
usable on real (if simple) English/Hindi/Hinglish utterances.

Every match records the matched span as `evidence`, so extractions are
always traceable back to the source text (hover-to-source, PRD §14.1).
"""

import re
from dataclasses import dataclass
from typing import Callable, List, Pattern

from contracts.dialogue import ClinicalSlot
from contracts.extraction import ExtractedSlot, ExtractionResult


@dataclass(frozen=True)
class _Rule:
    slot: ClinicalSlot
    pattern: Pattern
    confidence: float
    value_fn: Callable[[re.Match], str]


def _lit(value: str) -> Callable[[re.Match], str]:
    return lambda m: value


def _matched_text(m: re.Match) -> str:
    return m.group(0)


_RULES: List[_Rule] = [
    # Duration: "2 days", "3 weeks", "दो दिन से", "5 din se"
    _Rule(
        ClinicalSlot.DURATION,
        re.compile(r"\b\d+\s*(day|days|week|weeks|month|months|hour|hours|din)\b", re.I),
        0.88,
        _matched_text,
    ),
    _Rule(
        ClinicalSlot.DURATION,
        re.compile(r"(दो|तीन|चार|पांच|एक)\s*दिन\s*से"),
        0.85,
        _matched_text,
    ),
    # Severity: "8 out of 10", "severe pain", "mild"
    _Rule(
        ClinicalSlot.SEVERITY,
        re.compile(r"\b\d{1,2}\s*(?:/|out of)\s*10\b", re.I),
        0.9,
        _matched_text,
    ),
    _Rule(
        ClinicalSlot.SEVERITY,
        re.compile(r"\b(mild|moderate|severe|unbearable|excruciating)\b", re.I),
        0.75,
        _matched_text,
    ),
    # Fever / common associated symptoms
    _Rule(
        ClinicalSlot.ASSOCIATED_SYMPTOMS,
        re.compile(r"\b(fever|बुखार|vomiting|उल्टी|nausea|cough|खांसी|diarrhea|dizziness)\b", re.I),
        0.82,
        _matched_text,
    ),
    # Allergies
    _Rule(
        ClinicalSlot.ALLERGIES,
        re.compile(r"\b(allerg(?:y|ic|ies) to [\w\s]+|no known allergies|no allergies)\b", re.I),
        0.85,
        _matched_text,
    ),
    # Medications
    _Rule(
        ClinicalSlot.MEDICATIONS,
        re.compile(
            r"\b(taking|on|prescribed)\s+([a-zA-Z][\w\-]*(?:\s\d+\s?mg)?)\b",
            re.I,
        ),
        0.7,
        lambda m: m.group(2).strip(),
    ),
    # Smoking / lifestyle
    _Rule(
        ClinicalSlot.LIFESTYLE,
        re.compile(r"\b(smok(?:e|es|ing)|drink(?:s|ing)? alcohol|tobacco)\b", re.I),
        0.8,
        _matched_text,
    ),
    # Family history
    _Rule(
        ClinicalSlot.FAMILY_HISTORY,
        re.compile(r"\b(father|mother|family)\b.{0,40}\b(diabet\w*|hypertens\w*|cancer|heart)\b", re.I),
        0.75,
        _matched_text,
    ),
    # Past medical history
    _Rule(
        ClinicalSlot.PAST_MEDICAL_HISTORY,
        re.compile(r"\b(diagnosed with|history of|had)\s+([\w\s]+?)(?:\.|,|$)", re.I),
        0.65,
        _matched_text,
    ),
    # Location
    _Rule(
        ClinicalSlot.LOCATION,
        re.compile(r"\bin (my|the) (chest|stomach|abdomen|head|back|arm|leg|throat|jaw)\b", re.I),
        0.75,
        _matched_text,
    ),
]

# Chief complaint is left to a broader keyword set since it's the anchor slot.
_CHIEF_COMPLAINT_KEYWORDS = re.compile(
    r"\b(pain|ache|headache|पेट में दर्द|दर्द|hurts?|breathless|chest pain)\b", re.I
)


class RuleBasedClinicalExtractor:
    """LLM-free extractor. Conforms to the ClinicalExtractor protocol."""

    def extract(self, text: str) -> ExtractionResult:
        if not text or not text.strip():
            return ExtractionResult(extractions=[])

        extractions: List[ExtractedSlot] = []

        cc_match = _CHIEF_COMPLAINT_KEYWORDS.search(text)
        if cc_match:
            extractions.append(
                ExtractedSlot(
                    slot=ClinicalSlot.CHIEF_COMPLAINT,
                    value=cc_match.group(0),
                    confidence=0.7,
                    evidence=cc_match.group(0),
                )
            )

        for rule in _RULES:
            match = rule.pattern.search(text)
            if match:
                extractions.append(
                    ExtractedSlot(
                        slot=rule.slot,
                        value=rule.value_fn(match),
                        confidence=rule.confidence,
                        evidence=match.group(0),
                    )
                )

        return ExtractionResult(extractions=extractions)
