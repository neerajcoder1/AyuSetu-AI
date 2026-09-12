"""
Structured entity extraction from OCR'd document text (PRD §11.2).

Rule-based (regex) rather than a trained NER model: for a hackathon-stage
system this is auditable, has no training-data dependency, and — critically
for a clinical document — every match is traceable to the exact span it came
from (`raw_text`), which is the same evidence discipline used in
ayusetu.ai.clinical.extraction.rule_extractor.

Every entity below REVIEW_CONFIDENCE_THRESHOLD is marked needs_review=True,
per the "confidence discipline" in PRD §11.2: a drug name or dose is never
silently trusted.
"""

import re
from typing import List, Optional

from ayusetu.ai.clinical.document_ai.contracts import (
    REVIEW_CONFIDENCE_THRESHOLD,
    EntityType,
    ExtractedEntity,
)

# ── Medication ──────────────────────────────────────────────────────────────
# e.g. "Tab. Metformin 500mg 1-0-1 x 5 days", "Cap Amoxicillin 250 mg TDS for 7 days"
_MEDICATION_RE = re.compile(
    r"""(?P<form>Tab\.?|Cap\.?|Syp\.?|Inj\.?)?\s*
        (?P<name>[A-Z][a-zA-Z\-]+)\s*
        (?P<strength>\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml))?\s*
        (?P<freq>\d-\d-\d|OD|BD|TDS|QID|SOS|HS)?\s*
        (?:x|for)?\s*(?P<duration>\d+\s?days?)?
    """,
    re.VERBOSE,
)

# ── Lab result ───────────────────────────────────────────────────────────────
# e.g. "Hemoglobin: 10.2 g/dL (12.0-15.5)", "FBS 110 mg/dL (70-100) H"
_LAB_RESULT_RE = re.compile(
    r"(?P<analyte>[A-Za-z][A-Za-z0-9 ]{1,30}?)[:\s]+"
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>mg/dL|g/dL|%|mmol/L|IU/L|/uL|mIU/L|ng/mL)"
    r"(?:\s*\((?P<ref_low>\d+(?:\.\d+)?)\s*-\s*(?P<ref_high>\d+(?:\.\d+)?)\))?"
    r"(?:\s*(?P<flag>H|L|High|Low))?",
    re.IGNORECASE,
)

# ── Vitals ───────────────────────────────────────────────────────────────────
_VITALS_RES = {
    "blood_pressure": re.compile(r"\bBP[:\s]+(?P<systolic>\d{2,3})\s*/\s*(?P<diastolic>\d{2,3})\s*mmHg\b", re.I),
    "pulse": re.compile(r"\b(?:Pulse|HR)[:\s]+(?P<value>\d{2,3})\s*/?\s*min\b", re.I),
    "temperature": re.compile(r"\bTemp(?:erature)?[:\s]+(?P<value>\d{2,3}(?:\.\d)?)\s*(?P<unit>F|C)\b", re.I),
    "spo2": re.compile(r"\b(?:SpO2|SPO2)[:\s]+(?P<value>\d{2,3})\s*%", re.I),
    "weight": re.compile(r"\bWeight[:\s]+(?P<value>\d{1,3}(?:\.\d)?)\s*kg\b", re.I),
}

# ── Allergy ──────────────────────────────────────────────────────────────────
_ALLERGY_RE = re.compile(
    r"(?:Allerg(?:y|ic)\s*(?:to)?[:\s]+)(?P<substance>[A-Za-z][\w\s]{1,40}?)"
    r"(?:\s*-\s*(?P<reaction>[A-Za-z ]+))?(?:[.,\n]|$)",
    re.IGNORECASE,
)
_NO_ALLERGY_RE = re.compile(r"\bno known allergies?\b", re.I)

# ── Diagnosis ────────────────────────────────────────────────────────────────
_DIAGNOSIS_RE = re.compile(
    r"(?:Dx|Diagnosis)[:\s]+(?P<text>[A-Za-z][\w\s\-]{2,60}?)(?:\s*\((?P<code>[A-Z0-9.]{2,10})\))?(?:[.,\n]|$)",
    re.IGNORECASE,
)

