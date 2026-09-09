"""
AyuSetu AI — ASR Transcriber (Public API)
==========================================
This is the ONLY module that external code should import from.

All other modules (Sai's clinical extraction, conversation engine, etc.)
interact with the ASR module through a single function:

    from ayusetu.ai.voice.asr.transcriber import transcribe
    output: ASROutput = transcribe("path/to/audio.wav")

Internal modules (model.py, audio_utils.py, confidence.py, config.py)
are implementation details and should NOT be imported by external code.

Backend loading
---------------
The model is loaded lazily on the first call to ``transcribe()``.
Subsequent calls reuse the loaded singleton — no re-loading.
Use ``reset_backend()`` if you need to switch models (e.g., in tests).
"""

import logging
from pathlib import Path
from typing import Optional, Union

from contracts.asr_output import ASROutput
from ayusetu.ai.voice.asr.audio_utils import (
    AudioLoadError,
    AudioValidationError,
    duration_seconds,
    load_audio,
    validate_audio,
)
from ayusetu.ai.voice.asr.confidence import (
    confidence_from_segments,
    confidence_from_token_scores,
    infer_language_from_text,
)
from ayusetu.ai.voice.asr.config import ASRConfig, get_config
from ayusetu.ai.voice.asr.model import (
    BaseASRBackend,
    ModelLoadError,
    TranscriptionError,
    create_backend,
)

logger = logging.getLogger(__name__)

# ─── Module-level singleton ───────────────────────────────────────────────────
# The backend (model) is loaded once and shared across all calls.
_backend: Optional[BaseASRBackend] = None
_active_config: Optional[ASRConfig] = None


def _get_or_load_backend(config: ASRConfig) -> BaseASRBackend:
    """
    Return the loaded backend. Load it if not already loaded or if config changed.

    Args:
        config: ASRConfig to use.

    Returns:
        A loaded BaseASRBackend instance.

    Raises:
        ModelLoadError: If model initialization fails.
    """
    global _backend, _active_config

    # Reload if backend hasn't been created or config has changed
    if _backend is None or _active_config != config:
        if _backend is not None:
            logger.info(
                "ASR config changed — reinitializing backend "
                "(old model: '%s', new model: '%s').",
                _active_config.model_id if _active_config else "none",
                config.model_id,
            )
        else:
            logger.info(
                "First transcribe() call — loading backend "
                "(model='%s', backend='%s', device='%s').",
                config.model_id,
                config.backend,
                config.device,
            )

        backend = create_backend(config)
        backend.load()
        _backend = backend
        _active_config = config

    return _backend


# ─── Public API ───────────────────────────────────────────────────────────────

