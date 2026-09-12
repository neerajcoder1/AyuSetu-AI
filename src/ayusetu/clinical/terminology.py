"""
AyuSetu Authoritative Terminology & Clinical History Service
============================================================
Authoritative terminology translation (NAMASTE <-> ICD-11 TM2/MMS, LOINC, SNOMED CT, RxNorm),
herb-drug and drug-drug interaction screening, and longitudinal prior records timeline retrieval
per PRD v2.0 §11.3, §13.1, §13.2, §14.1, §21.7, §22.2 & §22.5.
"""

from datetime import date as Date, datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.consent.service import consent_service
from ayusetu.consent.models import ConsentStatus
from ayusetu.clinical.repository import ClinicalRepository, get_default_session_factory
from ayusetu.clinical.models import EncounterDTO, SlotDTO
from ayusetu.common.models import Encounter as EncounterModel, Slot as SlotModel
from ayusetu.ai.clinical.document_ai.contracts import EntityType, ExtractedEntity
from ayusetu.ai.clinical.document_ai.clinical_intelligence import (
    check_drug_interactions,
    check_herb_drug_interactions,
)
from ayusetu.ai.clinical.memory.contracts import (
    EncounterSnapshot,
    SourceKind,
    TimelineEvent,
    TimelineEventType,
)
from ayusetu.ai.clinical.memory.timeline import build_patient_timeline

logger = logging.getLogger("ayusetu.clinical.terminology")

# Provenance attribution constant
TERMINOLOGY_PROVENANCE = (
    "National AYUSH Morbidity & Standardized Terminology Electronic (NAMASTE) Portal v2.0 / "
    "WHO ICD-11 TM2 & MMS / LOINC v2.74 / RxNorm"
)

# ---------------------------------------------------------------------------
# Authoritative Knowledge Bases (Deterministic Dual-Coding Mappings)
# ---------------------------------------------------------------------------

