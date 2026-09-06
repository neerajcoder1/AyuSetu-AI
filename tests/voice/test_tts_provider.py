import unittest
import numpy as np
from contracts.tts_result import TTSResult
from src.ayusetu.ai.voice.tts.base import TTSProvider

class MockProvider(TTSProvider):
    def synthesize(self, text: str, language: str) -> TTSResult:
        sample_rate = 24000
        audio = np.zeros(sample_rate, dtype=np.float32)
        duration = 1.0
        return TTSResult(audio=audio, sample_rate=sample_rate, duration=duration, language=language)

class TestTTSProviderContract(unittest.TestCase):
    def setUp(self):
        self.provider = MockProvider()

    def test_synthesize_returns_valid_result(self):
        result = self.provider.synthesize("Hello world", "en")
        self.assertIsInstance(result, TTSResult)
        self.assertEqual(result.sample_rate, 24000)
        self.assertAlmostEqual(result.duration, 1.0)
        self.assertEqual(result.language, "en")
        self.assertTrue(isinstance(result.audio, np.ndarray))
        self.assertEqual(result.audio.shape[0], 24000)

    def test_multiple_languages(self):
        for lang in ["hi", "en", "hinglish"]:
            with self.subTest(lang=lang):
                result = self.provider.synthesize("Test", lang)
                self.assertEqual(result.language, lang)

if __name__ == "__main__":
    unittest.main()
