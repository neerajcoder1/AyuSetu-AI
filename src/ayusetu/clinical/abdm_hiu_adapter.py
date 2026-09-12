"""
Mock ABDM HIU Longitudinal Record Adapter
=========================================
Authoritative mock HIU data flow adapter per PRD v3 §10.2 and §17.3.
Provides:
1. Parsing and validation of synthetic external FHIR R4 CareContext bundles.
2. Ingestion and merging into patient longitudinal history with explicit external provenance.
3. Idempotent deduplication preventing duplicate external record ingestion.
4. Fail-safe handling for malformed or unauthorized bundles without crashing.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
import uuid6

from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode

logger = logging.getLogger("ayusetu.clinical.abdm_hiu")


class ExternalClinicalEntry(BaseModel):
    entry_id: str
    entry_type: str  # "condition", "medication", "observation", "allergy"
    code: Optional[str] = None
    display: str
    code_system: Optional[str] = None
    recorded_date: Optional[str] = None
    facility: str
    source: str = "abdm_hiu"
    provenance_type: str = "external_abdm"


class ParsedCareContext(BaseModel):
    care_context_ref: str
    patient_id: str
    facility_name: str
    encounter_type: str
    encounter_date: str
    entries: List[ExternalClinicalEntry] = Field(default_factory=list)
    raw_bundle_id: Optional[str] = None


class AbdmHiuAdapter:
    """Mock HIU Adapter coordinating external ABDM record ingestion."""

    def __init__(self) -> None:
        self._imported_context_refs: Set[str] = set()
        self._patient_external_records: Dict[str, List[ParsedCareContext]] = {}

    def parse_fhir_bundle(
        self,
        bundle: Dict[str, Any],
        facility_name: str = "External Hospital (ABDM)",
    ) -> ParsedCareContext:
        """
        Parse and validate a synthetic FHIR R4 Bundle into structured clinical entries.
        Raises AyuSetuGatewayError on malformed structure.
        """
        if not isinstance(bundle, dict):
            raise AyuSetuGatewayError(ErrorCode.POLICY_DENIED, "Invalid FHIR bundle: must be a JSON object", 422)

        resource_type = bundle.get("resourceType")
        if resource_type != "Bundle":
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Invalid FHIR resource: expected 'Bundle', got '{resource_type}'",
                422,
            )

        bundle_id = bundle.get("id") or str(uuid6.uuid7())
        entries_raw = bundle.get("entry", [])
        if not isinstance(entries_raw, list):
            raise AyuSetuGatewayError(ErrorCode.POLICY_DENIED, "Malformed FHIR bundle: 'entry' must be a list", 422)

        patient_id = "unknown_patient"
        encounter_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        encounter_type = "OPD Consultation"
        clinical_entries: List[ExternalClinicalEntry] = []

        for item in entries_raw:
            if not isinstance(item, dict):
                continue
            res = item.get("resource", {})
            rtype = res.get("resourceType", "")

            if rtype == "Patient":
                patient_id = res.get("id") or patient_id
            elif rtype == "Encounter":
                encounter_date = res.get("period", {}).get("start", encounter_date)[:10]
                encounter_type = res.get("class", {}).get("display", encounter_type)
            elif rtype == "Condition":
                code_obj = res.get("code", {})
                coding = code_obj.get("coding", [{}])[0] if code_obj.get("coding") else {}
                display = coding.get("display") or code_obj.get("text") or "External Condition"
                clinical_entries.append(
                    ExternalClinicalEntry(
                        entry_id=res.get("id") or str(uuid6.uuid7()),
                        entry_type="condition",
                        code=coding.get("code"),
                        code_system=coding.get("system"),
                        display=display,
                        recorded_date=res.get("recordedDate") or encounter_date,
                        facility=facility_name,
                    )
                )
            elif rtype == "MedicationStatement":
                med_obj = res.get("medicationCodeableConcept", {})
                coding = med_obj.get("coding", [{}])[0] if med_obj.get("coding") else {}
                display = coding.get("display") or med_obj.get("text") or "External Medication"
                clinical_entries.append(
                    ExternalClinicalEntry(
                        entry_id=res.get("id") or str(uuid6.uuid7()),
                        entry_type="medication",
                        code=coding.get("code"),
                        code_system=coding.get("system"),
                        display=display,
                        recorded_date=encounter_date,
                        facility=facility_name,
                    )
                )
            elif rtype == "Observation":
                obs_code = res.get("code", {})
                coding = obs_code.get("coding", [{}])[0] if obs_code.get("coding") else {}
                display = coding.get("display") or obs_code.get("text") or "External Observation"
                val = res.get("valueQuantity", {}).get("value")
                unit = res.get("valueQuantity", {}).get("unit", "")
                if val is not None:
                    display = f"{display}: {val} {unit}".strip()
                clinical_entries.append(
                    ExternalClinicalEntry(
                        entry_id=res.get("id") or str(uuid6.uuid7()),
                        entry_type="observation",
                        code=coding.get("code"),
                        code_system=coding.get("system"),
                        display=display,
                        recorded_date=res.get("effectiveDateTime") or encounter_date,
                        facility=facility_name,
                    )
                )

        care_context_ref = f"carecontext-{bundle_id[:16]}"
        return ParsedCareContext(
            care_context_ref=care_context_ref,
            patient_id=patient_id,
            facility_name=facility_name,
            encounter_type=encounter_type,
            encounter_date=encounter_date,
            entries=clinical_entries,
            raw_bundle_id=bundle_id,
        )

    def import_external_bundle(
        self,
        patient_id: str,
        bundle: Dict[str, Any],
        facility_name: str = "AIIMS New Delhi",
    ) -> Dict[str, Any]:
        """
        Import external FHIR bundle into patient's longitudinal record.
        Enforces deduplication and provenance attribution.
        """
        parsed = self.parse_fhir_bundle(bundle, facility_name=facility_name)
        
        # Check duplicate import
        if parsed.care_context_ref in self._imported_context_refs:
            return {
                "status": "deduplicated",
                "care_context_ref": parsed.care_context_ref,
                "imported_entries": 0,
                "message": "CareContext already imported; duplicate import skipped",
            }

        self._imported_context_refs.add(parsed.care_context_ref)
        if patient_id not in self._patient_external_records:
            self._patient_external_records[patient_id] = []
        self._patient_external_records[patient_id].append(parsed)

        # Merge entries into terminology / timeline service if available
        try:
            from ayusetu.clinical.terminology import terminology_service
            for entry in parsed.entries:
                terminology_service.add_prior_record(
                    encounter_id=f"ext-{parsed.care_context_ref}",
                    patient_id=patient_id,
                    diagnosis=entry.display if entry.entry_type == "condition" else None,
                    medications=[entry.display] if entry.entry_type == "medication" else None,
                )
        except Exception as e:
            logger.warning("Could not sync into terminology service: %s", e)

        return {
            "status": "imported",
            "patient_id": patient_id,
            "care_context_ref": parsed.care_context_ref,
            "facility_name": parsed.facility_name,
            "encounter_date": parsed.encounter_date,
            "imported_entries": len(parsed.entries),
            "entries": [e.model_dump() for e in parsed.entries],
            "abdm_provenance": "PROVISIONAL_HIU_MOCK_VERIFIED",
        }

    def get_external_records_for_patient(self, patient_id: str) -> List[Dict[str, Any]]:
        """Retrieve all external ABDM HIU records for a patient."""
        records = self._patient_external_records.get(patient_id, [])
        return [r.model_dump() for r in records]

    def clear(self) -> None:
        """Clear memory for testing."""
        self._imported_context_refs.clear()
        self._patient_external_records.clear()


abdm_hiu_adapter = AbdmHiuAdapter()
