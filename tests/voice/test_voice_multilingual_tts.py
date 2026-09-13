import pytest
import numpy as np
from ayusetu.ai.voice.tts.chatterbox import ChatterboxTTS, transliterate_devanagari_to_roman
from ayusetu.ai.voice.asr.confidence import infer_language_from_text
from ayusetu.ai.voice.pipeline.voice_pipeline import VoicePipeline

class TestVoiceMultilingualTTS:

    @pytest.fixture(autouse=True)
    def setup_tts(self):
        self.tts = ChatterboxTTS()
        self.pipeline = VoicePipeline()

    def test_transliteration_devanagari_to_roman(self):
        hindi_devanagari = "समझ गया, कृपया आगे बताएं।"
        romanized = transliterate_devanagari_to_roman(hindi_devanagari)
        assert "samajh" in romanized.lower()
        assert "kripya" in romanized.lower()
        assert "aage" in romanized.lower()

        # Non-Devanagari remains untouched
        english_text = "I have stomach pain for two days."
        assert transliterate_devanagari_to_roman(english_text) == english_text

    def test_case_a_english_tts_audio_synthesis(self):
        text = "I have stomach pain for two days."
        res = self.tts.synthesize(text=text, language="en")

        assert res is not None
        assert res.sample_rate == 24000
        assert res.duration > 0.0
        assert isinstance(res.audio, np.ndarray)
        assert len(res.audio) > 0
        assert res.language == "en"

    def test_case_b_hindi_devanagari_tts_audio_synthesis(self):
        hindi_text = "मुझे दो दिन से पेट में दर्द हो रहा है।"
        res = self.tts.synthesize(text=hindi_text, language="hi")

        assert res is not None
        assert res.sample_rate == 24000
        assert res.duration > 0.0
        assert isinstance(res.audio, np.ndarray)
        assert len(res.audio) > 0
        assert res.language == "hi"

    def test_case_c_hinglish_tts_audio_synthesis(self):
        hinglish_text = "Samajh gaya, kripya aage batayein."
        res = self.tts.synthesize(text=hinglish_text, language="hinglish")

        assert res is not None
        assert res.sample_rate == 24000
        assert res.duration > 0.0
        assert isinstance(res.audio, np.ndarray)
        assert len(res.audio) > 0
        assert res.language == "hinglish"

    def test_namaste_hinglish_language_heuristic(self):
        # Verify single word Romanized Hindi greeting is recognized as hinglish
        lang = infer_language_from_text("namaste")
        assert lang == "hinglish"
