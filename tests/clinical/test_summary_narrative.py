from ayusetu.ai.clinical.summary.gates import SourceContext
from ayusetu.ai.clinical.summary.narrative import generate_hpi_narrative, narrative_word_count


def test_generates_clause_per_present_slot_in_socrates_order():
    context = SourceContext(
        slots={
            "chief_complaint": "chest pain",
            "location": "left chest",
            "duration": "2 days",
            "severity": "8/10",
        }
    )
    clauses = generate_hpi_narrative(context)
    texts = [c.text for c in clauses]
    assert texts == [
        "Patient presents with chest pain.",
        "Located left chest.",
        "Present for 2 days.",
        "Severity reported as 8/10.",
    ]


def test_missing_slot_produces_no_clause():
    context = SourceContext(slots={"chief_complaint": "fever"})
    clauses = generate_hpi_narrative(context)
    assert len(clauses) == 1


def test_each_clause_traceable_to_exactly_its_source_slot():
    context = SourceContext(slots={"severity": "mild"})
    clauses = generate_hpi_narrative(context)
    assert clauses[0].source_slots == ["severity"]


def test_narrative_word_count_reasonable_for_full_slot_set():
    context = SourceContext(
        slots={
            "chief_complaint": "abdominal pain",
            "location": "lower right abdomen",
            "onset": "sudden",
            "duration": "1 day",
            "severity": "severe",
            "associated_symptoms": "nausea and vomiting",
            "aggravating_relieving": "worse on movement",
        }
    )
    clauses = generate_hpi_narrative(context)
    # PRD target is "roughly 80 words" for a full interview; a handful of
    # short templated clauses should land well under that.
    assert narrative_word_count(clauses) < 80