# NAMASTE / AYUSH Morbidity entries
# Key: canonical code / term normalized
_NAMASTE_CATALOG: Dict[str, Dict[str, Any]] = {
    "sk25": {
        "namaste_code": "SK25",
        "namaste_display": "Amlapitta",
        "system": "NAMASTE",
        "icd11_tm2": {"code": "SK25", "display": "Amlapitta (TM2)", "system": "ICD-11 TM2"},
        "icd11_mms": {"code": "DA42", "display": "Dyspepsia", "system": "ICD-11 MMS"},
        "snomed": {"code": "16331000", "display": "Heartburn", "system": "SNOMED-CT"},
        "synonyms": ["amlapitta", "hyperacidity", "acid peptic disorder", "dyspepsia", "gerd", "sk25"],
    },
    "ayu-pr-001": {
        "namaste_code": "AYU-PR-001",
        "namaste_display": "Prameha",
        "system": "NAMASTE",
        "icd11_tm2": {"code": "TM2-PR01", "display": "Prameha (TM2)", "system": "ICD-11 TM2"},
        "icd11_mms": {"code": "5A11", "display": "Type 2 diabetes mellitus", "system": "ICD-11 MMS"},
        "snomed": {"code": "73211009", "display": "Diabetes mellitus", "system": "SNOMED-CT"},
        "synonyms": ["prameha", "madhumeha", "diabetes mellitus", "type 2 diabetes", "ayu-pr-001", "pr01"],
    },
    "ayu-vd-001": {
        "namaste_code": "AYU-VD-001",
        "namaste_display": "Vata Dosha Imbalance",
        "system": "NAMASTE",
        "icd11_tm2": {"code": "TM2-VD01", "display": "Vata Vyadhi (TM2)", "system": "ICD-11 TM2"},
        "icd11_mms": {"code": "8E40", "display": "Disorders of the nervous system / musculoskeletal", "system": "ICD-11 MMS"},
        "snomed": {"code": "278860009", "display": "Musculoskeletal disorder", "system": "SNOMED-CT"},
        "synonyms": ["vata dosha imbalance", "vata vyadhi", "vatavyadhi", "neuromusculoskeletal disorder", "ayu-vd-001", "vd01"],
    },
    "ayu-am-001": {
        "namaste_code": "AYU-AM-001",
        "namaste_display": "Ama / Metabolic Dysregulation",
        "system": "NAMASTE",
        "icd11_tm2": {"code": "TM2-AM01", "display": "Ama (TM2)", "system": "ICD-11 TM2"},
        "icd11_mms": {"code": "5C53", "display": "Metabolic disorder", "system": "ICD-11 MMS"},
        "synonyms": ["ama", "metabolic endotoxemia", "metabolic dysregulation", "ayu-am-001", "am01"],
    },
    "ayu-kd-001": {
        "namaste_code": "AYU-KD-001",
        "namaste_display": "Kasa",
        "system": "NAMASTE",
        "icd11_tm2": {"code": "TM2-KD01", "display": "Kasa (TM2)", "system": "ICD-11 TM2"},
        "icd11_mms": {"code": "MD10", "display": "Cough", "system": "ICD-11 MMS"},
        "snomed": {"code": "49727002", "display": "Cough", "system": "SNOMED-CT"},
        "synonyms": ["kasa", "cough", "bronchial irritation", "ayu-kd-001", "kd01"],
    },
    "ayu-md-001": {
        "namaste_code": "AYU-MD-001",
        "namaste_display": "Medoroga / Sthaulya",
        "system": "NAMASTE",
        "icd11_tm2": {"code": "TM2-MD01", "display": "Sthaulya / Medoroga (TM2)", "system": "ICD-11 TM2"},
        "icd11_mms": {"code": "5B81", "display": "Obesity", "system": "ICD-11 MMS"},
        "snomed": {"code": "54718008", "display": "Obesity", "system": "SNOMED-CT"},
        "synonyms": ["medoroga", "sthaulya", "obesity", "dyslipidemia", "ayu-md-001", "md01"],
    },
    "ayu-jd-001": {
        "namaste_code": "AYU-JD-001",
        "namaste_display": "Jvara",
        "system": "NAMASTE",
        "icd11_tm2": {"code": "TM2-JD01", "display": "Jvara (TM2)", "system": "ICD-11 TM2"},
        "icd11_mms": {"code": "MG26", "display": "Fever of other or unknown origin", "system": "ICD-11 MMS"},
        "snomed": {"code": "386661006", "display": "Fever", "system": "SNOMED-CT"},
        "synonyms": ["jvara", "fever", "pyrexia", "ayu-jd-001", "jd01"],
    },
    "ayu-sd-001": {
        "namaste_code": "AYU-SD-001",
        "namaste_display": "Shwasa",
        "system": "NAMASTE",
        "icd11_tm2": {"code": "TM2-SD01", "display": "Shwasa (TM2)", "system": "ICD-11 TM2"},
        "icd11_mms": {"code": "CA23", "display": "Asthma", "system": "ICD-11 MMS"},
        "snomed": {"code": "195967001", "display": "Asthma", "system": "SNOMED-CT"},
        "synonyms": ["shwasa", "asthma", "dyspnea", "ayu-sd-001", "sd01"],
    },
    "ayu-hd-001": {
        "namaste_code": "AYU-HD-001",
        "namaste_display": "Hridroga",
        "system": "NAMASTE",
        "icd11_tm2": {"code": "TM2-HD01", "display": "Hridroga (TM2)", "system": "ICD-11 TM2"},
        "icd11_mms": {"code": "BA00", "display": "Essential hypertension", "system": "ICD-11 MMS"},
        "snomed": {"code": "38341003", "display": "Hypertensive disorder", "system": "SNOMED-CT"},
        "synonyms": ["hridroga", "hypertension", "essential hypertension", "high blood pressure", "ayu-hd-001", "hd01"],
    },
}

