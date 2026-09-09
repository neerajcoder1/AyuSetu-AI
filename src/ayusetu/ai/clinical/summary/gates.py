"""
Five gates between the model and the medical record (PRD §13.1, Figure 6).

The PRD text explicitly names three of the five by function:
  - Gate 2: closed-vocabulary terminology resolution — "a drug name that
    does not resolve is surfaced as unverified text, never as a coded
    medication" (§13.1, §21.7).
  - Gate 4: the entailment verifier — "content that does not entail from
    source slots is dropped" (§13.1, §21.7).
  - Gate 5: the elicited/not-elicited distinction — "there is no
    representation for a silently assumed negative" (§13.1, §22.3).

Figure 6 itself (the gate diagram) is not text-extractable from the PRD, so
Gates 1 and 3 below are an architectural reconstruction consistent with
everything the PRD says explicitly about the pipeline (§13.1 "why prompting
is not an answer", §21.7 security controls: data/instruction separation and
constrained output schema). If the actual Figure 6 labels differ, only the
docstrings here need correcting — the gates already do the right job:

  Gate 1 — Source grounding / data-instruction separation: the generator
           only ever receives a closed, structured context (slots +
           resolved entities), never raw free text as an instruction
           channel (mirrors §21.7's OCR "data / instruction separation").
  Gate 2 — Closed vocabulary (explicit in PRD).
  Gate 3 — Constrained output schema: generation can only populate fields
           that exist on ClinicalSummary; nothing else has anywhere to go
           (mirrors §21.7 "Extraction returns a fixed JSON Schema").
  Gate 4 — Entailment verification (explicit in PRD).
  Gate 5 — Elicited/not-elicited distinction (explicit in PRD).

Each gate is a plain function so it can be unit-tested — and, per the PRD's
own CI guardrail (§16, "gate behaviour has its own tests that assert
rejection... a change that reduces gate rejections below the fixture
baseline fails the build") — asserted to actually reject bad input.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ayusetu.ai.clinical.summary.contracts import NarrativeClause, StructuredField


@dataclass
class SourceContext:
    """
    Gate 1 output: the ONLY thing the narrative generator is allowed to see.
    Building this object IS the gate — there is no code path from raw
    transcript text into the summary that skips it.
    """

    slots: Dict[str, str] = field(default_factory=dict)
    missing_slots: List[str] = field(default_factory=list)


def gate1_build_source_context(collected_info: Dict, missing_slots: List) -> SourceContext:
    """Collapses ClinicalSlot-keyed dicts/enums to plain strings so nothing
    downstream can accidentally treat a slot key as free text to interpret."""
    slots = {
        (k.value if hasattr(k, "value") else str(k)): str(v) for k, v in collected_info.items()
    }
    missing = [s.value if hasattr(s, "value") else str(s) for s in missing_slots]
    return SourceContext(slots=slots, missing_slots=missing)


# ── Gate 2: closed vocabulary ────────────────────────────────────────────────

# Starter terminology table. In deployment this is the terminology service
# (§22.2, service 8106) — swap this dict for a real $lookup/$translate call.
_KNOWN_VOCABULARY = {
    "metformin": ("RxNorm", "6809"),
    "amlodipine": ("RxNorm", "17767"),
    "paracetamol": ("RxNorm", "161"),
    "hypertension": ("ICD-11", "BA00"),
    "diabetes mellitus": ("ICD-11", "5A11"),
}


def gate2_resolve_terminology(raw_text: str) -> Optional[Dict[str, str]]:
    """
    Returns {"system": ..., "code": ...} if raw_text resolves against the
    closed vocabulary, else None. A None result means the caller must
    surface raw_text as unverified text — there is no coded-medication
    field a None can be forced into (that's what makes this a gate and not
    a suggestion).
    """
    match = _KNOWN_VOCABULARY.get(raw_text.strip().lower())
    if match is None:
        return None
    system, code = match
    return {"system": system, "code": code}


# ── Gate 3: constrained output schema ────────────────────────────────────────


def gate3_constrain_to_schema(candidate_fields: Dict[str, object], allowed_fields: set) -> Dict[str, object]:
    """
    Drops any key not in `allowed_fields`. This is what "there is no field a
    model can populate with an invented drug name" means in code: the field
    simply doesn't exist on the far side of this call.
    """
    return {k: v for k, v in candidate_fields.items() if k in allowed_fields}


# ── Gate 4: entailment verification ──────────────────────────────────────────


def gate4_verify_entailment(clause: NarrativeClause, context: SourceContext, min_overlap: float = 0.3) -> bool:
    """
    A clause entails from its cited source slots if its content is
    substantially built from those slots' actual values — not a
    sophisticated NLI model, but a real rejection rule: a clause citing
    slots it doesn't overlap with, or citing no slots at all, is dropped
    exactly like the PRD describes ("content that does not entail from
    source slots is dropped").
    """
    if not clause.source_slots:
        return False

    cited_values = " ".join(context.slots.get(s, "") for s in clause.source_slots).lower()
    if not cited_values.strip():
        return False

    clause_words = {w.strip(".,!?;:") for w in clause.text.lower().split()}
    source_words = {w.strip(".,!?;:") for w in cited_values.split()}
    if not clause_words:
        return False

    overlap = len(clause_words & source_words) / len(clause_words)
    return overlap >= min_overlap


def filter_entailed_clauses(clauses: List[NarrativeClause], context: SourceContext) -> List[NarrativeClause]:
    kept = []
    for clause in clauses:
        clause.entailed = gate4_verify_entailment(clause, context)
        if clause.entailed:
            kept.append(clause)
    return kept


# ── Gate 5: elicited / not-elicited distinction ──────────────────────────────


def gate5_render_field(label: str, context: SourceContext, slot_path: str) -> StructuredField:
    """
    A slot in `missing_slots` renders as explicitly "not elicited"
    (elicited=False), never as an absent/negative value. A slot with no
    value that is ALSO not in missing_slots is a data-modelling bug
    upstream, not something this gate silently papers over — it still
    renders not-elicited rather than guessing, but that combination should
    not occur if callers build SourceContext correctly.
    """
    if slot_path in context.missing_slots:
        return StructuredField(label=label, value=None, elicited=False)
    value = context.slots.get(slot_path)
    return StructuredField(label=label, value=value, elicited=value is not None)