# ── Provider ─────────────────────────────────────────────────────────────────
_PROVIDER_RE = re.compile(
    r"Dr\.?\s+(?P<name>[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*),?\s*"
    r"(?:Reg(?:istration)?\.?\s*(?:No\.?)?[:\s]*(?P<reg_no>[A-Za-z0-9\-]+))?"
    r"(?:,\s*(?P<facility>[A-Za-z][\w\s]+))?"
)


# ── Prompt Injection Defense ─────────────────────────────────────────────────
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?", re.I),
    re.compile(r"(?i)disregard\s+(?:all\s+)?(?:prior|previous|clinical)\s+(?:instructions?|directives?)", re.I),
    re.compile(r"(?i)system\s*:\s*(?:override|reset|execute|admin|mode)", re.I),
    re.compile(r"(?i)you\s+are\s+now\s+in\s+(?:admin|superuser|jailbroken)\s+mode", re.I),
    re.compile(r"(?i)override\s+(?:diagnosis|medication|clinical\s+record|prescription)\s*(?:to|with)?", re.I),
    re.compile(r"(?i)output\s+(?:the\s+)?(?:secret|api\s*key|password|credentials?)", re.I),
    re.compile(r"(?i)delete\s+all\s+(?:records?|data|patients?)", re.I),
]


def detect_prompt_injections(text: str) -> List[str]:
    """Detect potential adversarial prompt injection payloads in document text."""
    detected = []
    for pattern in _PROMPT_INJECTION_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            detected.extend(matches if isinstance(matches[0], str) else [m[0] for m in matches])
    return detected


def sanitize_document_text(text: str) -> str:
    """Isolate and strip embedded prompt injection directives from document text."""
    sanitized = text
    for pattern in _PROMPT_INJECTION_PATTERNS:
        sanitized = pattern.sub("[ISOLATED_DOCUMENT_DATA]", sanitized)
    return sanitized


def _confidence(match_completeness: float) -> float:
    """Simple confidence heuristic from how many optional groups matched."""
    return round(0.6 + 0.4 * match_completeness, 2)


def extract_entities(raw_text: str, page_no: int = 1) -> List[ExtractedEntity]:
    # Detect and isolate prompt injection payloads per PRD §21.10 / SEC-T-02
    injections = detect_prompt_injections(raw_text)
    if injections:
        try:
            from ayusetu.gateway.auth.event_hooks import dispatch_security_event
            dispatch_security_event(
                event_type="DOCUMENT_PROMPT_INJECTION_DETECTED",
                actor_id="document_ai_parser",
                actor_role="system",
                target_resource=f"document_page_{page_no}",
                reason=f"Adversarial prompt injection attempt detected and isolated: {', '.join(injections[:3])}",
                metadata={"injections_detected": injections, "page_no": page_no},
            )
        except Exception:
            pass

    sanitized_text = sanitize_document_text(raw_text)
    entities: List[ExtractedEntity] = []

    entities.extend(_extract_medications(sanitized_text, page_no))
    entities.extend(_extract_lab_results(sanitized_text, page_no))
    entities.extend(_extract_vitals(sanitized_text, page_no))
    entities.extend(_extract_allergies(sanitized_text, page_no))
    entities.extend(_extract_diagnoses(sanitized_text, page_no))
    entities.extend(_extract_providers(sanitized_text, page_no))

    for e in entities:
        if e.confidence < REVIEW_CONFIDENCE_THRESHOLD:
            e.needs_review = True

    return entities


def _extract_medications(text: str, page_no: int) -> List[ExtractedEntity]:
    out = []
    for m in _MEDICATION_RE.finditer(text):
        name = m.group("name")
        strength = m.group("strength")
        if not name or not strength:
            # Require at least a name + dose strength to call this a medication —
            # bare capitalised words are far too noisy otherwise.
            continue
        groups_present = sum(1 for g in ("form", "strength", "freq", "duration") if m.group(g))
        out.append(
            ExtractedEntity(
                entity_type=EntityType.MEDICATION,
                raw_text=m.group(0).strip(),
                normalised={
                    "name": name,
                    "strength": strength.strip() if strength else None,
                    "frequency": m.group("freq"),
                    "duration": m.group("duration"),
                    "form": m.group("form"),
                },
                confidence=_confidence(groups_present / 4),
                page_no=page_no,
            )
        )
    return out