# LOINC Analyte Mappings
_LOINC_CATALOG: Dict[str, Dict[str, Any]] = {
    "718-7": {
        "code": "718-7",
        "display": "Hemoglobin [Mass/volume] in Blood",
        "analyte": "hemoglobin",
        "system": "LOINC",
        "reference_range": {"low": 12.0, "high": 16.5, "unit": "g/dL"},
        "synonyms": ["718-7", "hemoglobin", "hb", "hgb"],
    },
    "4548-4": {
        "code": "4548-4",
        "display": "Hemoglobin A1c/Hemoglobin.total in Blood",
        "analyte": "hba1c",
        "system": "LOINC",
        "reference_range": {"low": 4.0, "high": 5.6, "unit": "%"},
        "synonyms": ["4548-4", "hba1c", "glycated hemoglobin", "a1c"],
    },
    "1558-6": {
        "code": "1558-6",
        "display": "Fasting glucose [Mass/volume] in Blood",
        "analyte": "fbs",
        "system": "LOINC",
        "reference_range": {"low": 70.0, "high": 100.0, "unit": "mg/dL"},
        "synonyms": ["1558-6", "fbs", "fasting blood sugar", "fasting blood glucose"],
    },
    "2160-0": {
        "code": "2160-0",
        "display": "Creatinine [Mass/volume] in Serum or Plasma",
        "analyte": "creatinine",
        "system": "LOINC",
        "reference_range": {"low": 0.6, "high": 1.3, "unit": "mg/dL"},
        "synonyms": ["2160-0", "creatinine", "serum creatinine"],
    },
    "3016-3": {
        "code": "3016-3",
        "display": "Thyrotropin [Units/volume] in Serum or Plasma",
        "analyte": "tsh",
        "system": "LOINC",
        "reference_range": {"low": 0.4, "high": 4.0, "unit": "uIU/mL"},
        "synonyms": ["3016-3", "tsh", "thyroid stimulating hormone", "thyrotropin"],
    },
}

# Medication & Diagnosis Vocabulary (Synchronized with Safety Gate 2)
_MED_VOCABULARY: Dict[str, Dict[str, str]] = {
    "metformin": {"system": "RxNorm", "code": "6809", "display": "Metformin"},
    "6809": {"system": "RxNorm", "code": "6809", "display": "Metformin"},
    "amlodipine": {"system": "RxNorm", "code": "17767", "display": "Amlodipine"},
    "17767": {"system": "RxNorm", "code": "17767", "display": "Amlodipine"},
    "paracetamol": {"system": "RxNorm", "code": "161", "display": "Paracetamol"},
    "161": {"system": "RxNorm", "code": "161", "display": "Paracetamol"},
    "warfarin": {"system": "RxNorm", "code": "11289", "display": "Warfarin"},
    "aspirin": {"system": "RxNorm", "code": "1191", "display": "Aspirin"},
    "hypertension": {"system": "ICD-11", "code": "BA00", "display": "Essential hypertension"},
    "ba00": {"system": "ICD-11", "code": "BA00", "display": "Essential hypertension"},
    "diabetes mellitus": {"system": "ICD-11", "code": "5A11", "display": "Type 2 diabetes mellitus"},
    "5a11": {"system": "ICD-11", "code": "5A11", "display": "Type 2 diabetes mellitus"},
}


