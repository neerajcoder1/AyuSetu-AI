import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from contracts.asr_output import ASROutput
from ayusetu.ai.voice.pipeline.voice_pipeline import VoicePipeline

# Simple fake DialogueEngine for deterministic behavior
class FakeDialogueEngine:
    def __init__(self):
        pass

    def initialize(self):
        # Use a simple mutable dict as state
        return {"history": []}

    def step(self, asr_output, state):
        # Record a turn in state and return a fixed response
        state["history"].append({"text": asr_output.text})
        return "Fake response"

# Simple fake TTS provider returning deterministic result
class FakeTTSResult:
    def __init__(self):
        self.audio = b"audiobytes"
        self.sample_rate = 16000
        self.duration = 1.23

class FakeChatterboxTTS:
    def synthesize(self, text, language):
        return FakeTTSResult()

class TestVoicePipelineSessionManagement(unittest.TestCase):
    def setUp(self):
        # Patch the heavy components with fakes for all tests
        self.patcher_engine = patch(
            "ayusetu.ai.voice.pipeline.voice_pipeline.DialogueEngine",
            FakeDialogueEngine,
        )
        self.patcher_tts = patch(
            "ayusetu.ai.voice.pipeline.voice_pipeline.ChatterboxTTS",
            FakeChatterboxTTS,
        )
        self.mock_engine = self.patcher_engine.start()
        self.mock_tts = self.patcher_tts.start()
        self.addCleanup(self.patcher_engine.stop)
        self.addCleanup(self.patcher_tts.stop)

        # Use a dummy audio path – the transcribe function will be mocked
        self.dummy_path = Path("dummy.wav")

    def test_new_session_is_empty(self):
        pipeline = VoicePipeline()
        sid = pipeline.create_session()
        state = pipeline.get_state(sid)
        self.assertEqual(state["history"], [])

    def test_first_turn_updates_state(self):
        pipeline = VoicePipeline()
        sid = pipeline.create_session()
        high_conf = ASROutput(text="hello", language="en", confidence=0.9)
        with patch(
            "ayusetu.ai.voice.pipeline.voice_pipeline.transcribe",
            return_value=high_conf,
        ):
            result = pipeline.run(self.dummy_path, session_id=sid)
        self.assertIsNotNone(result["response_text"])
        state = pipeline.get_state(sid)
        self.assertEqual(len(state["history"]), 1)
        self.assertEqual(state["history"][0]["text"], "hello")

    def test_second_turn_preserves_same_state(self):
        pipeline = VoicePipeline()
        sid = pipeline.create_session()
        high_conf = ASROutput(text="first", language="en", confidence=0.9)
        with patch(
            "ayusetu.ai.voice.pipeline.voice_pipeline.transcribe",
            return_value=high_conf,
        ):
            pipeline.run(self.dummy_path, session_id=sid)
        # Second turn with different utterance
        high_conf2 = ASROutput(text="second", language="en", confidence=0.95)
        with patch(
            "ayusetu.ai.voice.pipeline.voice_pipeline.transcribe",
            return_value=high_conf2,
        ):
            pipeline.run(self.dummy_path, session_id=sid)
        state = pipeline.get_state(sid)
        self.assertEqual(len(state["history"]), 2)
        self.assertEqual(state["history"][1]["text"], "second")

    def test_low_confidence_does_not_mutate_state(self):
        pipeline = VoicePipeline()
        sid = pipeline.create_session()
        # First, run a high‑confidence turn to have some state
        high_conf = ASROutput(text="init", language="en", confidence=0.9)
        with patch(
            "ayusetu.ai.voice.pipeline.voice_pipeline.transcribe",
            return_value=high_conf,
        ):
            pipeline.run(self.dummy_path, session_id=sid)
        state_before = pipeline.get_state(sid)
        self.assertEqual(len(state_before["history"]), 1)
        # Now low‑confidence turn
        low_conf = ASROutput(text="noise", language="en", confidence=0.1)
        with patch(
            "ayusetu.ai.voice.pipeline.voice_pipeline.transcribe",
            return_value=low_conf,
        ):
            result = pipeline.run(self.dummy_path, session_id=sid)
        self.assertTrue(result["low_confidence"])
        # State must be unchanged and step should not be called (handled by fake engine)
        state_after = pipeline.get_state(sid)
        self.assertEqual(state_before, state_after)

    def test_ending_session_discards_state(self):
        pipeline = VoicePipeline()
        sid = pipeline.create_session()
        pipeline.end_session(sid)
        with self.assertRaises(KeyError):
            pipeline.get_state(sid)

    def test_missing_invalid_session_id_raises_error(self):
        pipeline = VoicePipeline()
        with self.assertRaises(KeyError):
            pipeline.get_state("nonexistent")
        with self.assertRaises(KeyError):
            pipeline.run(self.dummy_path, session_id="nonexistent")

if __name__ == "__main__":
    unittest.main()
