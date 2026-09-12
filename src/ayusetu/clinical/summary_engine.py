"""
Clinical Summary Synthesis & Provenance Engine
==============================================
Deterministic, non-generative Slot -> Summary transformation engine per PRD v2.0 §14 & packages/schemas/summary.json.
Generates structured clinical sections (HPI, PMH, Medications, Allergies, Lifestyle),
preserves granular provenance citations, and strictly preserves unelicited information without false negative inferences.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

import jsonschema

from ayusetu.clinical.models import (
    ClinicalSummaryDTO,
    SlotDTO,
    SlotSource,
    SummaryClause,
    SummarySection,
    SummaryStatus,
)

logger = logging.getLogger("ayusetu.clinical.summary_engine")

SCHEMA_PATH = Path(__file__).parents[3] / "packages" / "schemas" / "summary.json"
_CACHED_SCHEMA: Optional[Dict[str, Any]] = None


def get_summary_schema() -> Dict[str, Any]:
    """Load and cache the authoritative JSON schema for ClinicalSummary."""
    global _CACHED_SCHEMA
    if _CACHED_SCHEMA is None:
        if SCHEMA_PATH.exists():
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                _CACHED_SCHEMA = json.load(f)
        else:
            # Fallback schema matching packages/schemas/summary.json exactly
            _CACHED_SCHEMA = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://ayusetu.in/schemas/summary.json",
                "title": "ClinicalSummary",
                "type": "object",
                "required": ["encounter_id", "status", "model_version", "sections"],
                "properties": {
                    "encounter_id": {"type": "string", "format": "uuid"},
                    "version": {"type": "integer", "default": 1},
                    "status": {"type": "string", "enum": ["preliminary", "final"]},
                    "model_version": {"type": "string"},
                    "sections": {"type": "array"},
                    "alerts": {"type": "array"},
                    "coding": {"type": "array"},
                    "signed_by": {"type": ["string", "null"]},
                    "signed_at": {"type": ["string", "null"]},
                },
            }
    return _CACHED_SCHEMA


class SummarySynthesisEngine:
    """
    Deterministic synthesis engine mapping persisted Slot records to structured summary.
    """
    MODEL_VERSION = "ayusetu-synthesis-v1.0"

    def synthesize(
        self,
        encounter_id: str,
        slots: List[SlotDTO],
        alerts: Optional[List[Dict[str, Any]]] = None,
        coding: Optional[List[Dict[str, Any]]] = None,
    ) -> ClinicalSummaryDTO:
        """
        Synthesize structured clinical summary from Slot records.
        """
        # Group slots by domain prefix / path
        slot_map: Dict[str, SlotDTO] = {s.path.lower(): s for s in slots}

        sections: List[SummarySection] = [
            self._synthesize_hpi(slots, slot_map),
            self._synthesize_pmh(slots, slot_map),
            self._synthesize_medications(slots, slot_map),
            self._synthesize_allergies(slots, slot_map),
            self._synthesize_lifestyle(slots, slot_map),
        ]

        summary_dto = ClinicalSummaryDTO(
            encounter_id=str(encounter_id),
            version=1,
            status=SummaryStatus.PRELIMINARY,
            model_version=self.MODEL_VERSION,
            sections=sections,
            alerts=alerts or [],
            coding=coding or [],
            signed_by=None,
            signed_at=None,
        )

        # Validate against JSON schema
        self.validate_schema(summary_dto.model_dump(mode="json"))
        return summary_dto

    def validate_schema(self, summary_dict: Dict[str, Any]) -> None:
        """Validate summary payload against packages/schemas/summary.json."""
        schema = get_summary_schema()
        # Format checker for UUID and date-time
        format_checker = jsonschema.FormatChecker()
        jsonschema.validate(instance=summary_dict, schema=schema, format_checker=format_checker)

    def _build_source_dict(self, slot: SlotDTO) -> Dict[str, Any]:
        """Build provenance source object."""
        ids = [slot.id]
        if slot.source_ref:
            ids.append(slot.source_ref)
        return {
            "type": slot.source.value,
            "ids": ids,
        }

    def _synthesize_hpi(self, all_slots: List[SlotDTO], slot_map: Dict[str, SlotDTO]) -> SummarySection:
        """Synthesize History of Present Illness section."""
        clauses: List[SummaryClause] = []

        # Find primary chief complaint / symptoms
        cc_slot = (
            slot_map.get("hpi.chief_complaint")
            or slot_map.get("chief_complaint")
            or slot_map.get("symptoms.primary")
        )
        duration_slot = slot_map.get("hpi.duration") or slot_map.get("duration")
        severity_slot = slot_map.get("hpi.severity") or slot_map.get("severity")
        location_slot = slot_map.get("hpi.location") or slot_map.get("location")
        onset_slot = slot_map.get("hpi.onset") or slot_map.get("onset")

        if cc_slot and cc_slot.elicited and cc_slot.value:
            parts = [f"Chief complaint of {cc_slot.value}"]
            referenced_slots = [cc_slot.path]
            source_ids = [cc_slot.id]
            if cc_slot.source_ref:
                source_ids.append(cc_slot.source_ref)
            confidences = [cc_slot.confidence] if cc_slot.confidence is not None else []

            if duration_slot and duration_slot.elicited and duration_slot.value:
                parts.append(f"for {duration_slot.value}")
                referenced_slots.append(duration_slot.path)
                source_ids.append(duration_slot.id)
                if duration_slot.source_ref:
                    source_ids.append(duration_slot.source_ref)
                if duration_slot.confidence is not None:
                    confidences.append(duration_slot.confidence)

            if severity_slot and severity_slot.elicited and severity_slot.value:
                parts.append(f"with {severity_slot.value} severity")
                referenced_slots.append(severity_slot.path)
                source_ids.append(severity_slot.id)
                if severity_slot.source_ref:
                    source_ids.append(severity_slot.source_ref)
                if severity_slot.confidence is not None:
                    confidences.append(severity_slot.confidence)

            if location_slot and location_slot.elicited and location_slot.value:
                parts.append(f"located in {location_slot.value}")
                referenced_slots.append(location_slot.path)
                source_ids.append(location_slot.id)
                if location_slot.source_ref:
                    source_ids.append(location_slot.source_ref)
                if location_slot.confidence is not None:
                    confidences.append(location_slot.confidence)

            if onset_slot and onset_slot.elicited and onset_slot.value:
                parts.append(f"(onset: {onset_slot.value})")
                referenced_slots.append(onset_slot.path)
                source_ids.append(onset_slot.id)
                if onset_slot.source_ref:
                    source_ids.append(onset_slot.source_ref)
                if onset_slot.confidence is not None:
                    confidences.append(onset_slot.confidence)

            avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 1.0
            clauses.append(
                SummaryClause(
                    text=" ".join(parts) + ".",
                    slots=referenced_slots,
                    source={"type": cc_slot.source.value, "ids": source_ids},
                    confidence=avg_confidence,
                    elicited=True,
                )
            )

        # Other HPI / Symptom slots
        for slot in all_slots:
            p = slot.path.lower()
            if (p.startswith("hpi.") or p.startswith("symptoms.")) and p not in (
                "hpi.chief_complaint", "hpi.duration", "hpi.severity", "hpi.location", "hpi.onset"
            ):
                if slot.elicited and slot.value:
                    clauses.append(
                        SummaryClause(
                            text=f"Associated symptom ({slot.path}): {slot.value}.",
                            slots=[slot.path],
                            source=self._build_source_dict(slot),
                            confidence=slot.confidence if slot.confidence is not None else 1.0,
                            elicited=True,
                        )
                    )

        if not clauses:
            # Explicitly unelicited
            clauses.append(
                SummaryClause(
                    text="History of present illness not elicited.",
                    slots=[],
                    source={"type": "derived", "ids": []},
                    confidence=1.0,
                    elicited=False,
                )
            )

        return SummarySection(id="hpi", title="History of Present Illness", clauses=clauses)

    def _synthesize_pmh(self, all_slots: List[SlotDTO], slot_map: Dict[str, SlotDTO]) -> SummarySection:
        """Synthesize Past Medical History section."""
        clauses: List[SummaryClause] = []

        pmh_slots = [
            s for s in all_slots
            if s.path.lower().startswith("pmh.") or s.path.lower() in ("past_medical_history", "pmh")
        ]

        for slot in pmh_slots:
            if slot.elicited and slot.value:
                clauses.append(
                    SummaryClause(
                        text=f"Past medical condition: {slot.value}.",
                        slots=[slot.path],
                        source=self._build_source_dict(slot),
                        confidence=slot.confidence if slot.confidence is not None else 1.0,
                        elicited=True,
                    )
                )

        if not clauses:
            # Preserves unelicited state (CRITICAL: Never assume negative)
            clauses.append(
                SummaryClause(
                    text="Past medical history not elicited.",
                    slots=["pmh"],
                    source={"type": "derived", "ids": []},
                    confidence=1.0,
                    elicited=False,
                )
            )

        return SummarySection(id="pmh", title="Past Medical History", clauses=clauses)

    def _synthesize_medications(self, all_slots: List[SlotDTO], slot_map: Dict[str, SlotDTO]) -> SummarySection:
        """Synthesize Current Medications section."""
        clauses: List[SummaryClause] = []

        med_slots = [
            s for s in all_slots
            if s.path.lower().startswith("medications.") or s.path.lower() in ("medications", "meds")
        ]

        for slot in med_slots:
            if slot.elicited and slot.value:
                clauses.append(
                    SummaryClause(
                        text=f"Current medication: {slot.value}.",
                        slots=[slot.path],
                        source=self._build_source_dict(slot),
                        confidence=slot.confidence if slot.confidence is not None else 1.0,
                        elicited=True,
                    )
                )

        if not clauses:
            # Preserves unelicited state (CRITICAL: Never assume negative)
            clauses.append(
                SummaryClause(
                    text="Current medications not elicited.",
                    slots=["medications"],
                    source={"type": "derived", "ids": []},
                    confidence=1.0,
                    elicited=False,
                )
            )

        return SummarySection(id="medications", title="Medications", clauses=clauses)

    def _synthesize_allergies(self, all_slots: List[SlotDTO], slot_map: Dict[str, SlotDTO]) -> SummarySection:
        """Synthesize Allergies section."""
        clauses: List[SummaryClause] = []

        allergy_slots = [
            s for s in all_slots
            if s.path.lower().startswith("allergies.") or s.path.lower() in ("allergies", "allergy")
        ]

        for slot in allergy_slots:
            if slot.elicited:
                conf = slot.confidence if slot.confidence is not None else 1.0
                val_str = str(slot.value).lower().strip()
                if val_str in ("none", "no known allergies", "no allergies", "nka", "nkda", "nil"):
                    # Explicit elicited negative finding
                    clauses.append(
                        SummaryClause(
                            text="No known drug or environmental allergies reported.",
                            slots=[slot.path],
                            source=self._build_source_dict(slot),
                            confidence=conf,
                            elicited=True,
                        )
                    )
                elif slot.value:
                    clauses.append(
                        SummaryClause(
                            text=f"Allergy reported: {slot.value}.",
                            slots=[slot.path],
                            source=self._build_source_dict(slot),
                            confidence=conf,
                            elicited=True,
                        )
                    )

        if not clauses:
            # Preserves unelicited state (CRITICAL: Must be explicitly elicited=False)
            clauses.append(
                SummaryClause(
                    text="Allergies not elicited.",
                    slots=["allergies"],
                    source={"type": "derived", "ids": []},
                    confidence=1.0,
                    elicited=False,
                )
            )

        return SummarySection(id="allergies", title="Allergies", clauses=clauses)

    def _synthesize_lifestyle(self, all_slots: List[SlotDTO], slot_map: Dict[str, SlotDTO]) -> SummarySection:
        """Synthesize Lifestyle & Social History section."""
        clauses: List[SummaryClause] = []

        lifestyle_slots = [
            s for s in all_slots
            if s.path.lower().startswith("lifestyle.") or s.path.lower() in ("lifestyle", "family_history")
        ]

        for slot in lifestyle_slots:
            if slot.elicited and slot.value:
                clauses.append(
                    SummaryClause(
                        text=f"Lifestyle factor ({slot.path}): {slot.value}.",
                        slots=[slot.path],
                        source=self._build_source_dict(slot),
                        confidence=slot.confidence if slot.confidence is not None else 1.0,
                        elicited=True,
                    )
                )

        if not clauses:
            # Preserves unelicited state
            clauses.append(
                SummaryClause(
                    text="Lifestyle and social history not elicited.",
                    slots=["lifestyle"],
                    source={"type": "derived", "ids": []},
                    confidence=1.0,
                    elicited=False,
                )
            )

        return SummarySection(id="lifestyle", title="Lifestyle & Social History", clauses=clauses)


# Global singleton engine
summary_synthesis_engine = SummarySynthesisEngine()
