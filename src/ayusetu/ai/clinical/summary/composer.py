"""
SummaryGenerator: orchestrates the five gates into one ClinicalSummary
(PRD §13.2 structure), starting life as status=PRELIMINARY per §13.3
("Nothing enters the record unsigned").
"""

import re
from typing import Dict, List, Optional

from ayusetu.ai.clinical.document_ai import clinical_intelligence as ci
from ayusetu.ai.clinical.document_ai.contracts import ExtractedEntity
from ayusetu.ai.clinical.summary.contracts import (
    ClinicalSummary,
    CodingCandidate,
    HeaderSection,
    StructuredField,
    SummaryAlert,
)
from ayusetu.ai.clinical.summary.gates import (
    gate1_build_source_context,
    gate2_resolve_terminology,
    gate3_constrain_to_schema,
    gate5_render_field,
)
from ayusetu.ai.clinical.summary.narrative import generate_hpi_narrative
from ayusetu.ai.clinical.summary.gates import filter_entailed_clauses

_STRUCTURED_HISTORY_LABELS = {
    "past_medical_history": "Past medical history",
    "medications": "Medications",
    "allergies": "Allergies",
    "family_history": "Family history",
    "lifestyle": "Lifestyle",
}

_ALLOWED_SUMMARY_FIELDS = set(ClinicalSummary.model_fields.keys())


class SummaryGenerator:
    def generate(
        self,
        encounter_id: str,
        collected_info: Dict,
        missing_slots: List,
        red_flag_events: Optional[list] = None,
        header: Optional[HeaderSection] = None,
        document_entities: Optional[List[ExtractedEntity]] = None,
    ) -> ClinicalSummary:
        # Gate 1
        context = gate1_build_source_context(collected_info, missing_slots)

        # Narrative, then Gate 4
        hpi_clauses = generate_hpi_narrative(context)
        hpi_clauses = filter_entailed_clauses(hpi_clauses, context)

        # Gate 5 — structured, collapsible fields with explicit "not elicited"
        structured_history = {
            slot_path: gate5_render_field(label, context, slot_path)
            for slot_path, label in _STRUCTURED_HISTORY_LABELS.items()
        }

        # Alerts: red-flag engine output (tiered) plus document/clinical
        # intelligence findings (untiered) — PRD §13.2 groups both into one
        # Alerts section ("Tier 1 and 2 flags... abnormal laboratory values;
        # drug and herb–drug interactions").
        alerts = [
            SummaryAlert(
                tier=int(event.tier),
                category="red_flag",
                title=event.title,
                acknowledged=event.acknowledged_at is not None,
            )
            for event in (red_flag_events or [])
        ]
        alerts.extend(self._clinical_intelligence_alerts(context, document_entities or []))

        # Gate 2 — suggested coding, only for terms that resolve
        suggested_coding = self._suggest_coding(context)

        # Gate 3 — construct the candidate field set, then constrain it
        candidate_fields = {
            "encounter_id": encounter_id,
            "header": header or HeaderSection(),
            "alerts": alerts,
            "chief_complaint": context.slots.get("chief_complaint"),
            "hpi_narrative": hpi_clauses,
            "structured_history": structured_history,
            "suggested_coding": suggested_coding,
        }
        constrained = gate3_constrain_to_schema(candidate_fields, _ALLOWED_SUMMARY_FIELDS)

        return ClinicalSummary(**constrained)

    def _clinical_intelligence_alerts(self, context, document_entities: List[ExtractedEntity]) -> List[SummaryAlert]:
        """
        Runs every ayusetu.ai.clinical.document_ai.clinical_intelligence
        check over this encounter's document entities (and, where relevant,
        the patient's own reported medications/substances from dialogue)
        and turns each finding into a SummaryAlert. This is what makes
        AC-B4-1 (§23.2) hold end-to-end: a documented prescription plus a
        patient-reported herb now actually reaches the summary's alerts,
        not just the standalone clinical_intelligence functions.
        """
        reported_substances = _tokenize_reported_substances(context.slots.get("medications"))
        alerts: List[SummaryAlert] = []

        for flag in ci.flag_abnormal_values(document_entities):
            alerts.append(
                SummaryAlert(
                    category="abnormal_lab",
                    title=(
                        f"Abnormal {flag.analyte}: {flag.value} "
                        f"({flag.direction}, reference {flag.reference_low}-{flag.reference_high})"
                    ),
                )
            )

        for finding in ci.check_drug_interactions(document_entities):
            a, b = finding.substances
            alerts.append(
                SummaryAlert(
                    category="drug_interaction",
                    title=f"Drug interaction ({finding.severity}): {a} + {b} — {finding.description}",
                )
            )

        for finding in ci.check_herb_drug_interactions(document_entities, reported_substances=reported_substances):
            a, b = finding.substances
            alerts.append(
                SummaryAlert(
                    category="herb_drug_interaction",
                    title=f"Herb-drug interaction ({finding.severity}): {a} + {b} — {finding.description}",
                )
            )

        for finding in ci.detect_duplicate_therapy(document_entities):
            alerts.append(
                SummaryAlert(
                    category="duplicate_therapy",
                    title=f"Duplicate therapy ({finding.drug_class}): {', '.join(finding.medications)}",
                )
            )

        for discrepancy in ci.reconcile_medications(
            patient_reported=reported_substances, document_entities=document_entities
        ):
            side = "reported by patient, not found in documents" if discrepancy.reported_by_patient else "found in documents, not reported by patient"
            alerts.append(
                SummaryAlert(
                    category="medication_discrepancy",
                    title=f"Medication reconciliation: {discrepancy.medication} ({side})",
                )
            )

        return alerts

    def _suggest_coding(self, context) -> List[CodingCandidate]:
        candidates = []
        terms = [context.slots.get("chief_complaint")]
        med_value = context.slots.get("medications")
        if med_value:
            terms.append(med_value)

        for term in terms:
            if not term:
                continue
            resolved = gate2_resolve_terminology(term)
            if resolved is None:
                continue
            candidates.append(
                CodingCandidate(
                    system=resolved["system"],
                    code=resolved["code"],
                    display=term,
                    confidence=1.0,
                )
            )
        return candidates


def _tokenize_reported_substances(medications_slot_value: Optional[str]) -> List[str]:
    """
    The `medications` dialogue slot is free text (e.g. "Guggulu and
    Metformin 500mg"), not a list — clinical_intelligence's interaction/
    reconciliation checks need individual substance names. Splits on commas
    and "and". Trimming dose/frequency tokens (e.g. "500mg") is intentionally
    NOT attempted here — that's extraction's job, not this tokenizer's — a
    raw token like "metformin 500mg" simply won't match a curated table key
    and is harmless to pass through.
    """
    if not medications_slot_value:
        return []
    parts = re.split(r",|\band\b", medications_slot_value, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]
