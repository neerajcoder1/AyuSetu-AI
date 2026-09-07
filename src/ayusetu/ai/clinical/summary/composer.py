"""
SummaryGenerator: orchestrates the five gates into one ClinicalSummary
(PRD §13.2 structure), starting life as status=PRELIMINARY per §13.3
("Nothing enters the record unsigned").
"""

from typing import Dict, List, Optional

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

        # Alerts, from the red-flag engine's output for this encounter
        alerts = [
            SummaryAlert(
                tier=int(event.tier),
                title=event.title,
                acknowledged=event.acknowledged_at is not None,
            )
            for event in (red_flag_events or [])
        ]

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
