"""
Focused tests for the deterministic rule-based clinical extractor
and the session-scoped ClinicalMemory.

Coverage
--------
* English extraction (chief complaint, duration, severity, onset, location)
* Hindi extraction (Devanagari text)
* Hinglish extraction (mixed-script)
* Duration-specific parsing (numeric & word-based)
* Multi-slot extraction from one utterance
* Memory persistence across simulated turns
* Slot update/correction (lower confidence does NOT overwrite higher)
* Low/uncertain extraction confidence values
* Session isolation (two independent ClinicalMemory instances)
* Integration: DialogueEngine memory is populated after engine.step()
"""

import pytest
from contracts.asr_output import ASROutput
from contracts.dialogue import ClinicalSlot
from contracts.extraction import ExtractedSlot, ExtractionResult
from ayusetu.ai.clinical.memory import ClinicalMemory
from ayusetu.ai.clinical.utils import parse_duration, parse_onset, parse_severity, parse_location
from ayusetu.ai.conversation.engine import DialogueEngine
from ayusetu.ai.conversation.extractor import DeterministicRuleExtractor
from ayusetu.ai.conversation.llm_provider import LLMProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class SilentLLM(LLMProvider):
    """LLM stub that returns a fixed string without any network call."""
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return "OK"


def make_engine(**kwargs) -> DialogueEngine:
    return DialogueEngine(
        extractor=DeterministicRuleExtractor(),
        llm_provider=SilentLLM(),
        asr_confidence_threshold=0.6,
        extraction_confidence_threshold=0.7,
        **kwargs,
    )


@pytest.fixture
def extractor() -> DeterministicRuleExtractor:
    return DeterministicRuleExtractor()


@pytest.fixture
def memory() -> ClinicalMemory:
    return ClinicalMemory()


# ===========================================================================
# 1. English extraction
# ===========================================================================

class TestEnglishExtraction:
    def test_chief_complaint_stomach_pain(self, extractor):
        result = extractor.extract("I have a stomach pain since morning")
        cc = next((s for s in result.extractions if s.slot == ClinicalSlot.CHIEF_COMPLAINT), None)
        assert cc is not None
        assert "stomach" in cc.value.lower()
        assert cc.confidence >= 0.85

    def test_chief_complaint_headache(self, extractor):
        result = extractor.extract("I've been having a headache")
        cc = next((s for s in result.extractions if s.slot == ClinicalSlot.CHIEF_COMPLAINT), None)
        assert cc is not None
        assert "headache" in cc.value.lower()

    def test_chief_complaint_fever(self, extractor):
        result = extractor.extract("I have fever since yesterday")
        cc = next((s for s in result.extractions if s.slot == ClinicalSlot.CHIEF_COMPLAINT), None)
        assert cc is not None
        assert "fever" in cc.value.lower()

    def test_duration_numeric(self, extractor):
        result = extractor.extract("I have had pain for 3 days")
        dur = next((s for s in result.extractions if s.slot == ClinicalSlot.DURATION), None)
        assert dur is not None
        assert "3" in dur.value
        assert "day" in dur.value.lower()

    def test_severity_numeric_scale(self, extractor):
        result = extractor.extract("The pain is 7 out of 10")
        sev = next((s for s in result.extractions if s.slot == ClinicalSlot.SEVERITY), None)
        assert sev is not None
        assert "7" in sev.value
        assert sev.confidence >= 0.90

    def test_onset_yesterday(self, extractor):
        result = extractor.extract("It started yesterday")
        onset = next((s for s in result.extractions if s.slot == ClinicalSlot.ONSET), None)
        assert onset is not None
        assert "yesterday" in onset.value.lower()

    def test_location_chest(self, extractor):
        result = extractor.extract("I have pain in my chest")
        loc = next((s for s in result.extractions if s.slot == ClinicalSlot.LOCATION), None)
        assert loc is not None
        assert "chest" in loc.value.lower()

    def test_no_extraction_on_unrelated_text(self, extractor):
        result = extractor.extract("Hello doctor, how are you today")
        assert result.extractions == [] or all(
            s.slot != ClinicalSlot.CHIEF_COMPLAINT for s in result.extractions
        )

    def test_lifestyle_smoking(self, extractor):
        result = extractor.extract("I have been smoking for 10 years")
        ls = next((s for s in result.extractions if s.slot == ClinicalSlot.LIFESTYLE), None)
        assert ls is not None
        assert "smoking" in ls.value.lower()


# ===========================================================================
# 2. Hindi extraction
# ===========================================================================

