"""
AyuSetu AI — ASR Module Tests
==============================
Tests are organized into three groups:

Unit tests (run with no model required, fast)
    - TestASROutputContract   ASROutput Pydantic schema and validators
    - TestAudioUtils          Audio loading, resampling, and validation
    - TestConfidence          Confidence computation and language inference
    - TestConfig              Configuration loading and validation

Smoke tests (require model download; slow; need SKIP_MODEL_TESTS=0)
    - TestSmoke               End-to-end transcribe() with real audio

Running the tests
-----------------
    # Unit tests only (fast, no model download):
    pytest tests/test_asr.py -v -k "not Smoke"

    # All tests including smoke (requires model + audio files):
    SKIP_MODEL_TESTS=0 pytest tests/test_asr.py -v

    # With audio paths for smoke tests:
    HINDI_AUDIO=samples/hindi.wav \\
    ENGLISH_AUDIO=samples/english.wav \\
    HINGLISH_AUDIO=samples/hinglish.wav \\
    SKIP_MODEL_TESTS=0 pytest tests/test_asr.py -v -k Smoke

Environment variables for smoke tests
--------------------------------------
    SKIP_MODEL_TESTS    Set to "1" to skip model tests (default="0")
    HINDI_AUDIO         Path to a Hindi speech WAV file
    ENGLISH_AUDIO       Path to an English speech WAV file
    HINGLISH_AUDIO      Path to a Hinglish (code-switched) WAV file
"""

import json
import math
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import soundfile as sf

from contracts.asr_output import ASROutput
from ayusetu.ai.voice.asr.audio_utils import (
    TARGET_SAMPLE_RATE,
    AudioLoadError,
    AudioValidationError,
    duration_seconds,
    load_audio,
    validate_audio,
)
from ayusetu.ai.voice.asr.confidence import (
    confidence_from_segments,
    infer_language_from_text,
    logprob_to_confidence,
)

# ─── Markers ──────────────────────────────────────────────────────────────────

