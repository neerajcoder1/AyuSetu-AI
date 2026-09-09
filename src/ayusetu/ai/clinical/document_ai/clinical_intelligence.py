"""
Clinical intelligence over extracted document entities (PRD §11.3).

All curated tables here (reference ranges, drug-drug and herb-drug
interactions, drug-class groupings) are small STARTER datasets for
demonstrating the mechanism end-to-end. The PRD is explicit that these must
be "a curated, severity-graded interaction database" / "a curated,
referenced table maintained by the clinical advisory board" — i.e. real
deployment data owned by the Clinical Advisory Board, not hardcoded Python.
Swap `_REFERENCE_RANGES` / `_DRUG_INTERACTIONS` / `_HERB_DRUG_INTERACTIONS` /
`_DRUG_CLASSES` for a CAB-maintained data source without touching the logic
that consumes them.
"""

from dataclasses import dataclass
from datetime import date as Date
from typing import Dict, List, Optional, Tuple

from ayusetu.ai.clinical.document_ai.contracts import EntityType, ExtractedEntity

# analyte (lowercased) -> (low, high) adult reference range.
# PRD calls for age/sex adjustment; this starter table is adult-unisex only
# and callers should treat it as a coarse pass, flagging for physician review
# rather than a definitive read — same posture as entity confidence scoring.
_REFERENCE_RANGES: Dict[str, Tuple[float, float]] = {
    "hemoglobin": (12.0, 16.5),
    "hba1c": (4.0, 5.6),
    "fbs": (70.0, 100.0),
    "creatinine": (0.6, 1.3),
    "tsh": (0.4, 4.0),
}

# (drug_a, drug_b) lowercased, unordered -> (severity, description)
_DRUG_INTERACTIONS: Dict[frozenset, Tuple[str, str]] = {
    frozenset({"warfarin", "aspirin"}): ("severe", "Increased bleeding risk"),
    frozenset({"metformin", "contrast"}): ("moderate", "Risk of lactic acidosis with IV contrast"),
    frozenset({"ace inhibitor", "potassium"}): ("moderate", "Risk of hyperkalaemia"),
}

# PRD §11.3 — AYUSH-specific herb-drug pairs, "unbuilt elsewhere at point of intake".
_HERB_DRUG_INTERACTIONS: Dict[frozenset, Tuple[str, str]] = {
    frozenset({"guggulu", "thyroid medication"}): ("moderate", "Guggulu may alter thyroid hormone levels"),
    frozenset({"ashwagandha", "sedative"}): ("moderate", "Additive CNS depression risk"),
    frozenset({"brahmi", "anticonvulsant"}): ("moderate", "May alter seizure threshold / drug levels"),
    frozenset({"turmeric", "anticoagulant"}): (
        "severe",
        "High-dose turmeric potentiates anticoagulant effect, increasing bleeding risk",
    ),
}

# drug name (lowercased) -> drug class, for duplicate-therapy detection.
_DRUG_CLASSES: Dict[str, str] = {
    "metformin": "biguanide",
    "glimepiride": "sulfonylurea",
    "amlodipine": "calcium_channel_blocker",
    "cilnidipine": "calcium_channel_blocker",
    "atorvastatin": "statin",
    "rosuvastatin": "statin",
}


@dataclass
class AbnormalFlag:
    analyte: str
    value: float
    reference_low: float
    reference_high: float
    direction: str  # "high" | "low"


@dataclass
class TrendPoint:
    date: Date
    value: float


@dataclass
class InteractionFinding:
    substances: Tuple[str, str]
    severity: str
    description: str
    kind: str  # "drug_drug" | "herb_drug"


@dataclass
class DuplicateTherapyFinding:
    drug_class: str
    medications: List[str]


@dataclass
class ReconciliationDiscrepancy:
    medication: str
    reported_by_patient: bool
    found_in_documents: bool


