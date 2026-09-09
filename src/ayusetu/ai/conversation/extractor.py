"""
AyuSetu AI — Clinical Extractor
=================================
Provides:
  * ``ClinicalExtractor``               – structural Protocol (interface)
  * ``DeterministicRuleExtractor``      – production rule-based extractor
  * ``DeterministicPlaceholderExtractor`` – backward-compatible alias
    (preserved so that existing tests and imports continue to work)

Design constraints
------------------
* NO LLM calls.  All extraction is deterministic (regex / keyword).
* The extractor returns structured ``ExtractionResult`` objects.
* The extractor does NOT decide what question to ask next.
  That responsibility belongs exclusively to the ``DialoguePlanner``.
* Supports Hindi (Devanagari), English (Latin), and Hinglish (mixed-script).
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Protocol

from contracts.dialogue import ClinicalSlot
from contracts.extraction import ExtractedSlot, ExtractionResult
from ayusetu.ai.clinical.utils import (
    parse_duration,
    parse_location,
    parse_onset,
    parse_severity,
)


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------

class ClinicalExtractor(Protocol):
    """
    Interface for extracting structured clinical information from patient speech.

    Implementors must provide a single method ``extract(text) -> ExtractionResult``.
    The extractor must NEVER decide which question to ask next.
    """

    def extract(self, text: str) -> ExtractionResult:
        ...


# ---------------------------------------------------------------------------
# Helper: chief-complaint keyword matching
# ---------------------------------------------------------------------------

# Each entry: (regex pattern, canonical value, confidence)
_CHIEF_COMPLAINT_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    # Stomach pain / abdominal pain
    (re.compile(r"\b(stomach\s*pain|abdominal\s*pain|pet\s*(?:mein\s*)?dard|पेट\s*(?:में\s*)?दर्द)\b",
                re.I | re.U),
     "stomach pain", 0.92),
    # Headache
    (re.compile(r"\b(headache|head\s*ache|sir\s*dard|सिर\s*दर्द|sar\s*dard|migraine)\b",
                re.I | re.U),
     "headache", 0.92),
    # Chest pain
    (re.compile(r"\b(chest\s*pain|seene\s*mein\s*dard|सीने\s*(?:में\s*)?दर्द|chhati\s*mein\s*dard)\b",
                re.I | re.U),
     "chest pain", 0.93),
    # Fever
    (re.compile(r"\b(fever|bukhaar|बुखार)\b", re.I | re.U),
     "fever", 0.90),
    # Cough
    (re.compile(r"\b(cough|khansi|खांसी|khasi)\b", re.I | re.U),
     "cough", 0.90),
    # Vomiting / nausea
    (re.compile(r"\b(vomiting|vomit|ulti|उल्टी|nausea|ji\s*michlan|जी\s*मिचलाना)\b",
                re.I | re.U),
     "vomiting/nausea", 0.90),
    # Diarrhoea
    (re.compile(r"\b(diarrhea|diarrhoea|loose\s*motion|dast|दस्त)\b",
                re.I | re.U),
     "diarrhoea", 0.90),
    # Breathlessness
    (re.compile(r"\b(breathless|saans\s*(?:lene\s*mein\s*)?takleef|सांस\s*(?:लेने\s*में\s*)?तकलीफ|shortness\s*of\s*breath)\b",
                re.I | re.U),
     "breathlessness", 0.92),
    # Back pain
    (re.compile(r"\b(back\s*pain|kamar\s*dard|कमर\s*दर्द|peeth\s*mein\s*dard|पीठ\s*(?:में\s*)?दर्द)\b",
                re.I | re.U),
     "back pain", 0.90),
    # Dizziness
    (re.compile(r"\b(dizziness|dizzy|chakkar|चक्कर|giddiness)\b",
                re.I | re.U),
     "dizziness", 0.88),
    # Weakness / fatigue
    (re.compile(r"\b(weakness|fatigue|kamzori|कमज़ोरी|thakaan|थकान|tired)\b",
                re.I | re.U),
     "weakness/fatigue", 0.85),
    # Joint pain
    (re.compile(r"\b(joint\s*pain|jod\s*(?:mein\s*)?dard|जोड़\s*(?:में\s*)?दर्द)\b",
                re.I | re.U),
     "joint pain", 0.88),
    # Sore throat
    (re.compile(r"\b(sore\s*throat|gale\s*mein\s*dard|गले\s*(?:में\s*)?दर्द|throat\s*pain)\b",
                re.I | re.U),
     "sore throat", 0.88),
]


def _extract_chief_complaint(text: str) -> Optional[ExtractedSlot]:
    for pattern, value, confidence in _CHIEF_COMPLAINT_PATTERNS:
        m = pattern.search(text)
        if m:
            return ExtractedSlot(
                slot=ClinicalSlot.CHIEF_COMPLAINT,
                value=value,
                confidence=confidence,
                evidence=m.group(0),
            )
    return None


# ---------------------------------------------------------------------------
# Helper: associated symptoms
# ---------------------------------------------------------------------------

_ASSOCIATED_SYMPTOM_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    (re.compile(r"\b(fever|bukhaar|बुखार)\b", re.I | re.U), "fever", 0.88),
    (re.compile(r"\b(cough|khansi|खांसी)\b", re.I | re.U), "cough", 0.88),
    (re.compile(r"\b(vomiting|vomit|ulti|उल्टी)\b", re.I | re.U), "vomiting", 0.88),
    (re.compile(r"\b(diarrhea|loose\s*motion|dast|दस्त)\b", re.I | re.U), "diarrhoea", 0.88),
    (re.compile(r"\b(nausea|ji\s*michlan|जी\s*मिचलाना)\b", re.I | re.U), "nausea", 0.85),
    (re.compile(r"\b(sweating|paseena|पसीना)\b", re.I | re.U), "sweating", 0.82),
    (re.compile(r"\b(chills|kaampna|कांपना|ठंड\s*लगना)\b", re.I | re.U), "chills", 0.82),
    (re.compile(r"\b(headache|sir\s*dard|सिर\s*दर्द)\b", re.I | re.U), "headache", 0.88),
    (re.compile(r"\b(dizziness|chakkar|चक्कर)\b", re.I | re.U), "dizziness", 0.85),
    (re.compile(r"\b(weakness|kamzori|कमज़ोरी|thakaan|थकान)\b", re.I | re.U), "weakness", 0.82),
    (re.compile(r"\b(loss\s*of\s*appetite|bhookh\s*nahi|भूख\s*नहीं|khaana\s*nahi\s*khaya)\b",
                re.I | re.U), "loss of appetite", 0.85),
]


def _extract_associated_symptoms(
    text: str,
    chief_complaint_value: Optional[str],
) -> Optional[ExtractedSlot]:
    """
    Extract associated symptoms, skipping the chief complaint to avoid duplication.
    If multiple symptoms are found, they are concatenated into one slot value.
    """
    found: List[str] = []
    for pattern, symptom, _ in _ASSOCIATED_SYMPTOM_PATTERNS:
        if chief_complaint_value and symptom == chief_complaint_value:
            continue
        if pattern.search(text):
            found.append(symptom)

    if not found:
        return None

    # De-duplicate while preserving order
    seen: set = set()
    deduped: List[str] = []
    for s in found:
        if s not in seen:
            deduped.append(s)
            seen.add(s)

    return ExtractedSlot(
        slot=ClinicalSlot.ASSOCIATED_SYMPTOMS,
        value=", ".join(deduped),
        confidence=0.85,
        evidence=", ".join(deduped),
    )


# ---------------------------------------------------------------------------
# Helper: aggravating / relieving factors
# ---------------------------------------------------------------------------

def _extract_aggravating_relieving(text: str) -> Optional[ExtractedSlot]:
    patterns = [
        (re.compile(r"\b(worse\s*(?:when|after|with)?|badhta\s*hai|बढ़ता\s*है|zyada\s*hota\s*hai)\b",
                    re.I | re.U), "worsens", 0.78),
        (re.compile(r"\b(better\s*(?:when|after|with)?|kam\s*hota\s*hai|कम\s*होता\s*है|relief)\b",
                    re.I | re.U), "relieves", 0.78),
        (re.compile(r"\b(eating|khane\s*ke\s*baad|खाने\s*के\s*बाद)\b",
                    re.I | re.U), "after eating", 0.75),
        (re.compile(r"\b(lying\s*down|letne\s*par|लेटने\s*पर|rest\s*(?:mein|se)?)\b",
                    re.I | re.U), "on lying down", 0.75),
        (re.compile(r"\b(exertion|exercise|mehnat|मेहनत)\b",
                    re.I | re.U), "on exertion", 0.75),
    ]
    found: List[str] = []
    for pattern, label, _ in patterns:
        if pattern.search(text):
            found.append(label)
    if not found:
        return None
    return ExtractedSlot(
        slot=ClinicalSlot.AGGRAVATING_RELIEVING,
        value=", ".join(found),
        confidence=0.75,
        evidence=", ".join(found),
    )


# ---------------------------------------------------------------------------
# Helper: past medical history
# ---------------------------------------------------------------------------

def _extract_past_medical_history(text: str) -> Optional[ExtractedSlot]:
    patterns = [
        (re.compile(r"\b(diabetes|sugar\s*ki\s*bimari|madhumeh|मधुमेह|शुगर)\b",
                    re.I | re.U), "diabetes", 0.90),
        (re.compile(r"\b(hypertension|high\s*blood\s*pressure|BP\s*high|uccha\s*BP)\b",
                    re.I | re.U), "hypertension", 0.90),
        (re.compile(r"\b(asthma|damaa|दमा|saans\s*ki\s*bimari)\b",
                    re.I | re.U), "asthma", 0.90),
        (re.compile(r"\b(heart\s*disease|heart\s*attack|dil\s*ki\s*bimari|हृदय\s*रोग)\b",
                    re.I | re.U), "heart disease", 0.90),
        (re.compile(r"\b(thyroid)\b", re.I | re.U), "thyroid disorder", 0.88),
        (re.compile(r"\b(epilepsy|seizure|mircchi|मिर्गी)\b",
                    re.I | re.U), "epilepsy", 0.90),
        (re.compile(r"\b(TB|tuberculosis|kshay|क्षय\s*रोग)\b",
                    re.I | re.U), "tuberculosis", 0.90),
        (re.compile(r"\b(jaundice|peelia|पीलिया|hepatitis)\b",
                    re.I | re.U), "jaundice/hepatitis", 0.88),
        (re.compile(r"\b(no\s*(?:past\s*)?(?:medical\s*)?history|koi\s*bimari\s*nahi|कोई\s*बीमारी\s*नहीं)\b",
                    re.I | re.U), "none", 0.80),
    ]
    found: List[str] = []
    for pattern, label, _ in patterns:
        if pattern.search(text):
            found.append(label)
    if not found:
        return None
    return ExtractedSlot(
        slot=ClinicalSlot.PAST_MEDICAL_HISTORY,
        value=", ".join(found),
        confidence=0.88,
        evidence=", ".join(found),
    )


# ---------------------------------------------------------------------------
# Helper: medications
# ---------------------------------------------------------------------------

def _extract_medications(text: str) -> Optional[ExtractedSlot]:
    patterns = [
        re.compile(r"\b(paracetamol|crocin|tylenol|aspirin|ibuprofen|brufen|antacid|pantoprazole|"
                   r"metformin|insulin|lisinopril|atorvastatin|metoprolol|amoxicillin|azithromycin|"
                   r"cetirizine|omeprazole|dolo)\b", re.I | re.U),
        re.compile(r"\b(tablet|capsule|syrup|injection|goli|दवाई|dawai|medicine|davai)\b",
                   re.I | re.U),
        re.compile(r"\b(no\s*medications?|koi\s*dawai\s*nahi|कोई\s*दवाई\s*नहीं)\b",
                   re.I | re.U),
    ]
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            return ExtractedSlot(
                slot=ClinicalSlot.MEDICATIONS,
                value=m.group(0).lower(),
                confidence=0.80,
                evidence=m.group(0),
            )
    return None


# ---------------------------------------------------------------------------
# Helper: allergies
# ---------------------------------------------------------------------------

def _extract_allergies(text: str) -> Optional[ExtractedSlot]:
    allergy_pos = re.compile(
        r"\b(allerg(?:y|ic)|penicillin|sulfa|latex|nuts?|shellfish|kisi\s*se\s*allergy|"
        r"कोई\s*एलर्जी|allergy\s*hai)\b",
        re.I | re.U,
    )
    allergy_neg = re.compile(
        r"\b(no\s*allerg(?:y|ies)|koi\s*allergy\s*nahi|कोई\s*एलर्जी\s*नहीं)\b",
        re.I | re.U,
    )
    m_neg = allergy_neg.search(text)
    if m_neg:
        return ExtractedSlot(
            slot=ClinicalSlot.ALLERGIES,
            value="none",
            confidence=0.85,
            evidence=m_neg.group(0),
        )
    m_pos = allergy_pos.search(text)
    if m_pos:
        return ExtractedSlot(
            slot=ClinicalSlot.ALLERGIES,
            value=m_pos.group(0).lower(),
            confidence=0.82,
            evidence=m_pos.group(0),
        )
    return None


# ---------------------------------------------------------------------------
# Helper: lifestyle
# ---------------------------------------------------------------------------

def _extract_lifestyle(text: str) -> Optional[ExtractedSlot]:
    patterns = [
        (re.compile(r"\b(smok(?:ing|er|es?)|cigarette|bidi|beedi|tambaku|तंबाकू)\b",
                    re.I | re.U), "smoking", 0.90),
        (re.compile(r"\b(alcohol|sharab|शराब|drink(?:ing|er)?)\b",
                    re.I | re.U), "alcohol use", 0.90),
        (re.compile(r"\b(vegetarian|veg\b|shakahari|शाकाहारी)\b",
                    re.I | re.U), "vegetarian diet", 0.82),
        (re.compile(r"\b(non[-\s]?veg|meat|chicken|gosht|मांसाहारी)\b",
                    re.I | re.U), "non-vegetarian diet", 0.82),
        (re.compile(r"\b(exercise|workout|gym|yoga|vyayam|व्यायाम)\b",
                    re.I | re.U), "exercises", 0.80),
        (re.compile(r"\b(sedentary|no\s*exercise|nahi\s*karta|नहीं\s*करता)\b",
                    re.I | re.U), "sedentary", 0.75),
        (re.compile(r"\b(sleep\s*(?:problem|disorder)|insomnia|neend\s*nahi|नींद\s*नहीं)\b",
                    re.I | re.U), "sleep problems", 0.82),
    ]
    found: List[str] = []
    for pattern, label, _ in patterns:
        if pattern.search(text):
            found.append(label)
    if not found:
        return None
    return ExtractedSlot(
        slot=ClinicalSlot.LIFESTYLE,
        value=", ".join(found),
        confidence=0.82,
        evidence=", ".join(found),
    )


# ---------------------------------------------------------------------------
# Helper: family history
# ---------------------------------------------------------------------------

def _extract_family_history(text: str) -> Optional[ExtractedSlot]:
    patterns = [
        re.compile(r"\b(family\s*history|parivaar\s*mein|परिवार\s*में|father|mother|"
                   r"baap|maa|pita|mata|uncle|aunt|sibling|bhai|behen)\b",
                   re.I | re.U),
        re.compile(r"\b(no\s*family\s*history|parivaar\s*mein\s*koi\s*bimari\s*nahi|"
                   r"परिवार\s*में\s*कोई\s*बीमारी\s*नहीं)\b",
                   re.I | re.U),
    ]
    # Only fire if accompanied by a disease keyword
    disease_found = re.search(
        r"\b(diabetes|hypertension|cancer|heart|TB|asthma|madhumeh|मधुमेह)\b",
        text, re.I | re.U,
    )
    for pattern in patterns:
        if pattern.search(text) and disease_found:
            matched = pattern.search(text).group(0)
            return ExtractedSlot(
                slot=ClinicalSlot.FAMILY_HISTORY,
                value=text.strip()[:80],  # keep first 80 chars as value
                confidence=0.75,
                evidence=matched,
            )
    return None


# ---------------------------------------------------------------------------
# Production rule-based extractor
# ---------------------------------------------------------------------------

class DeterministicRuleExtractor:
    """
    Deterministic rule-based clinical extractor.

    Supports Hindi (Devanagari), English (Latin), and Hinglish (mixed-script).
    Uses regular expressions and keyword matching only — no LLM calls.

    The extractor returns structured ``ExtractionResult`` objects containing
    zero or more ``ExtractedSlot`` items.  It does NOT decide which question
    to ask next; that is the planner's responsibility.

    Extraction order
    ----------------
    Chief complaint is extracted first so that associated-symptoms detection
    can skip the chief complaint and avoid double-counting.
    """

    def extract(self, text: str) -> ExtractionResult:
        """
        Extract clinical slots from *text*.

        Parameters
        ----------
        text: str
            Transcribed patient utterance (Hindi, English, or Hinglish).

        Returns
        -------
        ExtractionResult
            Contains zero or more ``ExtractedSlot`` objects.
            Confidence values reflect extraction certainty, NOT ASR quality.
        """
        slots: list[ExtractedSlot] = []
        chief_value: Optional[str] = None

        # 1. Chief complaint
        cc = _extract_chief_complaint(text)
        if cc:
            slots.append(cc)
            chief_value = cc.value

        # 2. Duration (via utils)
        dur = parse_duration(text)
        if dur:
            slots.append(ExtractedSlot(
                slot=ClinicalSlot.DURATION,
                value=dur[0],
                confidence=dur[1],
                evidence=f"duration pattern: {dur[0]}",
            ))

        # 3. Onset (via utils)
        onset = parse_onset(text)
        if onset:
            slots.append(ExtractedSlot(
                slot=ClinicalSlot.ONSET,
                value=onset[0],
                confidence=onset[1],
                evidence=f"onset pattern: {onset[0]}",
            ))

        # 4. Location (via utils)
        loc = parse_location(text)
        if loc:
            slots.append(ExtractedSlot(
                slot=ClinicalSlot.LOCATION,
                value=loc[0],
                confidence=loc[1],
                evidence=f"location pattern: {loc[0]}",
            ))

        # 5. Severity (via utils)
        sev = parse_severity(text)
        if sev:
            slots.append(ExtractedSlot(
                slot=ClinicalSlot.SEVERITY,
                value=sev[0],
                confidence=sev[1],
                evidence=f"severity pattern: {sev[0]}",
            ))

        # 6. Associated symptoms (avoid duplicating chief complaint)
        assoc = _extract_associated_symptoms(text, chief_value)
        if assoc:
            slots.append(assoc)

        # 7. Aggravating / relieving factors
        agg = _extract_aggravating_relieving(text)
        if agg:
            slots.append(agg)

        # 8. Past medical history
        pmh = _extract_past_medical_history(text)
        if pmh:
            slots.append(pmh)

        # 9. Medications
        meds = _extract_medications(text)
        if meds:
            slots.append(meds)

        # 10. Allergies
        alg = _extract_allergies(text)
        if alg:
            slots.append(alg)

        # 11. Family history
        fh = _extract_family_history(text)
        if fh:
            slots.append(fh)

        # 12. Lifestyle
        ls = _extract_lifestyle(text)
        if ls:
            slots.append(ls)

        return ExtractionResult(extractions=slots)


# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------

class DeterministicPlaceholderExtractor(DeterministicRuleExtractor):
    """
    Backward-compatible alias retained so that all existing tests and imports
    that reference ``DeterministicPlaceholderExtractor`` continue to work.

    This class is now backed by the full ``DeterministicRuleExtractor`` logic
    and will produce richer extractions than the original keyword stub.
    The existing test suite uses controlled utterances that remain valid.
    """
