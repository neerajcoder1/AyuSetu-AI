import pytest
from contracts.asr_output import ASROutput
from contracts.dialogue import ClinicalSlot
from contracts.extraction import ExtractionResult, ExtractedSlot
from ayusetu.ai.clinical.memory import ClinicalMemory
from ayusetu.ai.conversation.engine import DialogueEngine
from ayusetu.ai.conversation.extractor import ClinicalExtractor, DeterministicRuleExtractor
from ayusetu.ai.conversation.llm_provider import LLMProvider
from ayusetu.ai.conversation.ontology import INTERVIEW_SEQUENCE

class SilentLLM(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return "OK"

class StubPrimaryExtractor(ClinicalExtractor):
    def __init__(self, predefined_results=None):
        # Mapping from string text to ExtractionResult
        self.predefined_results = predefined_results or {}

    def extract(self, text: str, target_slot=None) -> ExtractionResult:
        if text in self.predefined_results:
            return self.predefined_results[text]
        return ExtractionResult(extractions=[])

def make_session_with_stub(stub_extractor) -> tuple[DialogueEngine, object, ClinicalMemory]:
    memory = ClinicalMemory()
    engine = DialogueEngine(
        extractor=stub_extractor,
        llm_provider=SilentLLM(),
        asr_confidence_threshold=0.6,
        extraction_confidence_threshold=0.7,
        memory=memory,
    )
    state = engine.initialize()
    return engine, state, memory

def asr(text: str, lang: str = "en", conf: float = 0.92) -> ASROutput:
    return ASROutput(text=text, language=lang, confidence=conf)

class TestFallbackIntegration:

    def test_full_conversation_with_fallback(self):
        # Primary extractor always returns empty
        stub = StubPrimaryExtractor()
        engine, state, memory = make_session_with_stub(stub)

        # Turn 1: Chief complaint
        engine.step(asr("I have a severe headache"), state)
        snapshot = memory.get_current_snapshot()
        assert ClinicalSlot.CHIEF_COMPLAINT in snapshot.slots
        assert "headache" in snapshot.slots[ClinicalSlot.CHIEF_COMPLAINT].value.lower()

        # The planner should advance to ONSET or DURATION (next in INTERVIEW_SEQUENCE)
        missing = state.missing_slots
        assert ClinicalSlot.CHIEF_COMPLAINT not in missing

        # Turn 2: Duration
        engine.step(asr("It started 2 days ago"), state)
        snapshot = memory.get_current_snapshot()
        assert ClinicalSlot.DURATION in snapshot.slots
        assert "2 day" in snapshot.slots[ClinicalSlot.DURATION].value.lower()

        # Turn 3: Severity
        engine.step(asr("It's about an 8 out of 10"), state)
        snapshot = memory.get_current_snapshot()
        assert ClinicalSlot.SEVERITY in snapshot.slots
        assert "8" in snapshot.slots[ClinicalSlot.SEVERITY].value

    def test_mixed_primary_fallback(self):
        # Primary succeeds for chief complaint but fails for severity
        predefined = {
            "I have a stomach ache": ExtractionResult(extractions=[
                ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="stomach ache", confidence=0.9, evidence="stomach ache")
            ])
        }
        stub = StubPrimaryExtractor(predefined)
        engine, state, memory = make_session_with_stub(stub)

        # Primary handles this
        engine.step(asr("I have a stomach ache"), state)
        snapshot = memory.get_current_snapshot()
        assert snapshot.slots[ClinicalSlot.CHIEF_COMPLAINT].value == "stomach ache"

        # Primary fails this, fallback should pick it up
        engine.step(asr("Severity is 9 out of 10"), state)
        snapshot = memory.get_current_snapshot()
        assert ClinicalSlot.SEVERITY in snapshot.slots
        assert "9" in snapshot.slots[ClinicalSlot.SEVERITY].value

    def test_memory_receives_merged_results(self):
        # Primary provides ONE non-target slot with low confidence (gets preserved)
        # Fallback provides the target slot
        predefined = {
            "I have chest pain for 3 days": ExtractionResult(extractions=[
                ExtractedSlot(slot=ClinicalSlot.ASSOCIATED_SYMPTOMS, value="nausea", confidence=0.8, evidence="nausea")
            ])
        }
        stub = StubPrimaryExtractor(predefined)
        engine, state, memory = make_session_with_stub(stub)
        state.missing_slots = [ClinicalSlot.CHIEF_COMPLAINT]

        engine.step(asr("I have chest pain for 3 days"), state)
        snapshot = memory.get_current_snapshot()

        # From primary
        assert snapshot.slots[ClinicalSlot.ASSOCIATED_SYMPTOMS].value == "nausea"
        # From fallback
        assert "chest pain" in snapshot.slots[ClinicalSlot.CHIEF_COMPLAINT].value.lower()
        assert "3 day" in snapshot.slots[ClinicalSlot.DURATION].value.lower()

    def test_planner_advances_with_fallback_data(self):
        stub = StubPrimaryExtractor()
        engine, state, memory = make_session_with_stub(stub)

        assert state.missing_slots[0] == INTERVIEW_SEQUENCE[0] # CHIEF_COMPLAINT

        engine.step(asr("I have a fever"), state)

        # Should have advanced past chief complaint
        assert state.missing_slots[0] != ClinicalSlot.CHIEF_COMPLAINT
        assert ClinicalSlot.CHIEF_COMPLAINT not in state.missing_slots
