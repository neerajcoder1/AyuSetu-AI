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

    target_utterances = [
        "3 days ago it started.",
        "I noticed this symptom last 2 days",
        "I noticed first time symptom last 2 days",
        "I noticed this symptom two days ago",
        "It started two days ago",
        "I first noticed it two days ago",
        "The symptoms started two days ago",
        "Hello, I have had a fever and stomach pain from last 2 days.",
        "for the past 2 days",
        "since 2 days",
    ]

    for utt in target_utterances:
        result = extractor.extract(utt)
        slots = {e.slot: e.value for e in result.extractions}
        assert ClinicalSlot.ONSET in slots, f"English onset was not extracted for: '{utt}'"

def test_live_4turn_e2e_sequence_no_duplicate_onset():
    provider = MockWordingProvider()
    engine = DialogueEngine(
        extractor=DeterministicRuleExtractor(),
        llm_provider=provider,
    )
    state = engine.initialize()

    # Turn 1: Patient gives initial complaint with 'from last 2 days'
    asr1 = ASROutput(text="Hello, I have had a fever and stomach pain from last 2 days.", language="en", confidence=0.95)
    engine.step(asr1, state)
    assert ClinicalSlot.ONSET in state.collected_info
    assert state.missing_slots[0] != ClinicalSlot.ONSET

    # Turn 2: Patient answers 'I noticed first time symptom last 2 days'
    asr2 = ASROutput(text="I noticed first time symptom last 2 days", language="en", confidence=0.95)
    engine.step(asr2, state)
    assert state.missing_slots[0] != ClinicalSlot.ONSET

    # Turn 3: Patient gives headache and fever
    asr3 = ASROutput(text="My main problem is headache and fever", language="en", confidence=0.95)
    engine.step(asr3, state)
    assert state.missing_slots[0] != ClinicalSlot.ONSET

    # Turn 4: Patient gives 'I noticed this symptom last 2 days'
    asr4 = ASROutput(text="I noticed this symptom last 2 days", language="en", confidence=0.95)
    engine.step(asr4, state)
    assert state.missing_slots[0] != ClinicalSlot.ONSET

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

def test_negative_past_medical_history_extractions():
    extractor = DeterministicRuleExtractor()
    negative_utterances = [
        "No, I don't have any pre-susmedical conditions",
        "No, I don't have any previous medical conditions.",
        "I have no previous medical history.",
        "No medical conditions.",
        "No, nothing.",
        "I don't have any past medical conditions.",
        "There are no previous conditions.",
        "No past medical history",
        "No prior conditions",
        "koi bimari nahi hai",
        "kuch nahi hai",
        "koi dikkat nahi",
        "koi bimari nahi",
        "कोई बीमारी नहीं",
    ]

    for utt in negative_utterances:
        result = extractor.extract(utt, target_slot=ClinicalSlot.PAST_MEDICAL_HISTORY)
        slots = {e.slot: e.value for e in result.extractions}
        assert ClinicalSlot.PAST_MEDICAL_HISTORY in slots, f"Negative PMH was not extracted for: '{utt}'"
        assert slots[ClinicalSlot.PAST_MEDICAL_HISTORY] in ["none reported", "none"]

def test_planner_no_duplicate_past_medical_history_question():
    provider = MockWordingProvider()
    engine = DialogueEngine(
        extractor=DeterministicRuleExtractor(),
        llm_provider=provider,
    )
    state = engine.initialize()

    # Advance state until PAST_MEDICAL_HISTORY is the active slot
    while state.missing_slots and state.missing_slots[0] != ClinicalSlot.PAST_MEDICAL_HISTORY:
        state.collected_info[state.missing_slots[0]] = "dummy_value"
        state.missing_slots.pop(0)

    assert state.missing_slots[0] == ClinicalSlot.PAST_MEDICAL_HISTORY

    # Turn: Patient answers with garbled live transcript
    asr = ASROutput(text="No, I don't have any pre-susmedical conditions", language="en", confidence=0.95)
    engine.step(asr, state)

    # 1. Verify PMH is stored in DialogueState.collected_info
    assert ClinicalSlot.PAST_MEDICAL_HISTORY in state.collected_info
    assert state.collected_info[ClinicalSlot.PAST_MEDICAL_HISTORY] == "none reported"

    # 2. Verify PMH is stored in session-scoped ClinicalMemory
    stored_entry = engine.memory.get_slot(ClinicalSlot.PAST_MEDICAL_HISTORY)
    assert stored_entry is not None
    assert stored_entry.value == "none reported"

    # 3. Verify DialoguePlanner removes PAST_MEDICAL_HISTORY from missing_slots and advances
    assert state.missing_slots[0] != ClinicalSlot.PAST_MEDICAL_HISTORY

