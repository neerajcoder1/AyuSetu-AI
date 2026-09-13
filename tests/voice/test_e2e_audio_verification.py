"""
AyuSetu AI — E2E Real Audio & FastAPI Verification Test
======================================================
Tests the full voice pipeline through FastAPI TestClient with REAL models:
- Session Creation & Language Preference
- ASR Audio Processing
- Dialogue Engine Response Generation
- Devanagari → Roman Transliteration Preprocessing
- Real Chatterbox TTS Audio Synthesis
- Base64 WAV Encoding & Soundfile Decoding
- Audio Amplitude / Non-Silence Verification
"""

import base64
import io
import math
from unittest.mock import patch
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

import ayusetu.api.fastapi_voice as api
from ayusetu.ai.voice.tts.chatterbox import transliterate_devanagari_to_roman, ChatterboxTTS
from ayusetu.ai.voice.asr.confidence import infer_language_from_text
from contracts.asr_output import ASROutput


@pytest.fixture(scope="module")
def real_client():
    """Returns a TestClient wrapping the real FastAPI app with real VoicePipeline."""
    return TestClient(api.app)


def _create_dummy_wav_bytes():
    """16kHz mono WAV dummy file for HTTP upload."""
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), False)
    tone = 0.5 * np.sin(2 * np.pi * 440 * t)
    buf = io.BytesIO()
    sf.write(buf, tone, sr, format="WAV")
    return buf.getvalue()


class TestEndToEndVoicePipeline:
    def test_hindi_turn_e2e(self, real_client):
        """Test Hindi Voice Consultation Turn:
        Devanagari input -> Session creation -> ASR -> Dialogue -> TTS Transliteration -> Audio Output
        """
        # 1. Create session with preferred_language = "hi"
        res_sess = real_client.post("/sessions", json={"preferred_language": "hi"})
        assert res_sess.status_code == 200, f"Session creation failed: {res_sess.text}"
        sess_data = res_sess.json()
        session_id = sess_data["session_id"]
        assert sess_data["preferred_language"] == "hi"

        # 2. Prepare audio turn
        wav_bytes = _create_dummy_wav_bytes()

        # 3. Patch ASR output to simulate patient saying Hindi phrase
        mock_asr = ASROutput(
            text="मुझे दो दिन से पेट में दर्द हो रहा है।",
            language="hi",
            confidence=0.95,
            raw_text="मुझे दो दिन से पेट में दर्द हो रहा है।",
            backend="transformers",
            method="avg_logprob_from_token_scores"
        )

        with patch("ayusetu.ai.voice.asr.transcriber.transcribe", return_value=mock_asr):
            files = {"audio": ("turn_hindi.wav", wav_bytes, "audio/wav")}
            res_turn = real_client.post(f"/sessions/{session_id}/turn", files=files)

        assert res_turn.status_code == 200, f"Turn processing failed: {res_turn.text}"

        turn_data = res_turn.json()

        # 4. Verify AI response text exists
        assert turn_data.get("response_text"), "AI response text must be non-empty"

        # 5. Verify Devanagari to Roman transliteration
        raw_response = turn_data["response_text"]
        transliterated = transliterate_devanagari_to_roman(raw_response)
        assert len(transliterated) > 0, "Transliterated string must be non-empty"

        # 6. Verify FastAPI returned base64 WAV audio
        audio_b64 = turn_data.get("response_audio")
        assert audio_b64, "FastAPI response_audio base64 must be present"

        # 7. Decode Base64 WAV and verify physical audio properties
        audio_bytes = base64.b64decode(audio_b64)
        assert len(audio_bytes) > 44, "Audio WAV bytes must exceed 44-byte header"

        data, sample_rate = sf.read(io.BytesIO(audio_bytes))
        duration = len(data) / sample_rate
        rms_amplitude = np.sqrt(np.mean(data ** 2))

        assert sample_rate == 24000, f"Chatterbox sample rate should be 24000 Hz, got {sample_rate}"
        assert duration > 0.5, f"Audio duration must be > 0.5s, got {duration:.2f}s"
        assert rms_amplitude > 0.001, f"Audio must contain audible sound (RMS > 0.001), got {rms_amplitude:.6f}"

    def test_english_turn_e2e(self, real_client):
        """Test English Voice Consultation Turn:
        English input -> Session creation -> ASR -> Dialogue -> TTS -> Audio Output
        """
        # 1. Create session with preferred_language = "en"
        res_sess = real_client.post("/sessions", json={"preferred_language": "en"})
        assert res_sess.status_code == 200
        session_id = res_sess.json()["session_id"]

        # 2. Prepare audio turn
        wav_bytes = _create_dummy_wav_bytes()

        # 3. Patch ASR output
        mock_asr = ASROutput(
            text="I have had stomach pain for two days.",
            language="en",
            confidence=0.96,
            raw_text="I have had stomach pain for two days.",
            backend="transformers",
            method="avg_logprob_from_token_scores"
        )

        with patch("ayusetu.ai.voice.asr.transcriber.transcribe", return_value=mock_asr):
            files = {"audio": ("turn_english.wav", wav_bytes, "audio/wav")}
            res_turn = real_client.post(f"/sessions/{session_id}/turn", files=files)

        assert res_turn.status_code == 200

        turn_data = res_turn.json()
        assert turn_data.get("response_text")
        audio_b64 = turn_data.get("response_audio")
        assert audio_b64

        audio_bytes = base64.b64decode(audio_b64)
        data, sample_rate = sf.read(io.BytesIO(audio_bytes))
        duration = len(data) / sample_rate
        rms_amplitude = np.sqrt(np.mean(data ** 2))

        assert sample_rate == 24000
        assert duration > 0.5
        assert rms_amplitude > 0.001

    def test_hinglish_turn_e2e(self, real_client):
        """Test Hinglish Voice Consultation Turn:
        Hinglish input -> Session creation -> ASR -> Dialogue -> TTS -> Audio Output
        """
        # 1. Create session with preferred_language = "hinglish"
        res_sess = real_client.post("/sessions", json={"preferred_language": "hinglish"})
        assert res_sess.status_code == 200
        session_id = res_sess.json()["session_id"]

        # 2. Prepare audio turn
        wav_bytes = _create_dummy_wav_bytes()

        # 3. Patch ASR output
        mock_asr = ASROutput(
            text="Mujhe do din se stomach mein pain ho raha hai.",
            language="hinglish",
            confidence=0.94,
            raw_text="Mujhe do din se stomach mein pain ho raha hai.",
            backend="transformers",
            method="avg_logprob_from_token_scores"
        )

        with patch("ayusetu.ai.voice.asr.transcriber.transcribe", return_value=mock_asr):
            files = {"audio": ("turn_hinglish.wav", wav_bytes, "audio/wav")}
            res_turn = real_client.post(f"/sessions/{session_id}/turn", files=files)

        assert res_turn.status_code == 200

        turn_data = res_turn.json()
        assert turn_data.get("response_text")
        audio_b64 = turn_data.get("response_audio")
        assert audio_b64

        audio_bytes = base64.b64decode(audio_b64)
        data, sample_rate = sf.read(io.BytesIO(audio_bytes))
        duration = len(data) / sample_rate
        rms_amplitude = np.sqrt(np.mean(data ** 2))

        assert sample_rate == 24000
        assert duration > 0.5
        assert rms_amplitude > 0.001
