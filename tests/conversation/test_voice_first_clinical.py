import pytest
from contracts.asr_output import ASROutput
from contracts.dialogue import ClinicalSlot
from ayusetu.ai.conversation.engine import DialogueEngine
from ayusetu.ai.conversation.llm_provider import OpenAICompatibleProvider

class DummyLLM(OpenAICompatibleProvider):
    def generate(self, sys, user):
        return "" # returning empty forces the fallback

def test_body_map_opening():
    engine = DialogueEngine(llm_provider=DummyLLM())
    state = engine.initialize(body_map_location="Abdomen")
    opening = engine.generate_opening(state)
    assert "पेट" in opening
    assert state.body_map_location == "Abdomen"

def test_body_map_merging():
    engine = DialogueEngine(llm_provider=DummyLLM())
    state = engine.initialize(body_map_location="Chest")

    # Patient just says "I have pain for 2 days" without saying chest
    asr = ASROutput(text="do din se", language="hi", confidence=0.95)
    engine.step(asr, state)

    assert ClinicalSlot.LOCATION in state.collected_info
    assert state.collected_info[ClinicalSlot.LOCATION] == "Chest"

def test_duration_extraction():
    engine = DialogueEngine(llm_provider=DummyLLM())
    state = engine.initialize()
    asr = ASROutput(text="do din se", language="hi", confidence=0.95)
    engine.step(asr, state)
    assert state.collected_info.get(ClinicalSlot.DURATION) == "2 day(s)"

def test_severity_extraction():
    engine = DialogueEngine(llm_provider=DummyLLM())
    state = engine.initialize()
    asr = ASROutput(text="bahut tez dard hai", language="hi", confidence=0.95)
    engine.step(asr, state)
    assert state.collected_info.get(ClinicalSlot.SEVERITY) == "very severe"

def test_associated_symptoms_no():
    engine = DialogueEngine(llm_provider=DummyLLM())
    state = engine.initialize()
    # Mock planner so we are asking about associated symptoms
    state.missing_slots = [ClinicalSlot.ASSOCIATED_SYMPTOMS]

    asr = ASROutput(text="no", language="en", confidence=0.95)
    engine.step(asr, state)

    assert state.collected_info.get(ClinicalSlot.ASSOCIATED_SYMPTOMS) == "none"

def test_empty_ai_response_fallback():
    engine = DialogueEngine(llm_provider=DummyLLM())
    state = engine.initialize()
    state.missing_slots = [ClinicalSlot.CHIEF_COMPLAINT]

    asr = ASROutput(text="um", language="en", confidence=0.95)
    response = engine.step(asr, state)
    assert response == "आपको क्या समस्या हो रही है?"