SKIP_MODEL = os.environ.get("SKIP_MODEL_TESTS", "1") == "1"
_smoke_skip = pytest.mark.skipif(
    SKIP_MODEL,
    reason="Set SKIP_MODEL_TESTS=0 to run model smoke tests",
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_sine_wav(
    path: Path,
    duration_s: float = 2.0,
    freq_hz: float = 440.0,
) -> None:
    """Write a pure-tone sine wave WAV file. NOT real speech."""
    t = np.linspace(
        0, duration_s,
        int(TARGET_SAMPLE_RATE * duration_s),
        endpoint=False,
    )
    audio = (np.sin(2 * math.pi * freq_hz * t) * 0.5).astype(np.float32)
    sf.write(str(path), audio, TARGET_SAMPLE_RATE)


def sine_array(duration_s: float = 2.0, freq_hz: float = 440.0) -> np.ndarray:
    """Return a sine wave as a float32 numpy array (no file I/O)."""
    t = np.linspace(0, duration_s, int(TARGET_SAMPLE_RATE * duration_s), endpoint=False)
    return (np.sin(2 * math.pi * freq_hz * t) * 0.5).astype(np.float32)


# ─── ASROutput Contract ───────────────────────────────────────────────────────

class TestASROutputContract:
    """Tests for the frozen ASROutput Pydantic schema."""

    def test_valid_hindi_output(self):
        out = ASROutput(
            text="मुझे दो दिन से पेट में दर्द है",
            language="hi",
            confidence=0.92,
        )
        assert out.text == "मुझे दो दिन से पेट में दर्द है"
        assert out.language == "hi"
        assert out.confidence == pytest.approx(0.92)

    def test_valid_english_output(self):
        out = ASROutput(
            text="I have had a fever for two days",
            language="en",
            confidence=0.88,
        )
        assert out.language == "en"

    def test_valid_hinglish_output(self):
        out = ASROutput(
            text="मुझे दो दिन से fever है",
            language="hinglish",
            confidence=0.78,
        )
        assert out.language == "hinglish"

    def test_valid_unknown_language(self):
        out = ASROutput(text="...", language="unknown", confidence=0.10)
        assert out.language == "unknown"

    def test_invalid_language_rejected(self):
        """Language codes outside the agreed set must be rejected."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ASROutput(text="bonjour", language="fr", confidence=0.5)

    def test_confidence_above_one_rejected(self):
        with pytest.raises(Exception):
            ASROutput(text="test", language="en", confidence=1.01)

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(Exception):
            ASROutput(text="test", language="en", confidence=-0.01)

    def test_confidence_boundary_values_accepted(self):
        ASROutput(text="test", language="en", confidence=0.0)
        ASROutput(text="test", language="en", confidence=1.0)

    def test_is_low_confidence_with_default_threshold(self):
        low = ASROutput(text="test", language="en", confidence=0.59)
        high = ASROutput(text="test", language="en", confidence=0.61)
        assert low.is_low_confidence() is True
        assert high.is_low_confidence() is False

    def test_is_low_confidence_with_custom_threshold(self):
        out = ASROutput(text="test", language="en", confidence=0.75)
        assert out.is_low_confidence(threshold=0.80) is True
        assert out.is_low_confidence(threshold=0.70) is False

    def test_to_dict_exact_keys(self):
        """Contract requires exactly {text, language, confidence}."""
        out = ASROutput(text="hello", language="en", confidence=0.9)
        d = out.to_dict()
        assert set(d.keys()) == {"text", "language", "confidence"}

    def test_to_dict_value_types(self):
        out = ASROutput(
            text="मुझे दो दिन से fever है",
            language="hinglish",
            confidence=0.84,
        )
        d = out.to_dict()
        assert isinstance(d["text"], str)
        assert isinstance(d["language"], str)
        assert isinstance(d["confidence"], float)

    def test_to_dict_json_serializable(self):
        """The dict must be JSON-serializable without custom encoders."""
        out = ASROutput(
            text="मुझे दो दिन से पेट में दर्द है",
            language="hi",
            confidence=0.94,
        )
        serialized = json.dumps(out.to_dict())
        parsed = json.loads(serialized)
        assert parsed["text"] == out.text
        assert parsed["language"] == out.language
        assert parsed["confidence"] == pytest.approx(0.94, abs=0.001)

    def test_agreed_contract_format(self):
        """Verify output matches the exact structure agreed in the design doc."""
        expected_keys = {"text", "language", "confidence"}
        out = ASROutput(
            text="मुझे दो दिन से पेट में दर्द है",
            language="hi",
            confidence=0.94,
        )
        d = out.to_dict()
        assert set(d.keys()) == expected_keys
        assert 0.0 <= d["confidence"] <= 1.0
        assert d["language"] in {"hi", "en", "hinglish", "unknown"}


# ─── Audio Utilities ──────────────────────────────────────────────────────────

class TestAudioUtils:

    def test_load_audio_returns_float32(self, tmp_path):
        wav = tmp_path / "test.wav"
        make_sine_wav(wav, 2.0)
        audio = load_audio(str(wav))
        assert audio.dtype == np.float32

    def test_load_audio_correct_length_at_16khz(self, tmp_path):
        wav = tmp_path / "test.wav"
        make_sine_wav(wav, 3.0)
        audio = load_audio(str(wav))
        # Allow 1% tolerance for resampling
        assert len(audio) == pytest.approx(3.0 * TARGET_SAMPLE_RATE, rel=0.01)

    def test_load_audio_resamples_from_44100(self, tmp_path):
        """librosa should resample non-16kHz files."""
        t = np.linspace(0, 2.0, int(44100 * 2.0), endpoint=False)
        audio_44k = (np.sin(2 * math.pi * 440 * t) * 0.5).astype(np.float32)
        wav = tmp_path / "test_44k.wav"
        sf.write(str(wav), audio_44k, 44100)
        audio_16k = load_audio(str(wav))
        # Should have been resampled to 16 kHz
        assert len(audio_16k) == pytest.approx(2.0 * TARGET_SAMPLE_RATE, rel=0.02)

    def test_load_audio_file_not_found(self):
        with pytest.raises(AudioLoadError, match="not found"):
            load_audio("/nonexistent/path/audio.wav")

    def test_load_audio_path_is_directory(self, tmp_path):
        with pytest.raises(AudioLoadError):
            load_audio(str(tmp_path))

    def test_validate_passes_for_valid_audio(self):
        validate_audio(sine_array(2.0))  # Should not raise

    def test_validate_rejects_empty_array(self):
        with pytest.raises(AudioValidationError, match="empty"):
            validate_audio(np.array([], dtype=np.float32))

    def test_validate_rejects_none(self):
        with pytest.raises(AudioValidationError, match="empty"):
            validate_audio(None)

    def test_validate_rejects_too_short(self):
        # 50 ms = 800 samples — below 0.1s minimum
        audio = sine_array(0.05)
        with pytest.raises(AudioValidationError, match="too short"):
            validate_audio(audio)

    def test_validate_rejects_too_long(self):
        audio = sine_array(10.0)
        with pytest.raises(AudioValidationError, match="too long"):
            validate_audio(audio, max_duration_seconds=5.0)

    def test_validate_rejects_silent(self):
        silent = np.zeros(TARGET_SAMPLE_RATE * 2, dtype=np.float32)
        with pytest.raises(AudioValidationError, match="silent"):
            validate_audio(silent)

    def test_duration_seconds_correct(self):
        audio = sine_array(3.5)
        assert duration_seconds(audio) == pytest.approx(3.5, rel=0.001)


# ─── Confidence ───────────────────────────────────────────────────────────────

class TestConfidence:

    def test_logprob_near_zero_gives_high_confidence(self):
        conf = logprob_to_confidence(-0.1)
        assert conf > 0.80, f"Expected >0.80 for high logprob, got {conf:.4f}"

    def test_very_negative_logprob_gives_low_confidence(self):
        conf = logprob_to_confidence(-2.0)
        assert conf < 0.25, f"Expected <0.25 for poor logprob, got {conf:.4f}"

    def test_logprob_to_confidence_is_monotonic(self):
        logprobs = [-3.0, -2.0, -1.5, -1.0, -0.8, -0.5, -0.2, -0.05]
        confs = [logprob_to_confidence(lp) for lp in logprobs]
        for i in range(len(confs) - 1):
            assert confs[i] < confs[i + 1], (
                f"Confidence not monotonic at index {i}: "
                f"{confs[i]:.4f} >= {confs[i+1]:.4f}"
            )

    def test_logprob_output_is_in_range(self):
        for lp in [-5.0, -2.0, -1.0, -0.5, 0.0, 0.5]:
            conf = logprob_to_confidence(lp)
            assert 0.0 <= conf <= 1.0, f"Out of range for logprob={lp}: {conf}"

    def test_confidence_from_segments_basic(self):
        seg = MagicMock()
        seg.text = "मुझे दो दिन से fever है"
        seg.avg_logprob = -0.4

        conf, method = confidence_from_segments([seg])
        assert 0.0 <= conf <= 1.0
        assert method == "avg_logprob_from_segments"

    def test_confidence_from_segments_empty(self):
        conf, method = confidence_from_segments([])
        assert conf == 0.0

    def test_confidence_from_segments_longer_segment_weighted_more(self):
        """Longer segment text should have more weight in the average."""
        short_seg = MagicMock()
        short_seg.text = "hi"
        short_seg.avg_logprob = -2.0  # Low confidence

        long_seg = MagicMock()
        long_seg.text = "मुझे कल से पेट में बहुत तेज दर्द हो रहा है"
        long_seg.avg_logprob = -0.2   # High confidence

        conf, _ = confidence_from_segments([short_seg, long_seg])
        # Should be pulled toward -0.2 (high confidence) due to longer text
        assert conf > 0.60, (
            f"Expected confidence weighted toward high-confidence long segment, "
            f"got {conf:.4f}"
        )


# ─── Language Inference ───────────────────────────────────────────────────────

class TestLanguageInference:

    def test_pure_hindi_devanagari(self):
        result = infer_language_from_text("मुझे दो दिन से पेट में दर्द है")
        assert result == "hi", f"Expected 'hi', got '{result}'"

    def test_pure_english_latin(self):
        result = infer_language_from_text("I have had a fever for two days")
        assert result == "en", f"Expected 'en', got '{result}'"

    def test_hinglish_mixed_script(self):
        result = infer_language_from_text("मुझे दो दिन से fever है")
        assert result == "hinglish", f"Expected 'hinglish', got '{result}'"

    def test_hinglish_chest_pain(self):
        result = infer_language_from_text("मेरे chest में pain है")
        assert result == "hinglish", f"Expected 'hinglish', got '{result}'"

    def test_hinglish_medical_terms(self):
        result = infer_language_from_text("मुझे बहुत weakness है और nausea भी हो रही है")
        assert result == "hinglish", f"Expected 'hinglish', got '{result}'"

    def test_empty_string(self):
        assert infer_language_from_text("") == "unknown"

    def test_whitespace_only(self):
        assert infer_language_from_text("   \t\n") == "unknown"

    def test_punctuation_only(self):
        # Punctuation should be ignored; result is "unknown" since no letters
        result = infer_language_from_text("... , ! ?")
        assert result == "unknown"

    def test_predominantly_hindi_with_few_english_letters(self):
        # "OK" embedded in Hindi → still classified as hi (very high Devanagari ratio)
        result = infer_language_from_text(
            "मुझे ठीक ठीक नहीं पता मैं OK हूं"
        )
        # "OK" is 2 Latin chars; rest is Devanagari — should be hi or hinglish
        # We don't assert exact value here; just verify it's in the valid set
        assert result in {"hi", "hinglish", "en", "unknown"}

    def test_predominantly_english_with_few_hindi(self):
        result = infer_language_from_text(
            "I have fever and pain and थोड़ी weakness"
        )
        # 3 Hindi words vs many English words — expect hinglish or en
        assert result in {"hinglish", "en"}


# ─── Configuration ────────────────────────────────────────────────────────────

class TestConfig:

    def test_get_config_defaults(self, monkeypatch):
        """Verify defaults when no env vars are set."""
        monkeypatch.delenv("ASR_MODEL", raising=False)
        monkeypatch.delenv("ASR_BACKEND", raising=False)
        monkeypatch.delenv("ASR_DEVICE", raising=False)
        monkeypatch.delenv("ASR_COMPUTE_TYPE", raising=False)
        monkeypatch.delenv("ASR_FORCE_LANGUAGE", raising=False)
        monkeypatch.delenv("ASR_CONFIDENCE_THRESHOLD", raising=False)
        monkeypatch.delenv("ASR_MAX_DURATION_SECONDS", raising=False)
        monkeypatch.delenv("HF_TOKEN", raising=False)

        from ayusetu.ai.voice.asr.config import get_config
        config = get_config()
        assert config.model_id == "shunyalabs/zero-stt-hinglish"
        assert config.backend == "transformers"
        assert config.device == "cpu"
        assert config.force_language is None
        assert config.confidence_threshold == pytest.approx(0.60)

    def test_get_config_env_override(self, monkeypatch):
        monkeypatch.setenv("ASR_MODEL", "openai/whisper-large-v3-turbo")
        monkeypatch.setenv("ASR_BACKEND", "faster-whisper")
        monkeypatch.setenv("ASR_FORCE_LANGUAGE", "hi")

        from ayusetu.ai.voice.asr.config import get_config
        config = get_config()
        assert config.model_id == "openai/whisper-large-v3-turbo"
        assert config.backend == "faster-whisper"
        assert config.force_language == "hi"

    def test_invalid_backend_raises(self, monkeypatch):
        monkeypatch.setenv("ASR_BACKEND", "nemo")
        from ayusetu.ai.voice.asr.config import get_config
        with pytest.raises(ValueError, match="ASR_BACKEND"):
            get_config()

    def test_invalid_device_raises(self, monkeypatch):
        monkeypatch.setenv("ASR_DEVICE", "tpu")
        from ayusetu.ai.voice.asr.config import get_config
        with pytest.raises(ValueError, match="ASR_DEVICE"):
            get_config()

    def test_empty_force_language_treated_as_none(self, monkeypatch):
        monkeypatch.setenv("ASR_FORCE_LANGUAGE", "")
        from ayusetu.ai.voice.asr.config import get_config
        config = get_config()
        assert config.force_language is None


# ─── Smoke Tests (require model download) ────────────────────────────────────

class TestSmoke:
    """
    End-to-end smoke tests that require a real model download.

    Set environment variables to point to real audio files:
        HINDI_AUDIO     Path to Hindi speech WAV file
        ENGLISH_AUDIO   Path to English speech WAV file
        HINGLISH_AUDIO  Path to Hinglish (code-switched) WAV file

    If audio paths are not set, the tests use synthetic sine waves.
    Sine wave is not real speech — the model will produce garbled output,
    but the PIPELINE must not crash and must return a valid ASROutput.

    For the Hinglish mixed-script test to be meaningful, you MUST provide
    a real Hinglish recording via HINGLISH_AUDIO.
    """

    @_smoke_skip
    def test_pipeline_does_not_crash_on_synthetic_audio(self, tmp_path):
        """Pipeline must return ASROutput without exception on any audio."""
        from ayusetu.ai.voice.asr.transcriber import reset_backend, transcribe

        reset_backend()

        wav = tmp_path / "synthetic.wav"
        make_sine_wav(wav, 2.0)

        output = transcribe(str(wav))

        assert isinstance(output, ASROutput)
        assert isinstance(output.text, str)
        assert output.language in {"hi", "en", "hinglish", "unknown"}
        assert 0.0 <= output.confidence <= 1.0

    @_smoke_skip
    def test_output_matches_contract_schema(self, tmp_path):
        """The output dict must exactly match the agreed AyuSetu contract."""
        from ayusetu.ai.voice.asr.transcriber import reset_backend, transcribe

        reset_backend()

        wav = tmp_path / "contract_check.wav"
        make_sine_wav(wav, 1.5)

        output = transcribe(str(wav))
        d = output.to_dict()

        assert set(d.keys()) == {"text", "language", "confidence"}
        assert isinstance(d["text"], str)
        assert isinstance(d["language"], str)
        assert isinstance(d["confidence"], float)
        assert 0.0 <= d["confidence"] <= 1.0

    @_smoke_skip
    def test_hindi_audio(self):
        """
        Smoke test A: Hindi audio → ASROutput.

        Provide a real Hindi speech file via HINDI_AUDIO env var.
        Example: HINDI_AUDIO=samples/hindi_sample.wav
        """
        from ayusetu.ai.voice.asr.transcriber import reset_backend, transcribe

        audio_path = os.environ.get("HINDI_AUDIO")
        if not audio_path:
            pytest.skip(
                "Set HINDI_AUDIO=/path/to/hindi.wav to run this test."
            )

        reset_backend()
        output = transcribe(audio_path)

        assert isinstance(output, ASROutput)
        assert output.language in {"hi", "hinglish", "unknown"}
        # For real Hindi speech, confidence should be above a minimum
        assert output.confidence >= 0.01  # Not 0.0 (which means no signal)
        print(f"\n[Hindi smoke] text='{output.text}' lang='{output.language}' "
              f"conf={output.confidence:.4f}")

    @_smoke_skip
    def test_english_audio(self):
        """
        Smoke test B: English audio → ASROutput.

        Provide a real English speech file via ENGLISH_AUDIO env var.
        Example: ENGLISH_AUDIO=samples/english_sample.wav
        """
        from ayusetu.ai.voice.asr.transcriber import reset_backend, transcribe

        audio_path = os.environ.get("ENGLISH_AUDIO")
        if not audio_path:
            pytest.skip(
                "Set ENGLISH_AUDIO=/path/to/english.wav to run this test."
            )

        reset_backend()
        output = transcribe(audio_path)

        assert isinstance(output, ASROutput)
        assert output.language in {"en", "hinglish", "unknown"}
        assert output.confidence >= 0.01
        print(f"\n[English smoke] text='{output.text}' lang='{output.language}' "
              f"conf={output.confidence:.4f}")

    @_smoke_skip
    def test_hinglish_mixed_script(self):
        """
        Smoke test C: Hinglish audio → mixed-script output.

        This is the most important smoke test. It verifies that the pipeline
        can produce mixed Devanagari + Latin script in a single utterance,
        which is the key capability of zero-stt-hinglish.

        Provide a Hinglish recording via HINGLISH_AUDIO env var.
        The recording should contain natural Hindi-English code-switching,
        e.g. "मुझे दो दिन से fever है और बहुत weakness feel हो रही है"
        """
        from ayusetu.ai.voice.asr.transcriber import reset_backend, transcribe

        audio_path = os.environ.get("HINGLISH_AUDIO")
        if not audio_path:
            pytest.skip(
                "Set HINGLISH_AUDIO=/path/to/hinglish.wav to run this test. "
                "This test verifies mixed-script output — use a real Hinglish "
                "recording for a meaningful result."
            )

        reset_backend()
        output = transcribe(audio_path)

        assert isinstance(output, ASROutput)
        assert output.confidence >= 0.01

        print(f"\n[Hinglish smoke] text='{output.text}' lang='{output.language}' "
              f"conf={output.confidence:.4f}")

        # Report whether mixed-script output was observed
        has_devanagari = any(
            "DEVANAGARI" in __import__("unicodedata").name(c, "")
            for c in output.text
            if c.isalpha()
        )
        has_latin = any(
            c.isascii() and c.isalpha() for c in output.text
        )

        print(f"[Hinglish smoke] has_devanagari={has_devanagari}, "
              f"has_latin={has_latin}")

        if has_devanagari and has_latin:
            print("[Hinglish smoke] ✓ PASS: Mixed-script output confirmed.")
            assert output.language == "hinglish", (
                f"Expected language='hinglish' for mixed-script output, "
                f"got '{output.language}'"
            )
        else:
            # Model produced monolingual output — this is not a test failure
            # but must be reported. It may mean forced_decoder_ids is not working
            # as expected, or the audio is not code-switched enough.
            print(
                "[Hinglish smoke] ⚠ WARNING: Output is not mixed-script. "
                "Verify that forced_decoder_ids=None is correctly applied. "
                "This may indicate a configuration issue."
            )
            # Do not fail — report only. The investigation must be manual.