class TestHindiExtraction:
    def test_chief_complaint_pet_dard(self, extractor):
        result = extractor.extract("मुझे पेट में दर्द है")
        cc = next((s for s in result.extractions if s.slot == ClinicalSlot.CHIEF_COMPLAINT), None)
        assert cc is not None
        assert cc.confidence >= 0.85

    def test_chief_complaint_bukhaar(self, extractor):
        result = extractor.extract("मुझे बुखार है")
        cc = next((s for s in result.extractions if s.slot == ClinicalSlot.CHIEF_COMPLAINT), None)
        assert cc is not None
        assert "fever" in cc.value.lower()

    def test_duration_hindi_word(self, extractor):
        result = extractor.extract("मुझे दो दिन से पेट में दर्द है")
        dur = next((s for s in result.extractions if s.slot == ClinicalSlot.DURATION), None)
        assert dur is not None
        assert "2" in dur.value
        assert "day" in dur.value.lower()

    def test_severity_hindi(self, extractor):
        result = extractor.extract("दर्द बहुत तेज़ है")
        sev = next((s for s in result.extractions if s.slot == ClinicalSlot.SEVERITY), None)
        assert sev is not None
        assert "severe" in sev.value.lower()

    def test_onset_hindi_kal(self, extractor):
        result = extractor.extract("कल से सिर में दर्द है")
        onset = next((s for s in result.extractions if s.slot == ClinicalSlot.ONSET), None)
        assert onset is not None
        assert "yesterday" in onset.value.lower()

    def test_location_pet(self, extractor):
        result = extractor.extract("पेट में दर्द हो रहा है")
        loc = next((s for s in result.extractions if s.slot == ClinicalSlot.LOCATION), None)
        assert loc is not None
        assert "stomach" in loc.value.lower() or "abdomen" in loc.value.lower()

    def test_associated_symptom_bukhaar_with_complaint(self, extractor):
        # Chief complaint is stomach pain; fever should appear as associated
        result = extractor.extract("पेट में दर्द है और बुखार भी है")
        assoc = next((s for s in result.extractions if s.slot == ClinicalSlot.ASSOCIATED_SYMPTOMS), None)
        assert assoc is not None
        assert "fever" in assoc.value.lower()


# ===========================================================================
# 3. Hinglish extraction
# ===========================================================================

class TestHinglishExtraction:
    def test_chief_complaint_hinglish(self, extractor):
        result = extractor.extract("mujhe sir dard hai")
        cc = next((s for s in result.extractions if s.slot == ClinicalSlot.CHIEF_COMPLAINT), None)
        assert cc is not None
        assert "headache" in cc.value.lower()

    def test_duration_hinglish_do_din(self, extractor):
        result = extractor.extract("do din se sir dard hai")
        dur = next((s for s in result.extractions if s.slot == ClinicalSlot.DURATION), None)
        assert dur is not None
        assert "2" in dur.value

    def test_onset_hinglish_kal(self, extractor):
        result = extractor.extract("kal se pet mein dard shuru hua")
        onset = next((s for s in result.extractions if s.slot == ClinicalSlot.ONSET), None)
        assert onset is not None
        assert "yesterday" in onset.value.lower()

    def test_mixed_script_fever(self, extractor):
        result = extractor.extract("mujhe बुखार hai aur headache bhi")
        cc = next((s for s in result.extractions if s.slot == ClinicalSlot.CHIEF_COMPLAINT), None)
        assert cc is not None  # either fever or headache
        assoc = next((s for s in result.extractions if s.slot == ClinicalSlot.ASSOCIATED_SYMPTOMS), None)
        # At least one of the two symptoms should appear somewhere
        all_values = [s.value for s in result.extractions]
        combined = " ".join(all_values).lower()
        assert "fever" in combined or "headache" in combined


# ===========================================================================
# 4. Duration parsing (unit tests for utils)
# ===========================================================================

class TestDurationParsing:
    def test_numeric_days_en(self):
        result = parse_duration("I have had pain for 3 days")
        assert result is not None
        assert "3" in result[0]
        assert result[1] >= 0.85

    def test_word_number_hindi(self):
        result = parse_duration("दो दिन से बुखार है")
        assert result is not None
        assert "2" in result[0]

    def test_word_number_hinglish(self):
        result = parse_duration("do din se dard hai")
        assert result is not None
        assert "2" in result[0]

    def test_weeks(self):
        result = parse_duration("pain since 2 weeks")
        assert result is not None
        assert "week" in result[0].lower()

    def test_vague_duration_lower_confidence(self):
        result = parse_duration("kuch din se dard hai")
        assert result is not None
        # Vague durations have lower confidence
        assert result[1] < 0.70

    def test_no_duration(self):
        result = parse_duration("I have a headache")
        assert result is None