def test_clinical_slot_audit_fixes_extraction():
    extractor = DeterministicRuleExtractor()

    # 1. Location gale
    res1 = extractor.extract("gale mein pain hai", target_slot=ClinicalSlot.LOCATION)
    slots1 = {e.slot: e.value for e in res1.extractions}
    assert ClinicalSlot.LOCATION in slots1
    assert slots1[ClinicalSlot.LOCATION] == "throat/neck"

    # 2. Medications negative phrasing
    for phrase in ["I am not taking anything", "I don't take any medicine"]:
        res2 = extractor.extract(phrase, target_slot=ClinicalSlot.MEDICATIONS)
        slots2 = {e.slot: e.value for e in res2.extractions}
        assert ClinicalSlot.MEDICATIONS in slots2
        assert slots2[ClinicalSlot.MEDICATIONS] == "none"

    # 3. Associated symptoms weak & dizzy
    res3 = extractor.extract("Sometimes I also feel weak and dizzy", target_slot=ClinicalSlot.ASSOCIATED_SYMPTOMS)
    slots3 = {e.slot: e.value for e in res3.extractions}
    assert ClinicalSlot.ASSOCIATED_SYMPTOMS in slots3
    assert "weakness" in slots3[ClinicalSlot.ASSOCIATED_SYMPTOMS]
    assert "dizziness" in slots3[ClinicalSlot.ASSOCIATED_SYMPTOMS]

    # 4. Severity badly
    res4 = extractor.extract("It hurts badly", target_slot=ClinicalSlot.SEVERITY)
    slots4 = {e.slot: e.value for e in res4.extractions}
    assert ClinicalSlot.SEVERITY in slots4
    assert slots4[ClinicalSlot.SEVERITY] == "severe"

def test_clinical_slot_audit_fixes_planner_progression():
    provider = MockWordingProvider()

    # Test each of the 4 slots advancing planner state, collected_info, and ClinicalMemory
    test_specs = [
        (ClinicalSlot.LOCATION, "gale mein pain hai", "throat/neck"),
        (ClinicalSlot.MEDICATIONS, "I am not taking anything", "none"),
        (ClinicalSlot.ASSOCIATED_SYMPTOMS, "Sometimes I also feel weak and dizzy", "weakness, dizziness"),
        (ClinicalSlot.SEVERITY, "It hurts badly", "severe"),
    ]

    for target_slot, phrase, expected_val in test_specs:
        engine = DialogueEngine(
            extractor=DeterministicRuleExtractor(),
            llm_provider=provider,
        )
        state = engine.initialize()

        # Fast forward missing slots to target_slot
        while state.missing_slots and state.missing_slots[0] != target_slot:
            state.collected_info[state.missing_slots[0]] = "prefilled"
            state.missing_slots.pop(0)

        assert state.missing_slots[0] == target_slot

        asr = ASROutput(text=phrase, language="en", confidence=0.95)
        engine.step(asr, state)

        # 1. State collected_info check
        assert target_slot in state.collected_info
        # 2. ClinicalMemory check
        mem_entry = engine.memory.get_slot(target_slot)
        assert mem_entry is not None
        assert mem_entry.value is not None
        # 3. Missing slots removed & planner advanced
        assert target_slot not in state.missing_slots
