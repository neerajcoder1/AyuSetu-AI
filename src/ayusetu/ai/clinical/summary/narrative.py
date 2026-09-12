"""
SOCRATES-structured history-of-present-illness narrative (PRD §13.2:
"History of present illness — SOCRATES-structured narrative, roughly 80
words, every clause hoverable to reveal its source").

Each clause is built from exactly one source slot's value with a fixed
template — never free generation — so Gate 4 (entailment) has something
real to check, and so hover-to-source is exact rather than approximate.

SOCRATES = Site, Onset, Character, Radiation, Associations, Time course,
Exacerbating/relieving factors, Severity. Character and Radiation aren't
covered by the current ClinicalSlot set (contracts/dialogue.py) and are
skipped rather than fabricated — once those slots exist in the dialogue
ontology, add their template lines here.
"""

from typing import Dict, List

from ayusetu.ai.clinical.summary.contracts import NarrativeClause
from ayusetu.ai.clinical.summary.gates import SourceContext

# (slot_path, template) in SOCRATES order. `{value}` is substituted verbatim
# from the source slot — this is what keeps the clause entailed by
# construction, not just by luck.
_SOCRATES_TEMPLATES = [
    ("chief_complaint", "Patient presents with {value}."),
    ("location", "Located {value}."),
    ("onset", "Onset {value}."),
    ("duration", "Present for {value}."),
    ("severity", "Severity reported as {value}."),
    ("associated_symptoms", "Associated with {value}."),
    ("aggravating_relieving", "Aggravating/relieving factors: {value}."),
]


def generate_hpi_narrative(context: SourceContext) -> List[NarrativeClause]:
    clauses = []
    for slot_path, template in _SOCRATES_TEMPLATES:
        value = context.slots.get(slot_path)
        if not value:
            continue
        clauses.append(
            NarrativeClause(
                text=template.format(value=value),
                source_slots=[slot_path],
            )
        )
    return clauses


def narrative_word_count(clauses: List[NarrativeClause]) -> int:
    return sum(len(c.text.split()) for c in clauses)