class TerminologyService:
    """
    Authoritative service managing terminology mapping ($translate),
    herb-drug & drug-drug interaction screening, and prior clinical records retrieval.
    """

    def __init__(self, repository: Optional[ClinicalRepository] = None) -> None:
        self.repository = repository or ClinicalRepository()
        self._session_factory = get_default_session_factory()

    def translate(
        self,
        code: str,
        system: str = "NAMASTE",
        target_system: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic dual-directional terminology translation per PRD §13.1 & §22.2.
        Supports:
        - NAMASTE -> ICD-11 TM2 / MMS, SNOMED CT
        - ICD-11 (TM2 or MMS) -> NAMASTE
        - LOINC analyte mappings
        - RxNorm / Gate 2 closed vocabulary

        Returns structured match list with confidence scores and provenance.
        Returns empty matches if unmapped (zero hallucinated codes).
        """
        raw_code = (code or "").strip()
        norm_code = raw_code.lower()
        norm_system = (system or "").strip().upper()
        norm_target = (target_system or "").strip().upper() if target_system else None

        if not raw_code:
            return {
                "source_code": raw_code,
                "source_system": system,
                "matches": [],
                "provenance": TERMINOLOGY_PROVENANCE,
            }

        matches: List[Dict[str, Any]] = []

        # 1. Check NAMASTE catalog (by code or synonym)
        # Search direct code match
        namaste_entry = _NAMASTE_CATALOG.get(norm_code)
        exact_code_match = bool(namaste_entry)

        if not namaste_entry:
            # Search by synonyms or reverse ICD-11 codes
            for entry in _NAMASTE_CATALOG.values():
                if norm_code in entry["synonyms"]:
                    namaste_entry = entry
                    break
                # Check ICD-11 TM2 code
                if entry.get("icd11_tm2", {}).get("code", "").lower() == norm_code:
                    namaste_entry = entry
                    break
                # Check ICD-11 MMS code
                if entry.get("icd11_mms", {}).get("code", "").lower() == norm_code:
                    namaste_entry = entry
                    break

        if namaste_entry:
            # If translating FROM ICD-11 or source is ICD-11, provide NAMASTE target
            if "ICD-11" in norm_system or norm_target == "NAMASTE":
                conf = 1.0 if (
                    namaste_entry.get("icd11_tm2", {}).get("code", "").lower() == norm_code
                    or namaste_entry.get("icd11_mms", {}).get("code", "").lower() == norm_code
                ) else 0.9
                matches.append({
                    "system": namaste_entry["system"],
                    "code": namaste_entry["namaste_code"],
                    "display": namaste_entry["namaste_display"],
                    "confidence": conf,
                })
            else:
                # Translating FROM NAMASTE or default -> return ICD-11 TM2 / MMS / SNOMED
                base_conf = 1.0 if exact_code_match or namaste_entry["namaste_code"].lower() == norm_code else 0.85
                
                if "icd11_tm2" in namaste_entry and (not norm_target or "TM2" in norm_target or "ICD-11" in norm_target):
                    tm2 = namaste_entry["icd11_tm2"]
                    matches.append({
                        "system": tm2["system"],
                        "code": tm2["code"],
                        "display": tm2["display"],
                        "confidence": base_conf,
                    })

                if "icd11_mms" in namaste_entry and (not norm_target or "MMS" in norm_target or "ICD-11" in norm_target):
                    mms = namaste_entry["icd11_mms"]
                    matches.append({
                        "system": mms["system"],
                        "code": mms["code"],
                        "display": mms["display"],
                        "confidence": base_conf,
                    })

                if "snomed" in namaste_entry and (not norm_target or "SNOMED" in norm_target):
                    snomed = namaste_entry["snomed"]
                    matches.append({
                        "system": snomed["system"],
                        "code": snomed["code"],
                        "display": snomed["display"],
                        "confidence": round(base_conf * 0.95, 2),
                    })

        # 2. Check LOINC catalog
        loinc_entry = _LOINC_CATALOG.get(raw_code) or _LOINC_CATALOG.get(norm_code)
        if not loinc_entry:
            for entry in _LOINC_CATALOG.values():
                if norm_code in entry["synonyms"]:
                    loinc_entry = entry
                    break

        if loinc_entry:
            conf = 1.0 if loinc_entry["code"].lower() == norm_code else 0.95
            matches.append({
                "system": loinc_entry["system"],
                "code": loinc_entry["code"],
                "display": loinc_entry["display"],
                "analyte": loinc_entry["analyte"],
                "reference_range": loinc_entry.get("reference_range"),
                "confidence": conf,
            })

        # 3. Check Gate 2 Medication / Diagnostic closed vocabulary
        med_entry = _MED_VOCABULARY.get(norm_code)
        if med_entry:
            matches.append({
                "system": med_entry["system"],
                "code": med_entry["code"],
                "display": med_entry["display"],
                "confidence": 1.0 if med_entry["code"].lower() == norm_code else 0.95,
            })

        return {
            "source_code": raw_code,
            "source_system": system,
            "matches": matches,
            "provenance": TERMINOLOGY_PROVENANCE,
        }

    def check_interactions(self, drugs: List[str]) -> Dict[str, Any]:
        """
        Screen drug-drug and AYUSH herb-drug interactions deterministically
        by reusing the clinical intelligence engine from PRD §11.3.
        """
        cleaned_drugs = [d.strip() for d in (drugs or []) if d and d.strip()]
        if not cleaned_drugs:
            return {"checked_drugs": [], "interactions": []}

        entities = [
            ExtractedEntity(
                entity_type=EntityType.MEDICATION,
                raw_text=d,
                normalised={"name": d.strip().lower()},
                confidence=1.0,
                page_no=1,
            )
            for d in cleaned_drugs
        ]

        # Run clinical intelligence screening
        drug_findings = check_drug_interactions(entities)
        herb_findings = check_herb_drug_interactions(entities, reported_substances=cleaned_drugs)

        # Merge findings uniquely
        all_findings = []
        seen_pairs: Set[Tuple[str, str]] = set()

        for f in drug_findings + herb_findings:
            pair_key = (min(f.substances), max(f.substances))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            all_findings.append({
                "substances": list(f.substances),
                "severity": f.severity,
                "description": f.description,
                "kind": f.kind,
            })

        # Sort findings deterministically by severity and substance name
        severity_order = {"severe": 1, "moderate": 2, "low": 3}
        all_findings.sort(key=lambda item: (severity_order.get(item["severity"], 9), item["substances"]))

        return {
            "checked_drugs": cleaned_drugs,
            "interactions": all_findings,
        }

    def get_prior_records(
        self,
        encounter_id: str,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve patient prior records and longitudinal timeline from PostgreSQL
        per PRD §13.2 & §14.1.
        Enforces patient boundaries and active clinical consent.
        """
        encounter = self.repository.get_encounter(encounter_id)
        if not encounter:
            raise AyuSetuGatewayError(
                ErrorCode.NOT_FOUND,
                f"Encounter not found: {encounter_id}",
                404,
            )

        patient_id = encounter.patient_id

        # Consent verification: active clinical consent is mandatory
        # Check active consent record for the encounter or verify clinical consent for patient
        active_consent = consent_service.get_active_consent(encounter_id)
        if active_consent is None or active_consent.status != ConsentStatus.ACTIVE or not active_consent.purposes.get("clinical", False):
            raise AyuSetuGatewayError(
                ErrorCode.CONSENT_REQUIRED,
                f"Active clinical consent required to view prior records for encounter '{encounter_id}'",
                403,
            )

        # Retrieve all historical encounters for this patient from PostgreSQL
        pat_uuid = uuid.UUID(str(patient_id))
        with self._session_factory() as db:
            enc_rows = (
                db.query(EncounterModel)
                .filter(EncounterModel.patient_id == pat_uuid)
                .order_by(EncounterModel.started_at.asc())
                .all()
            )

        # Build snapshots for each encounter
        snapshots: List[EncounterSnapshot] = []
        for row in enc_rows:
            enc_id = str(row.id)
            slots = self.repository.get_slots(enc_id)
            
            # Map slots to collected_info dict
            collected_info: Dict[str, Any] = {}
            for slot in slots:
                collected_info[slot.path] = slot.value

            enc_date: Optional[Date] = None
            if row.started_at:
                try:
                    if isinstance(row.started_at, str):
                        enc_date = datetime.fromisoformat(row.started_at).date()
                    elif isinstance(row.started_at, datetime):
                        enc_date = row.started_at.date()
                except Exception:
                    enc_date = None

            snapshot = EncounterSnapshot(
                encounter_id=enc_id,
                date=enc_date,
                collected_info=collected_info,
                missing_slots=[],
                document_entities=[],
                red_flag_titles=[],
            )
            snapshots.append(snapshot)

        # Build patient timeline using authoritative timeline engine
        timeline_events = build_patient_timeline(snapshots)

        # Format timeline records for JSON output
        records = [
            {
                "encounter_id": event.encounter_id,
                "date": event.date.isoformat() if event.date else None,
                "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
                "title": event.title,
                "detail": event.detail,
                "source": event.source.value if hasattr(event.source, "value") else str(event.source),
                "source_ref": event.source_ref,
                "confidence": event.confidence,
                "elicited": event.elicited,
            }
            for event in timeline_events
        ]

        return {
            "encounter_id": encounter_id,
            "patient_id": str(patient_id),
            "encounter_count": len(enc_rows),
            "records": records,
        }


# Authoritative singleton
terminology_service = TerminologyService()
