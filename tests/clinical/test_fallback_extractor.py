import pytest
from contracts.asr_output import ASROutput
from contracts.dialogue import ClinicalSlot, DialogueState
from contracts.extraction import ExtractionResult, ExtractedSlot
from ayusetu.ai.conversation.engine import DialogueEngine
from ayusetu.ai.conversation.extractor import DeterministicRuleExtractor, ClinicalExtractor
from ayusetu.ai.conversation.llm_provider import LLMProvider
from ayusetu.ai.clinical.memory import ClinicalMemory

class MockExtractor(ClinicalExtractor):
    def __init__(self, return_result: ExtractionResult):
        self.return_result = return_result
        self.called = False

    def extract(self, text: str, target_slot=None) -> ExtractionResult:
        self.called = True
        return self.return_result

class MockLLMProvider(LLMProvider):
    def __init__(self, return_text=""):
        self.return_text = return_text

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return self.return_text

# Tests 1-3: Engine merge logic
def test_primary_high_confidence_fallback_not_invoked():
    primary_result = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="headache", confidence=0.9, evidence="headache")
    ])
    primary_extractor = MockExtractor(primary_result)

    engine = DialogueEngine(extractor=primary_extractor)
    state = engine.initialize()
    state.missing_slots = [ClinicalSlot.CHIEF_COMPLAINT]

    asr = ASROutput(text="I have a headache", confidence=0.9, language="en")
    engine.step(asr, state)

    assert primary_extractor.called
    snapshot = engine.memory.get_current_snapshot()
    assert len(snapshot.slots) == 1
    assert snapshot.slots[ClinicalSlot.CHIEF_COMPLAINT].value == "headache"

def test_primary_low_confidence_fallback_invoked():
    primary_result = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="headache", confidence=0.4, evidence="headache")
    ])
    primary_extractor = MockExtractor(primary_result)

    engine = DialogueEngine(extractor=primary_extractor)
    state = engine.initialize()
    state.missing_slots = [ClinicalSlot.CHIEF_COMPLAINT]

    asr = ASROutput(text="I have a headache", confidence=0.9, language="en")
    engine.step(asr, state)

    assert primary_extractor.called
    snapshot = engine.memory.get_current_snapshot()
    assert snapshot.slots[ClinicalSlot.CHIEF_COMPLAINT].value == "headache"

def test_merge_rules_preserve_non_target():
    primary_result = ExtractionResult(extractions=[
        ExtractedSlot(slot=ClinicalSlot.DURATION, value="2 days", confidence=0.9, evidence="2 days"),
        ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="headache", confidence=0.2, evidence="headache")
    ])
    primary_extractor = MockExtractor(primary_result)

    engine = DialogueEngine(extractor=primary_extractor)
    state = engine.initialize()
    state.missing_slots = [ClinicalSlot.CHIEF_COMPLAINT]

    asr = ASROutput(text="I have a headache for 2 days", confidence=0.9, language="en")
    engine.step(asr, state)

    snapshot = engine.memory.get_current_snapshot()
    assert snapshot.slots[ClinicalSlot.DURATION].value == "2 days"
    assert snapshot.slots[ClinicalSlot.CHIEF_COMPLAINT].value == "headache"

# Tests 4-13: Deterministic rule extractor specifics
@pytest.fixture
def fallback_extractor():
    return DeterministicRuleExtractor()

def test_chief_complaint_english(fallback_extractor):
    res = fallback_extractor.extract("I have a stomach pain from last 2 days")
    slots = {e.slot: e.value for e in res.extractions}
    assert ClinicalSlot.CHIEF_COMPLAINT in slots
    assert "stomach pain" in slots[ClinicalSlot.CHIEF_COMPLAINT].lower()
    assert ClinicalSlot.DURATION in slots
    assert "2 day" in slots[ClinicalSlot.DURATION].lower()

def test_chief_complaint_hindi(fallback_extractor):
    res = fallback_extractor.extract("मुझे पेट दर्द है")
    slots = {e.slot: e.value for e in res.extractions}
    assert ClinicalSlot.CHIEF_COMPLAINT in slots

def test_severity_parsing(fallback_extractor):
    res1 = fallback_extractor.extract("5 out of 10")
    slots1 = {e.slot: e.value for e in res1.extractions}
    assert ClinicalSlot.SEVERITY in slots1
    assert "5/10" in slots1[ClinicalSlot.SEVERITY] or "5" in slots1[ClinicalSlot.SEVERITY]

    res2 = fallback_extractor.extract("7/10")
    slots2 = {e.slot: e.value for e in res2.extractions}
    assert ClinicalSlot.SEVERITY in slots2
    assert "7/10" in slots2[ClinicalSlot.SEVERITY] or "7" in slots2[ClinicalSlot.SEVERITY]

def test_negation_for_pmh(fallback_extractor):
    res = fallback_extractor.extract("no", target_slot=ClinicalSlot.PAST_MEDICAL_HISTORY)
    slots = {e.slot: e.value for e in res.extractions}
    assert ClinicalSlot.PAST_MEDICAL_HISTORY in slots
    assert slots[ClinicalSlot.PAST_MEDICAL_HISTORY] == "none reported"

def test_negation_for_medications(fallback_extractor):
    res = fallback_extractor.extract("no", target_slot=ClinicalSlot.MEDICATIONS)
    slots = {e.slot: e.value for e in res.extractions}
    assert ClinicalSlot.MEDICATIONS in slots
    assert slots[ClinicalSlot.MEDICATIONS] == "none"

def test_negation_for_allergies(fallback_extractor):
    res = fallback_extractor.extract("nothing", target_slot=ClinicalSlot.ALLERGIES)
    slots = {e.slot: e.value for e in res.extractions}
    assert ClinicalSlot.ALLERGIES in slots
    assert slots[ClinicalSlot.ALLERGIES] == "none"

def test_duration_hinglish(fallback_extractor):
    res = fallback_extractor.extract("do din se")
    slots = {e.slot: e.value for e in res.extractions}
    assert ClinicalSlot.DURATION in slots
    assert "2 day" in slots[ClinicalSlot.DURATION].lower() or "do din" in slots[ClinicalSlot.DURATION].lower()

def test_associated_symptoms(fallback_extractor):
    res = fallback_extractor.extract("I also have fever and vomiting")
    slots = {e.slot: e.value for e in res.extractions}
    assert ClinicalSlot.ASSOCIATED_SYMPTOMS in slots

def test_blank_empty_input(fallback_extractor):
    res = fallback_extractor.extract("")
    assert len(res.extractions) == 0

def test_irrelevant_input(fallback_extractor):
    res = fallback_extractor.extract("hello doctor")
    slots = {e.slot: e.value for e in res.extractions}
    assert ClinicalSlot.CHIEF_COMPLAINT not in slots

# Test 14: Empty response guard
def test_empty_response_guard():
    # Use a mock LLM that returns empty string
    empty_llm_provider = MockLLMProvider(return_text="   ")
    engine = DialogueEngine(llm_provider=empty_llm_provider)
    state = engine.initialize()

    asr = ASROutput(text="hello", confidence=0.9, language="en")
    response = engine.step(asr, state)

    assert response is not None
    assert response.strip() != ""
    assert "आपको क्या समस्या हो रही है?" in response or "कृपया थोड़ा और बताइए।" in response
