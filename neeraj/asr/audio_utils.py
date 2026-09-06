"""
AyuSetu AI — Audio Utilities
==============================
Load, validate, and normalize audio files for ASR input.

All audio entering the ASR pipeline is normalized to:
  - Sample rate: 16 000 Hz (required by Whisper-family models)
  - Channels:    Mono (single channel)
  - Dtype:       float32

Supported input formats: WAV, MP3, FLAC, OGG (via librosa + soundfile).

Exceptions
----------
    AudioLoadError      File not found, unreadable, or unsupported format.
    AudioValidationError Audio fails duration or amplitude checks.
"""

import logging
from pathlib import Path
from typing import Union

import librosa
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

# All Whisper-family models require 16 kHz mono input.
TARGET_SAMPLE_RATE: int = 16_000

# Minimum and absolute maximum durations (seconds).
_MIN_DURATION_S: float = 0.1
_SILENCE_PEAK_THRESHOLD: float = 1e-4  # Below this → warn but don't reject


class AudioLoadError(Exception):
    """Raised when an audio file cannot be opened or decoded."""


class AudioValidationError(Exception):
    """Raised when audio fails a validation check."""


def load_audio(path: Union[str, Path]) -> np.ndarray:
    """
    Load an audio file and return a 16 kHz mono float32 array.

    Args:
        path: Path to the audio file. Must exist and be a supported format.

    Returns:
        np.ndarray of shape ``(num_samples,)``, dtype float32, at 16 kHz.

    Raises:
        AudioLoadError: File not found, unreadable, or unsupported format.
    """
    path = Path(path)
    if not path.exists():
        raise AudioLoadError(f"Audio file not found: '{path}'")
    if not path.is_file():
        raise AudioLoadError(f"Path is not a file: '{path}'")

    try:
        audio, sr = librosa.load(
            str(path),
            sr=TARGET_SAMPLE_RATE,  # librosa resamples automatically
            mono=True,              # Down-mix to mono if stereo
        )
        audio = audio.astype(np.float32)
        logger.debug(
            "Loaded audio: file='%s', samples=%d, duration=%.2fs",
            path.name,
            len(audio),
            len(audio) / TARGET_SAMPLE_RATE,
        )
        return audio
    except AudioLoadError:
        raise
    except Exception as exc:
        raise AudioLoadError(
            f"Failed to load '{path.name}': {exc}"
        ) from exc


def validate_audio(
    audio: np.ndarray,
    max_duration_seconds: float = 120.0,
) -> None:
    """
    Validate a loaded audio array before sending it to the ASR model.

    Checks
    ------
    1. Array is not None or empty.
    2. Duration >= 0.1 seconds.
    3. Duration <= max_duration_seconds.
    4. Audio is not completely silent (all-zero signal).

    Low-amplitude (but non-zero) audio triggers a warning only.

    Args:
        audio: float32 numpy array at 16 kHz.
        max_duration_seconds: Reject audio longer than this.

    Raises:
        AudioValidationError: If any hard check fails.
    """
    if audio is None or audio.size == 0:
        raise AudioValidationError("Audio array is empty.")

    dur = duration_seconds(audio)

    if dur < _MIN_DURATION_S:
        raise AudioValidationError(
            f"Audio too short: {dur:.3f}s "
            f"(minimum is {_MIN_DURATION_S}s)."
        )

    if dur > max_duration_seconds:
        raise AudioValidationError(
            f"Audio too long: {dur:.1f}s "
            f"(maximum is {max_duration_seconds}s). "
            "Split the recording into shorter segments."
        )

    if np.all(audio == 0.0):
        raise AudioValidationError(
            "Audio is completely silent (all-zero signal). "
            "Check microphone connection or recording setup."
        )

    peak = float(np.max(np.abs(audio)))
    if peak < _SILENCE_PEAK_THRESHOLD:
        logger.warning(
            "Audio amplitude is very low (peak=%.6f). "
            "Transcription quality may be poor. "
            "Consider increasing microphone gain.",
            peak,
        )


def duration_seconds(audio: np.ndarray) -> float:
    """
    Return audio duration in seconds.

    Assumes the array was loaded at TARGET_SAMPLE_RATE (16 000 Hz).

    Args:
        audio: float32 numpy array.

    Returns:
        Duration in seconds (float).
    """
    return len(audio) / TARGET_SAMPLE_RATE
