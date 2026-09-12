from ayusetu.ai.clinical.summary.contracts import NarrativeClause
from ayusetu.ai.clinical.summary.gates import (
    SourceContext,
    gate1_build_source_context,
    gate2_resolve_terminology,
    gate3_constrain_to_schema,
    gate4_verify_entailment,
    gate5_render_field,
)


def test_gate1_collapses_enum_keys_to_plain_strings():
    class FakeSlot:
        value = "chief_complaint"

    context = gate1_build_source_context({FakeSlot(): "chest pain"}, [FakeSlot()])
    assert context.slots == {"chief_complaint": "chest pain"}
    assert context.missing_slots == ["chief_complaint"]


def test_gate2_resolves_known_term():
    result = gate2_resolve_terminology("Metformin")
    assert result == {"system": "RxNorm", "code": "6809"}


def test_gate2_returns_none_for_unknown_term_never_invents_a_code():
    assert gate2_resolve_terminology("SomeMadeUpDrugName") is None


def test_gate3_drops_fields_outside_allowed_set():
    candidate = {"chief_complaint": "fever", "injected_field": "malicious"}
    result = gate3_constrain_to_schema(candidate, allowed_fields={"chief_complaint"})
    assert result == {"chief_complaint": "fever"}


def test_gate4_accepts_clause_entailed_by_its_source_slot():
    context = SourceContext(slots={"duration": "2 days"})
    clause = NarrativeClause(text="Present for 2 days.", source_slots=["duration"])
    assert gate4_verify_entailment(clause, context) is True


def test_gate4_rejects_clause_with_no_source_slots():
    context = SourceContext(slots={"duration": "2 days"})
    clause = NarrativeClause(text="Patient has terminal cancer.", source_slots=[])
    assert gate4_verify_entailment(clause, context) is False


def test_gate4_rejects_fabricated_clause_not_derived_from_cited_slot():
    context = SourceContext(slots={"duration": "2 days"})
    # Claims to cite "duration" but the text has nothing to do with it —
    # simulates a hallucinated clause smuggled in with a fake citation.
    clause = NarrativeClause(text="Patient reports severe chest pain radiating to the jaw", source_slots=["duration"])
    assert gate4_verify_entailment(clause, context) is False


def test_gate5_missing_slot_renders_not_elicited_never_a_negative():
    context = SourceContext(slots={}, missing_slots=["allergies"])
    field = gate5_render_field("Allergies", context, "allergies")
    assert field.elicited is False
    assert field.display_value == "not elicited"


def test_gate5_present_slot_renders_its_value():
    context = SourceContext(slots={"allergies": "penicillin"}, missing_slots=[])
    field = gate5_render_field("Allergies", context, "allergies")
    assert field.elicited is True
    assert field.display_value == "penicillin"
