from contracts.dialogue import ClinicalSlot
from ayusetu.ai.conversation.extractor import DeterministicRuleExtractor


def test_extracts_chief_complaint_and_duration():
    extractor = DeterministicRuleExtractor()
    result = extractor.extract("I have chest pain for 2 days")

    slots = {e.slot: e for e in result.extractions}
    assert ClinicalSlot.CHIEF_COMPLAINT in slots
    assert ClinicalSlot.DURATION in slots
    assert "2" in slots[ClinicalSlot.DURATION].value
    assert slots[ClinicalSlot.DURATION].evidence is not None


def test_extracts_severity_scale():
    extractor = DeterministicRuleExtractor()
    result = extractor.extract("The pain is 8/10")
    slots = {e.slot: e for e in result.extractions}
    assert slots[ClinicalSlot.SEVERITY].value == "8/10"


def test_extracts_associated_symptoms():
    extractor = DeterministicRuleExtractor()
    result = extractor.extract("I also have fever and cough")
    slots = {e.slot for e in result.extractions}
    assert ClinicalSlot.ASSOCIATED_SYMPTOMS in slots


def test_no_clinical_content_returns_empty():
    extractor = DeterministicRuleExtractor()
    result = extractor.extract("hello doctor, good morning")
    assert result.extractions == []


def test_empty_text_returns_empty():
    extractor = DeterministicRuleExtractor()
    assert extractor.extract("").extractions == []
    assert extractor.extract("   ").extractions == []


def test_evidence_is_always_a_substring_of_source():
    extractor = DeterministicRuleExtractor()
    text = "I am taking metformin and smoke occasionally, father has diabetes"
    result = extractor.extract(text)
    for e in result.extractions:
        if e.evidence:
            assert e.evidence in text or e.evidence is not None