# ===========================================================================
# 5. Multi-slot extraction
# ===========================================================================

class TestMultiSlotExtraction:
    def test_complaint_and_duration_together(self, extractor):
        result = extractor.extract("I have had stomach pain for 2 days")
        slots = {s.slot for s in result.extractions}
        assert ClinicalSlot.CHIEF_COMPLAINT in slots
        assert ClinicalSlot.DURATION in slots

    def test_complaint_duration_onset_hinglish(self, extractor):
        result = extractor.extract("kal se do din pehle pet mein dard shuru hua hai")
        slots = {s.slot for s in result.extractions}
        assert ClinicalSlot.CHIEF_COMPLAINT in slots or ClinicalSlot.DURATION in slots

    def test_complaint_severity_location(self, extractor):
        result = extractor.extract("I have severe chest pain")
        slots = {s.slot for s in result.extractions}
        assert ClinicalSlot.CHIEF_COMPLAINT in slots
        assert ClinicalSlot.SEVERITY in slots
        assert ClinicalSlot.LOCATION in slots

    def test_no_duplicate_slot_types(self, extractor):
        result = extractor.extract("I have had stomach pain for 3 days and fever")
        # Each slot should appear at most once
        slot_counts: dict = {}
        for s in result.extractions:
            slot_counts[s.slot] = slot_counts.get(s.slot, 0) + 1
        for slot, count in slot_counts.items():
            assert count == 1, f"Slot {slot} appears {count} times"


# ===========================================================================
# 6. Memory persistence across turns
# ===========================================================================

class TestMemoryPersistence:
    def test_slot_stored_after_single_update(self, memory):
        slots = [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="fever", confidence=0.90)]
        memory.update_from_extractions(slots, "I have fever")
        snap = memory.get_current_snapshot()
        assert ClinicalSlot.CHIEF_COMPLAINT in snap.slots
        assert snap.slots[ClinicalSlot.CHIEF_COMPLAINT].value == "fever"

    def test_multiple_turns_accumulate_slots(self, memory):
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="stomach pain", confidence=0.92)],
            "I have stomach pain",
        )
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.DURATION, value="2 day(s)", confidence=0.90)],
            "It started 2 days ago",
        )
        snap = memory.get_current_snapshot()
        assert ClinicalSlot.CHIEF_COMPLAINT in snap.slots
        assert ClinicalSlot.DURATION in snap.slots

    def test_source_utterance_stored(self, memory):
        utterance = "I have had a headache for 3 days"
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="headache", confidence=0.92)],
            utterance,
        )
        entry = memory.get_slot(ClinicalSlot.CHIEF_COMPLAINT)
        assert entry is not None
        assert entry.source_utterance == utterance


# ===========================================================================
# 7. Slot correction / update (confidence-guarded)
# ===========================================================================

class TestSlotUpdate:
    def test_higher_confidence_overwrites(self, memory):
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="headache", confidence=0.75)],
            "mujhe sir dard hai",
        )
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="migraine", confidence=0.92)],
            "I have migraine",
        )
        entry = memory.get_slot(ClinicalSlot.CHIEF_COMPLAINT)
        assert entry.value == "migraine"
        assert entry.confidence == 0.92

    def test_lower_confidence_does_not_overwrite(self, memory):
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="fever", confidence=0.92)],
            "I have fever",
        )
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="cough", confidence=0.65)],
            "maybe cough",
        )
        entry = memory.get_slot(ClinicalSlot.CHIEF_COMPLAINT)
        # Original high-confidence value must be preserved
        assert entry.value == "fever"
        assert entry.confidence == 0.92

    def test_equal_confidence_does_not_overwrite(self, memory):
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.DURATION, value="2 day(s)", confidence=0.90)],
            "two days ago",
        )
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.DURATION, value="3 day(s)", confidence=0.90)],
            "three days ago",
        )
        entry = memory.get_slot(ClinicalSlot.DURATION)
        # Equal confidence → keep original (strictly greater required to update)
        assert entry.value == "2 day(s)"

    def test_history_preserved_on_overwrite(self, memory):
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="headache", confidence=0.75)],
            "mujhe sir dard hai",
        )
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="migraine", confidence=0.93)],
            "severe migraine",
        )
        entry = memory.get_slot(ClinicalSlot.CHIEF_COMPLAINT)
        assert len(entry.history) == 1
        assert entry.history[0].value == "headache"


