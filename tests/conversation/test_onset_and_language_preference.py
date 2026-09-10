import pytest
from contracts.asr_output import ASROutput
from contracts.dialogue import ClinicalSlot, DialogueState
from ayusetu.ai.conversation.engine import DialogueEngine
from ayusetu.ai.conversation.extractor import DeterministicRuleExtractor
from ayusetu.ai.conversation.wording import WordingLLM
from ayusetu.ai.voice.pipeline.voice_pipeline import VoicePipeline

class MockWordingProvider:
    def __init__(self):
        self.last_user_prompt = ""
        self.last_system_prompt = ""

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return "Mocked AI Response"

def test_onset_extraction_hindi():
    extractor = DeterministicRuleExtractor()
    text = "तीन दिन पहले शुरू हुआ"
    result = extractor.extract(text)
    slots = {e.slot: e.value for e in result.extractions}
    assert ClinicalSlot.ONSET in slots, "Hindi onset was not extracted"
    assert "तीन दिन पहले" in slots[ClinicalSlot.ONSET] or "3 days ago" in slots[ClinicalSlot.ONSET] or "day" in slots[ClinicalSlot.ONSET]

def test_onset_extraction_hinglish():
    extractor = DeterministicRuleExtractor()
    text = "Teen din pehle shuru hui hai yeh lakshan."
    result = extractor.extract(text)
    slots = {e.slot: e.value for e in result.extractions}
    assert ClinicalSlot.ONSET in slots, "Hinglish onset was not extracted"
    assert "Teen din pehle" in slots[ClinicalSlot.ONSET]

def test_onset_extraction_english():
    extractor = DeterministicRuleExtractor()
    text = "3 days ago it started."
    result = extractor.extract(text)
    slots = {e.slot: e.value for e in result.extractions}
    assert ClinicalSlot.ONSET in slots, "English onset was not extracted"
    assert "3 days ago" in slots[ClinicalSlot.ONSET]

def test_planner_no_duplicate_onset_question():
    provider = MockWordingProvider()
    engine = DialogueEngine(
        extractor=DeterministicRuleExtractor(),
        llm_provider=provider,
    )
    state = engine.initialize()

    # Turn 1: Chief Complaint
    asr1 = ASROutput(text="I have stomach pain", language="en", confidence=0.95)
    engine.step(asr1, state)
    assert state.missing_slots[0] == ClinicalSlot.ONSET

    # Turn 2: Patient gives onset response in Hinglish
    asr2 = ASROutput(text="Teen din pehle shuru hui hai yeh lakshan.", language="hinglish", confidence=0.95)
    engine.step(asr2, state)

    # Verify ONSET is now collected and missing_slots advanced past ONSET
    assert ClinicalSlot.ONSET in state.collected_info
    assert state.missing_slots[0] != ClinicalSlot.ONSET

def test_session_preferred_language_scoping():
    provider = MockWordingProvider()
    engine = DialogueEngine(
        extractor=DeterministicRuleExtractor(),
        llm_provider=provider,
    )
    state = engine.initialize()
    state.preferred_language = "hi"

    # Patient speaks in English script ("I have fever"), but preferred language is Hindi
    asr = ASROutput(text="I have fever", language="en", confidence=0.95)
    engine.step(asr, state)

    # Wording prompt must request Hindi
    assert "Requested Language: hi" in provider.last_user_prompt
    assert state.history[-1].language == "hi"

def test_session_isolation_and_language():
    pipeline = VoicePipeline()

    # Session 1: Hindi preference
    s1_id = pipeline.create_session(preferred_language="hi")
    state1 = pipeline.get_state(s1_id)

    # Session 2: English preference
    s2_id = pipeline.create_session(preferred_language="en")
    state2 = pipeline.get_state(s2_id)

    assert state1.preferred_language == "hi"
    assert state2.preferred_language == "en"

    # Isolation check: mutating state1 does not affect state2
    state1.collected_info[ClinicalSlot.CHIEF_COMPLAINT] = "fever"
    assert ClinicalSlot.CHIEF_COMPLAINT not in state2.collected_info
