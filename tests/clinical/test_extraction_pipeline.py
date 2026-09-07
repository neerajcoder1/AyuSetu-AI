from contracts.dialogue import ClinicalSlot, DialogueTurn
from contracts.asr_output import ASROutput
from ayusetu.ai.clinical.extraction.rule_extractor import RuleBasedClinicalExtractor
from ayusetu.ai.clinical.extraction.pipeline import ClinicalExtractionPipeline


def test_aggregates_across_turns_keeping_highest_confidence():
    pipeline = ClinicalExtractionPipeline(RuleBasedClinicalExtractor())
    turns = [
        DialogueTurn(speaker="patient", text="pain is mild", language="en", confidence=0.9),
        DialogueTurn(speaker="system", text="how severe?", language="en", confidence=None),
        DialogueTurn(speaker="patient", text="pain is 9/10", language="en", confidence=0.9),
    ]

    result = pipeline.extract_from_turns(turns)
    slots = {e.slot: e for e in result.extractions}
    # "9/10" match has confidence 0.9, "mild" has confidence 0.75 -> keep the numeric one
    assert slots[ClinicalSlot.SEVERITY].value == "9/10"


def test_low_asr_confidence_turns_are_skipped():
    pipeline = ClinicalExtractionPipeline(RuleBasedClinicalExtractor(), min_asr_confidence=0.6)
    turns = [
        DialogueTurn(speaker="patient", text="chest pain", language="en", confidence=0.2),
    ]
    result = pipeline.extract_from_turns(turns)
    assert result.extractions == []


def test_extract_from_asr_stream():
    pipeline = ClinicalExtractionPipeline(RuleBasedClinicalExtractor())
    utterances = [ASROutput(text="fever and cough", language="en", confidence=0.9)]
    result = pipeline.extract_from_asr_stream(utterances)
    slots = {e.slot for e in result.extractions}
    assert ClinicalSlot.ASSOCIATED_SYMPTOMS in slots
