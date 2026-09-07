from contracts.dialogue import ClinicalSlot
from ayusetu.ai.clinical.extraction.rule_extractor import RuleBasedClinicalExtractor


def test_extracts_chief_complaint_and_duration():
    extractor = RuleBasedClinicalExtractor()
    result = extractor.extract("I have chest pain for 2 days")

    slots = {e.slot: e for e in result.extractions}
    assert ClinicalSlot.CHIEF_COMPLAINT in slots
    assert ClinicalSlot.DURATION in slots
    assert slots[ClinicalSlot.DURATION].value == "2 days"
    assert slots[ClinicalSlot.DURATION].evidence in "I have chest pain for 2 days"


def test_extracts_severity_scale():
    extractor = RuleBasedClinicalExtractor()
    result = extractor.extract("The pain is 8/10")
    slots = {e.slot: e for e in result.extractions}
    assert slots[ClinicalSlot.SEVERITY].value == "8/10"


def test_extracts_associated_symptoms():
    extractor = RuleBasedClinicalExtractor()
    result = extractor.extract("I also have fever and cough")
    slots = {e.slot for e in result.extractions}
    assert ClinicalSlot.ASSOCIATED_SYMPTOMS in slots


def test_no_clinical_content_returns_empty():
    extractor = RuleBasedClinicalExtractor()
    result = extractor.extract("hello doctor, good morning")
    assert result.extractions == []


def test_empty_text_returns_empty():
    extractor = RuleBasedClinicalExtractor()
    assert extractor.extract("").extractions == []
    assert extractor.extract("   ").extractions == []


def test_evidence_is_always_a_substring_of_source():
    extractor = RuleBasedClinicalExtractor()
    text = "I am taking metformin 500 mg and smoke occasionally, father has diabetes"
    result = extractor.extract(text)
    for e in result.extractions:
        if e.evidence:
            assert e.evidence in text