def flag_abnormal_values(entities: List[ExtractedEntity]) -> List[AbnormalFlag]:
    """Flags lab results outside reference range, preferring the range printed
    on the report itself and falling back to the curated table."""
    flags = []
    for e in entities:
        if e.entity_type != EntityType.LAB_RESULT:
            continue
        analyte = str(e.normalised.get("analyte", "")).strip().lower()
        value = e.normalised.get("value")
        if value is None:
            continue
        value = float(value)

        low = e.normalised.get("reference_low")
        high = e.normalised.get("reference_high")
        if low is None or high is None:
            ref = _REFERENCE_RANGES.get(analyte)
            if ref is None:
                continue
            low, high = ref
        low, high = float(low), float(high)

        if value < low:
            flags.append(AbnormalFlag(analyte, value, low, high, "low"))
        elif value > high:
            flags.append(AbnormalFlag(analyte, value, low, high, "high"))
    return flags


def detect_trend(entities: List[ExtractedEntity], analyte: str) -> List[TrendPoint]:
    """Same analyte across two or more dated documents, sorted chronologically."""
    analyte = analyte.lower()
    points = []
    for e in entities:
        if e.entity_type != EntityType.LAB_RESULT or e.doc_date is None:
            continue
        if str(e.normalised.get("analyte", "")).strip().lower() != analyte:
            continue
        value = e.normalised.get("value")
        if value is not None:
            points.append(TrendPoint(e.doc_date, float(value)))
    return sorted(points, key=lambda p: p.date)


def _medication_names(entities: List[ExtractedEntity]) -> List[str]:
    return [
        str(e.normalised.get("name", "")).strip().lower()
        for e in entities
        if e.entity_type == EntityType.MEDICATION and e.normalised.get("name")
    ]


def check_drug_interactions(entities: List[ExtractedEntity]) -> List[InteractionFinding]:
    names = set(_medication_names(entities))
    findings = []
    for pair, (severity, desc) in _DRUG_INTERACTIONS.items():
        if pair.issubset(names):
            a, b = tuple(pair)
            findings.append(InteractionFinding((a, b), severity, desc, "drug_drug"))
    return findings


def check_herb_drug_interactions(
    entities: List[ExtractedEntity], reported_substances: Optional[List[str]] = None
) -> List[InteractionFinding]:
    """
    `reported_substances` covers herbal/AYUSH substances the patient
    mentions verbally (they rarely appear as document "medications"), unioned
    with document-derived medication names.
    """
    names = set(_medication_names(entities))
    if reported_substances:
        names |= {s.strip().lower() for s in reported_substances}

    findings = []
    for pair, (severity, desc) in _HERB_DRUG_INTERACTIONS.items():
        if pair.issubset(names):
            a, b = tuple(pair)
            findings.append(InteractionFinding((a, b), severity, desc, "herb_drug"))
    return findings


def detect_duplicate_therapy(entities: List[ExtractedEntity]) -> List[DuplicateTherapyFinding]:
    """Same drug class prescribed more than once, e.g. by different providers."""
    by_class: Dict[str, List[str]] = {}
    for name in _medication_names(entities):
        drug_class = _DRUG_CLASSES.get(name)
        if drug_class is None:
            continue
        by_class.setdefault(drug_class, []).append(name)

    return [
        DuplicateTherapyFinding(drug_class=cls, medications=sorted(set(meds)))
        for cls, meds in by_class.items()
        if len(set(meds)) > 1
    ]


def reconcile_medications(
    patient_reported: List[str], document_entities: List[ExtractedEntity]
) -> List[ReconciliationDiscrepancy]:
    """
    What the patient says they take vs what the documents show was
    prescribed (PRD §11.3 "medication reconciliation"). Non-adherence and
    undisclosed medications both surface here as discrepancies.
    """
    reported = {s.strip().lower() for s in patient_reported}
    documented = set(_medication_names(document_entities))

    discrepancies = []
    for med in sorted(reported | documented):
        in_reported = med in reported
        in_documented = med in documented
        if in_reported != in_documented:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    medication=med, reported_by_patient=in_reported, found_in_documents=in_documented
                )
            )
    return discrepancies
