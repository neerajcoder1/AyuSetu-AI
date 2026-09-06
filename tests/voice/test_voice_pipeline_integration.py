import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from ayusetu.ai.voice.pipeline.voice_pipeline import VoicePipeline
from contracts.asr_output import ASROutput


class TestVoicePipelineEndToEnd(unittest.TestCase):
    def test_voice_pipeline_end_to_end(self):
        # Use a short real audio sample (English). Adjust path relative to repository root.
        audio_path = Path(__file__).parents[2] / "samples" / "audio" / "english.wav"
        pipeline = VoicePipeline()
        result = pipeline.run(audio_path)

        # Verify all expected keys are present.
        expected_keys = [
            "transcribed_text",
            "detected_language",
            "asr_confidence",
            "low_confidence",
            "response_text",
            "response_audio",
            "response_sample_rate",
            "response_duration",
        ]
        for key in expected_keys:
            self.assertIn(key, result)

        # Low confidence should be False for a normal sample.
        self.assertFalse(result["low_confidence"], "Expected high confidence for the sample audio")

        # Verify that TTS produced audio and that its metadata is sensible.
        self.assertIsNotNone(result["response_audio"], "TTS audio should be generated")
        self.assertTrue(len(result["response_audio"]) > 0, "Audio array should not be empty")
        self.assertIsInstance(result["response_sample_rate"], int)
        self.assertGreater(result["response_sample_rate"], 0)
        self.assertIsInstance(result["response_duration"], float)
        self.assertGreater(result["response_duration"], 0)


class TestVoicePipelineLowConfidence(unittest.TestCase):
    def test_low_confidence_skips_dialogue_and_tts(self):
        # Prepare a low‑confidence ASR output.
        low_conf_asr = ASROutput(text="low confidence speech", language="en", confidence=0.1)

        # Patch the ASR transcribe function to return the low‑confidence output.
        with patch("ayusetu.ai.voice.asr.transcriber.transcribe", return_value=low_conf_asr) as mock_transcribe:
            # Patch DialogueEngine and TTS provider to ensure they are not called.
            with patch("ayusetu.ai.conversation.engine.DialogueEngine") as MockEngine:
                mock_engine_instance = MagicMock()
                MockEngine.return_value = mock_engine_instance
                with patch("ayusetu.ai.voice.tts.chatterbox.ChatterboxTTS") as MockTTS:
                    mock_tts_instance = MagicMock()
                    MockTTS.return_value = mock_tts_instance

                    pipeline = VoicePipeline()
                    result = pipeline.run("dummy_path.wav")

        # Verify low_confidence flag is True.
        self.assertTrue(result["low_confidence"], "Result should indicate low confidence")
        # Response fields should be None / empty.
        self.assertIsNone(result["response_text"], "No response text should be generated for low confidence")
        self.assertIsNone(result["response_audio"], "No audio should be generated for low confidence")
        self.assertIsNone(result["response_sample_rate"], "No sample rate for low confidence")
        self.assertIsNone(result["response_duration"], "No duration for low confidence")

        # Ensure ASR was called.
        mock_transcribe.assert_called_once()
        # Ensure DialogueEngine and TTS were never used.
        mock_engine_instance.initialize.assert_not_called()
        mock_engine_instance.step.assert_not_called()
        mock_tts_instance.synthesize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
