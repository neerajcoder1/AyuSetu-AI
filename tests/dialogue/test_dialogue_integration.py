import pytest
from contracts.asr_output import ASROutput
from contracts.dialogue import ClinicalSlot
from contracts.extraction import ExtractionResult, ExtractedSlot
from ayusetu.ai.dialogue.engine import DialogueEngine
from ayusetu.ai.dialogue.extractor import ClinicalExtractor
from ayusetu.ai.dialogue.llm_provider import LLMProvider

class E2ETestExtractor(ClinicalExtractor):
    """Specific deterministic extractor mapping strings for the E2E integration test."""
    def extract(self, text: str) -> ExtractionResult:
        text_lower = text.lower()
        exts = []
        if "headache" in text_lower or "sir dard" in text_lower:
            exts.append(ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="Headache", confidence=0.9))
        if "2 days" in text_lower or "do din" in text_lower:
            exts.append(ExtractedSlot(slot=ClinicalSlot.DURATION, value="2 days", confidence=0.9))
        if "yesterday" in text_lower or "kal" in text_lower:
            exts.append(ExtractedSlot(slot=ClinicalSlot.ONSET, value="Yesterday", confidence=0.9))
        if "front of my head" in text_lower:
            exts.append(ExtractedSlot(slot=ClinicalSlot.LOCATION, value="Frontal", confidence=0.9))
        return ExtractionResult(extractions=exts)

class E2EMockLLM(LLMProvider):
    """
    Simulates an LLM where the wording output constantly changes.
    Used to prove the planner is completely independent of the LLM's text.
    """
    def __init__(self):
        self.call_count = 0
        
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        return f"Dynamic Wording Variation #{self.call_count}"

@pytest.fixture
def engine():
    return DialogueEngine(
        extractor=E2ETestExtractor(),
        llm_provider=E2EMockLLM(),
        asr_confidence_threshold=0.6,
        extraction_confidence_threshold=0.7
    )

def test_integration_full_dialogue_flow(engine):
    """
    End-to-end multi-turn interview simulating:
    1. Chief complaint + Duration (together)
    2. Low confidence handling
    3. Unrelated/Incomplete answers
    4. Hinglish response + Duplicate information handling
    5. LLM Independence Verification
    """
    state = engine.initialize()
    
    # Baseline checks
    assert state.missing_slots[0] == ClinicalSlot.CHIEF_COMPLAINT
    assert ClinicalSlot.DURATION in state.missing_slots
    assert ClinicalSlot.ONSET in state.missing_slots

    # ==========================================
    # TURN 1: Chief Complaint + Duration (Scenarios 1 & 2)
    # ==========================================
    asr1 = ASROutput(text="I have a headache for 2 days", language="en", confidence=0.95)
    resp1 = engine.step(asr1, state)
    
    # Both are extracted
    assert ClinicalSlot.CHIEF_COMPLAINT in state.collected_info
    assert ClinicalSlot.DURATION in state.collected_info
    
    # Explicit Verification: Duration != Onset
    assert ClinicalSlot.ONSET not in state.collected_info
    
    # Explicit Verification: Engine knows exactly which slot is next
    assert state.missing_slots[0] == ClinicalSlot.ONSET
    assert resp1 == "Dynamic Wording Variation #1"

    # ==========================================
    # TURN 2: Low ASR Confidence (Scenario 3)
    # ==========================================
    asr2 = ASROutput(text="*mumble*", language="en", confidence=0.40)
    resp2 = engine.step(asr2, state)
    
    # Explicit Verification: Low confidence does not update clinical state
    assert state.needs_clarification is True
    assert state.missing_slots[0] == ClinicalSlot.ONSET
    assert ClinicalSlot.ONSET not in state.collected_info
    assert resp2 == "Dynamic Wording Variation #2"

    # ==========================================
    # TURN 3: Unrelated / Incomplete Answer (Scenarios 6 & 7)
    # ==========================================
    asr3 = ASROutput(text="I really like apples", language="en", confidence=0.90)
    resp3 = engine.step(asr3, state)
    
    # Extractor gets nothing -> state does not advance -> repeats question
    assert state.missing_slots[0] == ClinicalSlot.ONSET
    assert resp3 == "Dynamic Wording Variation #3"

    # ==========================================
    # TURN 4: Hinglish + Duplicate Info (Scenarios 4 & 5)
    # ==========================================
    # Patient repeats "sir dard" (headache) which we already have, and adds "kal" (yesterday)
    asr4 = ASROutput(text="kal se sir dard hai", language="hinglish", confidence=0.95)
    resp4 = engine.step(asr4, state)
    
    # Explicit Verification: Duplicate info doesn't break state, Onset is added
    assert ClinicalSlot.ONSET in state.collected_info
    
    # Explicit Verification: Engine moves to Location
    assert state.missing_slots[0] == ClinicalSlot.LOCATION
    # Verifies the Wording LLM was targeted with 'hinglish'
    assert state.history[-1].language == "hinglish"
    assert resp4 == "Dynamic Wording Variation #4"

    # ==========================================
    # TURN 5: LLM Independence (Scenario 8)
    # ==========================================
    asr5 = ASROutput(text="front of my head", language="en", confidence=0.90)
    resp5 = engine.step(asr5, state)
    
    # Explicit Verification: Even though LLM wording completely changes every turn, 
    # the planner deterministically progresses.
    assert ClinicalSlot.LOCATION in state.collected_info
    assert state.missing_slots[0] == ClinicalSlot.SEVERITY
    assert resp5 == "Dynamic Wording Variation #5"
