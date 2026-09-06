import unittest
import numpy as np
from src.ayusetu.ai.voice.tts.chatterbox import ChatterboxTTS

class TestChatterboxIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize provider; uses default config (cpu)
        cls.provider = ChatterboxTTS()

    def test_synthesize_short_sentence(self):
        text = "नमस्ते"
        result = self.provider.synthesize(text, language="hi")
        # Basic sanity checks
        self.assertIsNotNone(result)
        self.assertTrue(isinstance(result.audio, np.ndarray))
        self.assertGreater(len(result.audio), 0)
        self.assertEqual(result.sample_rate, getattr(self.provider, "_sample_rate", 24000))
        self.assertAlmostEqual(result.duration, len(result.audio) / result.sample_rate, places=3)
        self.assertEqual(result.language, "hi")

if __name__ == "__main__":
    unittest.main()