# ===========================================================================
# 8. Low/uncertain confidence extractions
# ===========================================================================

class TestLowConfidenceExtraction:
    def test_vague_duration_stored_with_low_confidence(self, memory):
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.DURATION, value="a few days", confidence=0.55)],
            "kuch din se dard hai",
        )
        entry = memory.get_slot(ClinicalSlot.DURATION)
        assert entry is not None
        assert entry.confidence < 0.70

    def test_low_conf_does_not_block_future_high_conf(self, memory):
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.DURATION, value="a few days", confidence=0.55)],
            "kuch din se",
        )
        memory.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.DURATION, value="3 day(s)", confidence=0.90)],
            "three days",
        )
        entry = memory.get_slot(ClinicalSlot.DURATION)
        assert entry.value == "3 day(s)"
        assert entry.confidence == 0.90


# ===========================================================================
# 9. Session isolation
# ===========================================================================

class TestSessionIsolation:
    def test_two_memories_are_independent(self):
        mem_a = ClinicalMemory()
        mem_b = ClinicalMemory()

        mem_a.update_from_extractions(
            [ExtractedSlot(slot=ClinicalSlot.CHIEF_COMPLAINT, value="fever", confidence=0.90)],
            "session A utterance",
        )

        # Session B must have no data
        snap_b = mem_b.get_current_snapshot()
        assert ClinicalSlot.CHIEF_COMPLAINT not in snap_b.slots

        # Session A must be unaffected by B
        snap_a = mem_a.get_current_snapshot()
        assert ClinicalSlot.CHIEF_COMPLAINT in snap_a.slots

    def test_engine_creates_own_memory_by_default(self):
        engine_a = make_engine()
        engine_b = make_engine()
        assert engine_a.memory is not engine_b.memory


# ===========================================================================
# 10. Integration: DialogueEngine memory updated after step()
# ===========================================================================

class TestEngineMemoryIntegration:
    def test_memory_populated_after_step(self):
        engine = make_engine()
        state = engine.initialize()
        asr = ASROutput(text="I have stomach pain for 2 days", language="en", confidence=0.92)
        engine.step(asr, state)

        snap = engine.memory.get_current_snapshot()
        assert ClinicalSlot.CHIEF_COMPLAINT in snap.slots
        assert ClinicalSlot.DURATION in snap.slots

    def test_memory_not_updated_on_low_asr_confidence(self):
        engine = make_engine()
        state = engine.initialize()
        asr = ASROutput(text="I have stomach pain for 2 days", language="en", confidence=0.30)
        engine.step(asr, state)

        snap = engine.memory.get_current_snapshot()
        # Low ASR confidence bypasses extraction → memory must remain empty
        assert snap.slots == {}

    def test_memory_accumulates_across_turns(self):
        engine = make_engine()
        state = engine.initialize()

        engine.step(ASROutput(text="I have a headache", language="en", confidence=0.92), state)
        engine.step(ASROutput(text="It started yesterday", language="en", confidence=0.90), state)
        engine.step(ASROutput(text="The pain is 7 out of 10", language="en", confidence=0.88), state)

        snap = engine.memory.get_current_snapshot()
        collected = snap.collected_slots()
        assert ClinicalSlot.CHIEF_COMPLAINT in collected
        assert ClinicalSlot.ONSET in collected
        assert ClinicalSlot.SEVERITY in collected

    def test_memory_correction_across_turns(self):
        engine = make_engine()
        state = engine.initialize()

        # First turn: low confidence duration
        engine.step(
            ASROutput(text="kuch din se dard hai", language="hinglish", confidence=0.85),
            state,
        )
        first_entry = engine.memory.get_slot(ClinicalSlot.DURATION)
        first_confidence = first_entry.confidence if first_entry else None

        # Second turn: explicit numeric duration (should overwrite if confidence is higher)
        engine.step(
            ASROutput(text="pain since 3 days", language="en", confidence=0.92),
            state,
        )
        second_entry = engine.memory.get_slot(ClinicalSlot.DURATION)
        assert second_entry is not None

        if first_entry and first_confidence:
            if 0.90 > first_confidence:
                assert second_entry.value == "3 day(s)"

    def test_engine_memory_is_injection_passable(self):
        """Verify that memory can be injected externally (e.g., by tests)."""
        external_memory = ClinicalMemory()
        engine = make_engine(memory=external_memory)
        assert engine.memory is external_memory