def _extract_lab_results(text: str, page_no: int) -> List[ExtractedEntity]:
    out = []
    for m in _LAB_RESULT_RE.finditer(text):
        has_range = bool(m.group("ref_low") and m.group("ref_high"))
        has_flag = bool(m.group("flag"))
        out.append(
            ExtractedEntity(
                entity_type=EntityType.LAB_RESULT,
                raw_text=m.group(0).strip(),
                normalised={
                    "analyte": m.group("analyte").strip(),
                    "value": float(m.group("value")),
                    "unit": m.group("unit"),
                    "reference_low": float(m.group("ref_low")) if m.group("ref_low") else None,
                    "reference_high": float(m.group("ref_high")) if m.group("ref_high") else None,
                    "abnormal_flag": m.group("flag"),
                },
                confidence=_confidence((has_range + has_flag) / 2),
                page_no=page_no,
            )
        )
    return out


def _extract_vitals(text: str, page_no: int) -> List[ExtractedEntity]:
    out = []
    for name, pattern in _VITALS_RES.items():
        m = pattern.search(text)
        if not m:
            continue
        normalised = {"vital": name, **{k: v for k, v in m.groupdict().items() if v is not None}}
        out.append(
            ExtractedEntity(
                entity_type=EntityType.VITAL_SIGN,
                raw_text=m.group(0).strip(),
                normalised=normalised,
                confidence=0.9,
                page_no=page_no,
            )
        )
    return out


def _extract_allergies(text: str, page_no: int) -> List[ExtractedEntity]:
    out = []
    if _NO_ALLERGY_RE.search(text):
        out.append(
            ExtractedEntity(
                entity_type=EntityType.ALLERGY,
                raw_text=_NO_ALLERGY_RE.search(text).group(0),
                normalised={"substance": None, "reaction": None, "status": "none_reported"},
                confidence=0.9,
                page_no=page_no,
            )
        )
        return out

    for m in _ALLERGY_RE.finditer(text):
        substance = m.group("substance").strip()
        reaction = m.group("reaction")
        out.append(
            ExtractedEntity(
                entity_type=EntityType.ALLERGY,
                raw_text=m.group(0).strip(),
                normalised={
                    "substance": substance,
                    "reaction": reaction.strip() if reaction else None,
                    "status": "active",
                },
                confidence=_confidence(1.0 if reaction else 0.5),
                page_no=page_no,
            )
        )
    return out


def _extract_diagnoses(text: str, page_no: int) -> List[ExtractedEntity]:
    out = []
    for m in _DIAGNOSIS_RE.finditer(text):
        code = m.group("code")
        out.append(
            ExtractedEntity(
                entity_type=EntityType.DIAGNOSIS,
                raw_text=m.group(0).strip(),
                normalised={"text": m.group("text").strip(), "code": code},
                code_system="ICD-11" if code else None,
                code=code,
                confidence=_confidence(1.0 if code else 0.4),
                page_no=page_no,
            )
        )
    return out


def _extract_providers(text: str, page_no: int) -> List[ExtractedEntity]:
    out = []
    m = _PROVIDER_RE.search(text)
    if m:
        groups_present = sum(1 for g in ("reg_no", "facility") if m.group(g))
        out.append(
            ExtractedEntity(
                entity_type=EntityType.PROVIDER,
                raw_text=m.group(0).strip(),
                normalised={
                    "name": m.group("name").strip(),
                    "registration_number": m.group("reg_no"),
                    "facility": m.group("facility").strip() if m.group("facility") else None,
                },
                confidence=_confidence(groups_present / 2),
                page_no=page_no,
            )
        )
    return out