def transcribe(
    audio_path: Union[str, Path],
    config: Optional[ASRConfig] = None,
) -> ASROutput:
    """
    Transcribe a push-to-talk audio recording and return structured output.

    This is the primary public API for the AyuSetu ASR module.
    Accepts a path to a recorded audio file (WAV, MP3, FLAC, or OGG)
    and returns an ASROutput containing the transcription, language code,
    and a confidence score.

    Processing pipeline
    -------------------
    1. Load and resample audio to 16 kHz mono (audio_utils.load_audio)
    2. Validate audio duration and amplitude (audio_utils.validate_audio)
    3. Run ASR inference (model.TransformersBackend or FasterWhisperBackend)
    4. Compute confidence from token scores or segment avg_logprob (confidence.py)
    5. Infer language from text script composition (confidence.infer_language_from_text)
    6. Assemble and validate the ASROutput contract (contracts.asr_output.ASROutput)

    Args:
        audio_path: Path to the audio file. Must exist and be readable.
        config:     Optional ASRConfig override. If None, reads from environment
                    variables (see ayusetu.ai/asr/config.py and .env.example).

    Returns:
        ASROutput with fields:
            text       - Transcribed text (may be mixed Devanagari + Latin)
            language   - "hi", "en", "hinglish", or "unknown"
            confidence - Float in [0.0, 1.0]; method depends on backend

    Raises:
        AudioLoadError:       File not found or unreadable.
        AudioValidationError: Audio too short, too long, or silent.
        ModelLoadError:       ASR model failed to load (download issue, etc.).
        TranscriptionError:   Inference failed.

    Example
    -------
        >>> from ayusetu.ai.voice.asr.transcriber import transcribe
        >>> output = transcribe("recordings/patient_01.wav")
        >>> print(output.to_dict())
        {"text": "मुझे दो दिन से fever है", "language": "hinglish", "confidence": 0.84}
    """
    if config is None:
        config = get_config()

    audio_path = Path(audio_path)

    # ── 1. Load audio ─────────────────────────────────────────────────────────
    logger.debug("Starting transcription: file='%s'", audio_path.name)
    audio = load_audio(audio_path)

    # ── 2. Validate audio ─────────────────────────────────────────────────────
    validate_audio(audio, max_duration_seconds=config.max_duration_seconds)
    logger.debug("Audio valid: duration=%.2fs", duration_seconds(audio))

    # ── 3. Run inference ──────────────────────────────────────────────────────
    backend = _get_or_load_backend(config)
    raw = backend.transcribe(audio)

    # ── 4. Compute confidence ─────────────────────────────────────────────────
    confidence: float
    method: str

    if (
        raw.confidence_method == "avg_logprob_from_token_scores"
        and raw.token_scores is not None
        and raw.chosen_ids is not None
        and len(raw.token_scores) > 0
    ):
        confidence, method = confidence_from_token_scores(
            raw.token_scores, raw.chosen_ids
        )

    elif (
        raw.confidence_method == "avg_logprob_from_segments"
        and raw.segments
        and all(s.avg_logprob is not None for s in raw.segments)
    ):
        confidence, method = confidence_from_segments(raw.segments)

    else:
        # No confidence signal available from this backend output.
        # This should not happen in normal operation — investigate if seen.
        confidence = 0.0
        method = "unavailable"
        logger.warning(
            "No confidence signal available (method='%s', backend='%s'). "
            "Confidence set to 0.0. Investigate backend output.",
            raw.confidence_method,
            config.backend,
        )

    logger.debug("Confidence: value=%.4f, method='%s'", confidence, method)

    # ── 5. Determine language ─────────────────────────────────────────────────
    # Strategy: use model-detected language as a starting point, but override
    # with "hinglish" if the text contains a mix of scripts. This handles the
    # case where the model reports a monolingual code but zero-stt-hinglish
    # has produced mixed-script output.

    heuristic_lang = infer_language_from_text(raw.text)

    if heuristic_lang == "hinglish":
        # Mixed script detected — this is the key Hinglish case.
        # Trust the text composition over the model's language token.
        language = "hinglish"
        if raw.detected_language and raw.detected_language != "hinglish":
            logger.debug(
                "Mixed-script text detected despite model reporting language='%s'. "
                "Using 'hinglish'.",
                raw.detected_language,
            )
    elif raw.detected_language in {"hi", "en"}:
        # Model reported a clean language and text confirms it.
        language = raw.detected_language
    else:
        # Fall back to heuristic for "unknown" or unrecognised model output.
        language = heuristic_lang

    # ── 6. Assemble contract ──────────────────────────────────────────────────
    output = ASROutput(
        text=raw.text,
        language=language,
        confidence=round(confidence, 4),
    )

    # Log operational summary with ZERO-PHI
    logger.info(
        "Transcription done: language='%s', confidence=%.4f, "
        "backend='%s', method='%s'",
        output.language,
        output.confidence,
        config.backend,
        method,
    )

    if output.is_low_confidence(config.confidence_threshold):
        logger.warning(
            "Low-confidence result: %.4f < threshold %.4f. "
            "Consider re-prompting the patient.",
            output.confidence,
            config.confidence_threshold,
        )

    return output


def reset_backend() -> None:
    """
    Force the backend to be reloaded on the next ``transcribe()`` call.

    Use this when switching models between test runs or when you have
    changed ASR_MODEL in the environment.
    """
    global _backend, _active_config
    if _backend is not None:
        logger.info(
            "Resetting ASR backend (current model: '%s').",
            _active_config.model_id if _active_config else "unknown",
        )
    _backend = None
    _active_config = None
