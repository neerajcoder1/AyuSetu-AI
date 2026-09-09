import logging
import sys
from unittest.mock import MagicMock, patch

# Ensure missing optional audio packages don't prevent test execution in platform env
if "librosa" not in sys.modules:
    sys.modules["librosa"] = MagicMock()
if "soundfile" not in sys.modules:
    sys.modules["soundfile"] = MagicMock()

import pytest

from ayusetu.ai.voice.asr.config import ASRConfig, get_config
from ayusetu.ai.voice.asr.model import RawSegment, RawTranscriptionResult


@pytest.fixture(autouse=True)
def mock_audio_deps():
    """Mock audio file loading and validation to isolate transcriber logging logic."""
    import numpy as np
    dummy_audio = np.zeros(16000, dtype=np.float32)

    with patch("ayusetu.ai.voice.asr.transcriber.load_audio", return_value=dummy_audio), \
         patch("ayusetu.ai.voice.asr.transcriber.validate_audio", return_value=None):
        yield


def test_asr_transcribe_zero_phi_logging(caplog):
    """
    Verify that confidential patient transcript text is NOT leaked in application logs.
    """
    from ayusetu.ai.voice.asr.transcriber import transcribe

    secret_transcript = "PATIENT_SECRET_TRANSCRIPT_9F42: Patient discloses severe pain and ABHA 99-8877-6655"
    
    mock_backend = MagicMock()
    mock_backend.transcribe.return_value = RawTranscriptionResult(
        text=secret_transcript,
        segments=[RawSegment(text=secret_transcript, avg_logprob=-0.15, start=0.0, end=2.5)],
        token_scores=None,
        chosen_ids=None,
        detected_language="en",
        confidence_method="avg_logprob_from_segments",
    )

    config = get_config()

    caplog.set_level(logging.DEBUG)

    with patch("ayusetu.ai.voice.asr.transcriber._get_or_load_backend", return_value=mock_backend):
        output = transcribe("fake_audio_path.wav", config=config)

    # 1. Functional assertion: ASROutput contains the actual text for downstream processing
    assert output.text == secret_transcript
    assert output.language == "en"
    assert output.confidence > 0.8

    # 2. Strict Zero-PHI Logging Assertions:
    # Secret transcript must NEVER appear in emitted logs
    assert "PATIENT_SECRET_TRANSCRIPT_9F42" not in caplog.text
    assert "ABHA 99-8877-6655" not in caplog.text
    assert "text_preview" not in caplog.text

    # 3. Safe operational metadata must still be recorded
    assert "Transcription done" in caplog.text
    assert "language='en'" in caplog.text
    assert "backend='transformers'" in caplog.text
    assert "confidence=" in caplog.text
    assert "method='avg_logprob_from_segments'" in caplog.text
