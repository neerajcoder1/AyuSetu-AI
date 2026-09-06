import pytest
from contracts.asr_output import ASROutput
from contracts.dialogue import ClinicalSlot
from contracts.extraction import ExtractionResult, ExtractedSlot
from ayusetu.ai.dialogue.planner import DialoguePlanner

@pytest.fixture
def planner():
    return DialoguePlanner(asr_confidence_threshold=0.6, extraction_confidence_threshold=0.7)

def test_planner_low_extraction_confidence_ignored(planner):
    """Extraction confidence below threshold is ignored and does not update state."""
    state = planner.initialize_state()
    
    asr = ASROutput(text="maybe I have fever", language="en", confidence=0.9)
    # Extractor returns fever but with very low extraction confidence
    ext_result = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.ASSOCIATED_SYMPTOMS, value="fever", confidence=0.4)
    ])
    
    planner.plan_next_action(asr, state, ext_result)
    
    # State should remain completely unmodified
    assert ClinicalSlot.ASSOCIATED_SYMPTOMS not in state.collected_info
    assert ClinicalSlot.ASSOCIATED_SYMPTOMS in state.missing_slots

def test_planner_multiple_slots_extracted(planner):
    """Multiple slots are extracted correctly."""
    state = planner.initialize_state()
    
    asr = ASROutput(text="headache for 2 days", language="en", confidence=0.9)
    ext_result = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="headache", confidence=0.95),
        ExtractedSlot(slot=ClinicalSlot.DURATION, value="2 days", confidence=0.90)
    ])
    
    planner.plan_next_action(asr, state, ext_result)
    
    assert state.collected_info[ClinicalSlot.CHIEF_COMPLAINT] == "headache"
    assert state.collected_info[ClinicalSlot.DURATION] == "2 days"
    assert ClinicalSlot.CHIEF_COMPLAINT not in state.missing_slots
    assert ClinicalSlot.DURATION not in state.missing_slots

def test_planner_repeated_identical_extraction(planner):
    """If the exact same slot+value is extracted again, state remains unchanged and no correction logged."""
    state = planner.initialize_state()
    
    # First turn
    asr = ASROutput(text="headache", language="en", confidence=0.9)
    ext = ExtractionResult(extractions=[ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="headache", confidence=0.95)])
    planner.plan_next_action(asr, state, ext)
    
    assert state.collected_info[ClinicalSlot.CHIEF_COMPLAINT] == "headache"
    assert len(state.corrections) == 0
    
    # Second turn (identical)
    planner.plan_next_action(asr, state, ext)
    assert state.collected_info[ClinicalSlot.CHIEF_COMPLAINT] == "headache"
    assert len(state.corrections) == 0

def test_planner_already_known_slot_overwritten(planner):
    """If a slot is already known, a high-confidence extraction should overwrite it and log a correction."""
    state = planner.initialize_state()
    
    # First turn sets it
    asr1 = ASROutput(text="stomach ache", language="en", confidence=0.9)
    ext_result1 = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="stomach ache", confidence=0.95)
    ])
    planner.plan_next_action(asr1, state, ext_result1)
    
    assert state.collected_info[ClinicalSlot.CHIEF_COMPLAINT] == "stomach ache"
    
    # Second turn overrides it
    asr2 = ASROutput(text="no actually it is back pain", language="en", confidence=0.9)
    ext_result2 = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="back pain", confidence=0.95)
    ])
    planner.plan_next_action(asr2, state, ext_result2)
    
    # Active value is updated
    assert state.collected_info[ClinicalSlot.CHIEF_COMPLAINT] == "back pain"
    
    # Correction is logged!
    assert len(state.corrections) == 1
    corr = state.corrections[0]
    assert corr.slot == ClinicalSlot.CHIEF_COMPLAINT
    assert corr.previous_value == "stomach ache"
    assert corr.updated_value == "back pain"
    assert corr.update_reason == "patient_correction"

def test_planner_low_confidence_correction_ignored(planner):
    """A low-confidence extraction does not overwrite an existing known slot."""
    state = planner.initialize_state()
    
    # First turn sets it (high confidence)
    asr1 = ASROutput(text="stomach ache", language="en", confidence=0.9)
    ext_result1 = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="stomach ache", confidence=0.95)
    ])
    planner.plan_next_action(asr1, state, ext_result1)
    
    # Second turn tries to correct it with low extraction confidence (e.g. 0.4)
    asr2 = ASROutput(text="back pain maybe", language="en", confidence=0.9)
    ext_result2 = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="back pain", confidence=0.4)
    ])
    planner.plan_next_action(asr2, state, ext_result2)
    
    # Active value remains unchanged
    assert state.collected_info[ClinicalSlot.CHIEF_COMPLAINT] == "stomach ache"
    assert len(state.corrections) == 0

def test_planner_no_clinical_info(planner):
    """If no clinical information is extracted, state remains unchanged."""
    state = planner.initialize_state()
    
    asr = ASROutput(text="hello doctor", language="en", confidence=0.9)
    ext_result = ExtractionResult(extractions=[])
    
    action = planner.plan_next_action(asr, state, ext_result)
    
    # State unmodified
    assert len(state.collected_info) == 0
    assert state.missing_slots[0] == ClinicalSlot.CHIEF_COMPLAINT
    # Action intent continues to prompt for chief complaint
    assert action.next_slot == ClinicalSlot.CHIEF_COMPLAINT

def test_asr_confidence_low_bypasses_extraction(planner):
    """If ASR confidence is low, extraction results shouldn't even be processed by the planner."""
    state = planner.initialize_state()
    
    asr = ASROutput(text="*mumble*", language="en", confidence=0.3) # Low ASR conf
    # Even if an extractor hallucinates data
    ext_result = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="hallucination", confidence=0.99)
    ])
    
    action = planner.plan_next_action(asr, state, ext_result)
    
    assert action.needs_clarification is True
    assert ClinicalSlot.CHIEF_COMPLAINT not in state.collected_info
