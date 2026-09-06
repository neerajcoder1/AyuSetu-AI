import pytest
from contracts.asr_output import ASROutput
from contracts.dialogue import DialogueState, ClinicalSlot
from neeraj.dialogue.engine import DialogueEngine
from neeraj.dialogue.extractor import DeterministicPlaceholderExtractor
from neeraj.dialogue.llm_provider import LLMProvider

# 1. Provide a Mock LLM to prove independence from LLM output
class IndependenceMockLLM(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # No matter what the intent is, return gibberish
        # This proves the Planner ignores the LLM entirely.
        return "GIBBERISH_OUTPUT"

@pytest.fixture
def engine():
    # Use deterministic extractor + Mock LLM
    return DialogueEngine(
        extractor=DeterministicPlaceholderExtractor(),
        llm_provider=IndependenceMockLLM(),
        asr_confidence_threshold=0.6,
        extraction_confidence_threshold=0.7
    )

def test_planner_normal_progression(engine):
    """Test progression from CHIEF_COMPLAINT -> ONSET"""
    state = engine.initialize()
    
    assert state.missing_slots[0] == ClinicalSlot.CHIEF_COMPLAINT
    
    # User provides chief complaint
    asr = ASROutput(text="मुझे पेट में दर्द है", language="hi", confidence=0.9)
    response = engine.step(asr, state)
    
    # LLM outputs gibberish, but state machine must advance
    assert response == "GIBBERISH_OUTPUT"
    
    # State should now reflect CHIEF_COMPLAINT is collected
    assert ClinicalSlot.CHIEF_COMPLAINT in state.collected_info
    assert ClinicalSlot.CHIEF_COMPLAINT not in state.missing_slots
    
    # Next slot should now be ONSET
    assert state.missing_slots[0] == ClinicalSlot.ONSET

def test_low_confidence_trigger(engine):
    """Low confidence should trigger clarification, skipping extraction."""
    state = engine.initialize()
    
    # High confidence chief complaint
    asr = ASROutput(text="मुझे पेट में दर्द है", language="hi", confidence=0.9)
    engine.step(asr, state)
    
    assert ClinicalSlot.CHIEF_COMPLAINT in state.collected_info
    assert state.missing_slots[0] == ClinicalSlot.ONSET
    
    # Low confidence answer for ONSET
    asr_low = ASROutput(text="mumble mumble", language="en", confidence=0.4)
    engine.step(asr_low, state)
    
    # State should flag needs_clarification
    assert state.needs_clarification is True
    # Missing slots should NOT have advanced
    assert state.missing_slots[0] == ClinicalSlot.ONSET

def test_duplicate_information(engine):
    """If patient gives multiple slots at once, skip those questions."""
    state = engine.initialize()
    
    # User provides BOTH chief complaint and duration in one go
    # "मुझे दो दिन से पेट में दर्द है" triggers both CHIEF_COMPLAINT and DURATION in the PlaceholderExtractor
    asr = ASROutput(text="मुझे दो दिन से पेट में दर्द है", language="hi", confidence=0.9)
    engine.step(asr, state)
    
    assert ClinicalSlot.CHIEF_COMPLAINT in state.collected_info
    assert ClinicalSlot.DURATION in state.collected_info
    
    assert ClinicalSlot.CHIEF_COMPLAINT not in state.missing_slots
    assert ClinicalSlot.DURATION not in state.missing_slots
    
    # Next slot should be ONSET (since it wasn't collected yet, but duration was skipped!)
    assert state.missing_slots[0] == ClinicalSlot.ONSET
    
    # Let's say user gives ONSET
    asr2 = ASROutput(text="kal se", language="hi", confidence=0.9)
    # Actually PlaceholderExtractor doesn't extract onset in our mock rules yet.
    # So if it fails to extract, missing_slots[0] stays ONSET.
    engine.step(asr2, state)
    assert state.missing_slots[0] == ClinicalSlot.ONSET

def test_independence_llm_cannot_change_sequence(engine):
    """
    Ensure the LLM returning random data has zero effect on the sequence.
    This fulfills requirement #4 and #6.
    """
    state = engine.initialize()
    
    # No matter what LLM returned, the first question intent from planner is for Chief Complaint.
    # After user answers, it extracts.
    asr = ASROutput(text="I have a stomach pain", language="en", confidence=0.9)
    engine.step(asr, state)
    
    assert ClinicalSlot.CHIEF_COMPLAINT in state.collected_info
    # DURATION is NOT extracted by "stomach pain" alone.
    assert ClinicalSlot.DURATION not in state.collected_info
    
    assert state.missing_slots[0] == ClinicalSlot.ONSET

def test_missing_information(engine):
    """If extraction yields nothing, planner asks the same slot again."""
    state = engine.initialize()
    
    # Empty string or irrelevant string
    asr = ASROutput(text="hello doctor", language="en", confidence=0.9)
    engine.step(asr, state)
    
    # Chief complaint is still missing
    assert ClinicalSlot.CHIEF_COMPLAINT not in state.collected_info
    assert state.missing_slots[0] == ClinicalSlot.CHIEF_COMPLAINT
