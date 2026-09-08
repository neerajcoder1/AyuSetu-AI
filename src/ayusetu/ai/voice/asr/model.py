"""
AyuSetu AI — ASR Model Backend
================================
Wraps two ASR inference backends behind a common interface.

Backends
--------
TransformersBackend ("transformers")
    Uses HuggingFace ``transformers`` library with
    ``WhisperForConditionalGeneration`` directly.
    Works with models distributed in standard HuggingFace format.
    This is the DEFAULT and RECOMMENDED backend for Phase 1.

    Confidence: computed from per-step token logits (output_scores=True).
    Language token: cleared via generate kwargs so zero-stt-hinglish can
                    produce mixed-script output.

FasterWhisperBackend ("faster-whisper")
    Uses the ``faster_whisper`` library (CTranslate2 engine).
    Requires the model weights to be pre-converted to CTranslate2 format:

        ct2-transformers-converter \\
            --model shunyalabs/zero-stt-hinglish \\
            --output_dir ./models/zero-stt-ct2 \\
            --quantization int8

    IMPORTANT: Always run the Hinglish smoke test after conversion.
    CTranslate2 conversion may affect code-switching token generation.
    If the smoke test fails (output is monolingual), fall back to
    the transformers backend for Phase 1 and document the issue.

    Confidence: from segment avg_logprob (direct, reliable).

Switching backends
------------------
Set ``ASR_BACKEND=transformers`` or ``ASR_BACKEND=faster-whisper`` in .env.
No code changes required.

License notice
--------------
The default model (shunyalabs/zero-stt-hinglish) is released under OpenRAIL.
See LICENSE_ATTRIBUTION.md in the repository root for full attribution and
usage terms. Do not assume commercial deployment rights.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ayusetu.ai.voice.asr.config import ASRConfig

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE: int = 16_000


# ─── Exceptions ───────────────────────────────────────────────────────────────

class ModelLoadError(Exception):
    """Raised when the ASR model cannot be initialized."""


class TranscriptionError(Exception):
    """Raised when inference fails."""


# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class RawSegment:
    """A single transcription segment from the ASR backend."""

    text: str
    avg_logprob: Optional[float]  # None if not available from this backend
    start: Optional[float]        # Segment start time in seconds (or None)
    end: Optional[float]          # Segment end time in seconds (or None)


@dataclass
class RawTranscriptionResult:
    """
    Raw output from an ASR backend, before ASROutput contract assembly.

    The ``confidence_method`` field tells transcriber.py which confidence
    estimation function to call.
    """

    text: str
    """Full concatenated transcription text."""

    segments: list[RawSegment] = field(default_factory=list)
    """Segment-level results (for faster-whisper; single entry for transformers)."""

    token_scores: Optional[list] = None
    """
    Per-step logit tensors from transformers generate(output_scores=True).
    Shape per element: (1, vocab_size). None for faster-whisper.
    """

    chosen_ids: Optional[list] = None
    """
    Token IDs chosen at each generation step (parallel to token_scores).
    None for faster-whisper.
    """

    detected_language: Optional[str] = None
    """Language code detected by the model (e.g. 'hi', 'en'). May be None."""

    confidence_method: str = "unavailable"
    """
    Which confidence method to use in confidence.py:
        "avg_logprob_from_segments"   → confidence_from_segments()
        "avg_logprob_from_token_scores" → confidence_from_token_scores()
        "unavailable"                 → no signal; confidence = 0.0
    """


# ─── Abstract base ────────────────────────────────────────────────────────────

class BaseASRBackend(ABC):
    """Common interface for all ASR backends."""

    @abstractmethod
    def load(self) -> None:
        """Download (if needed) and initialize the model."""
        ...

    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> RawTranscriptionResult:
        """
        Transcribe audio and return raw results.

        Args:
            audio: float32 numpy array at 16 kHz, shape (num_samples,).

        Returns:
            RawTranscriptionResult.

        Raises:
            TranscriptionError on inference failure.
        """
        ...

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """True if the model is loaded and ready for inference."""
        ...


# ─── Transformers backend ─────────────────────────────────────────────────────

class TransformersBackend(BaseASRBackend):
    """
    HuggingFace Transformers backend for Whisper-family models.

    Uses WhisperForConditionalGeneration directly (not the high-level
    pipeline) so that:
      1. forced_decoder_ids can be set to None for code-switching.
      2. Per-step logit scores are accessible for genuine confidence estimation.

    Model card note
    ---------------
    The shunyalabs/zero-stt-hinglish model card example mistakenly
    references ``model="shunya-labs/hinglish-whisper-medium"``. The
    correct HuggingFace repo ID is ``shunyalabs/zero-stt-hinglish``.
    This backend always uses ``config.model_id`` — do not copy the example.
    """

    def __init__(self, config: ASRConfig) -> None:
        self._config = config
        self._model = None
        self._processor = None
        self._loaded: bool = False

    def load(self) -> None:
        """Download and initialize the WhisperForConditionalGeneration model."""
        try:
            import torch
            from transformers import WhisperForConditionalGeneration, WhisperProcessor
        except ImportError as exc:
            raise ModelLoadError(
                "Required packages missing for 'transformers' backend. "
                "Run: pip install transformers torch"
            ) from exc

        logger.info(
            "Loading '%s' via transformers (device=%s, compute_type=%s)...",
            self._config.model_id,
            self._config.device,
            self._config.compute_type,
        )

        hf_kwargs: dict = {}
        if self._config.hf_token:
            hf_kwargs["token"] = self._config.hf_token

        # Load processor (tokenizer + feature extractor)
        try:
            self._processor = WhisperProcessor.from_pretrained(
                self._config.model_id, **hf_kwargs
            )
            logger.debug("WhisperProcessor loaded for '%s'.", self._config.model_id)
        except Exception as exc:
            raise ModelLoadError(
                f"Cannot load WhisperProcessor for '{self._config.model_id}': {exc}. "
                "Verify the model ID is correct. "
                "Note: the model card example uses a wrong ID. "
                "The correct ID is 'shunyalabs/zero-stt-hinglish'."
            ) from exc

        # Determine torch dtype from compute_type
        try:
            import torch
            _dtype_map = {
                "float32": torch.float32,
                "float16": torch.float16,
                "int8": torch.float32,  # Transformers uses float32 internally; int8 is BitsAndBytes
            }
            torch_dtype = _dtype_map.get(self._config.compute_type, torch.float32)
        except Exception:
            torch_dtype = None  # Will use default

        # Load model weights
        try:
            load_kwargs: dict = {**hf_kwargs}
            if torch_dtype is not None:
                load_kwargs["torch_dtype"] = torch_dtype

            # Load base Whisper model
            self._model = WhisperForConditionalGeneration.from_pretrained(
                self._config.model_id,
                **load_kwargs,
            )
            # Move model to device
            self._model = self._model.to(self._config.device)
            # Optional PEFT LoRA adapter loading
            from ayusetu.ai.voice.asr.config import get_adapter_path
            adapter_path = get_adapter_path()
            if adapter_path is not None:
                try:
                    from peft import PeftModel
                    self._model = PeftModel.from_pretrained(self._model, str(adapter_path))
                    logger.info("Loaded PEFT adapter from %s", adapter_path)
                except Exception as exc:
                    raise ModelLoadError(
                        f"Failed to load PEFT adapter from '{adapter_path}': {exc}"
                    ) from exc
            # Set model to eval mode
            self._model.eval()
            logger.debug(
                "WhisperForConditionalGeneration loaded and moved to '%s'.",
                self._config.device,
            )
        except Exception as exc:
            raise ModelLoadError(
                f"Cannot load WhisperForConditionalGeneration "
                f"for '{self._config.model_id}': {exc}"
            ) from exc

        logger.info(
            "Model '%s' ready on device '%s'.",
            self._config.model_id,
            self._config.device,
        )
        self._loaded = True

    def transcribe(self, audio: np.ndarray) -> RawTranscriptionResult:
        """Run Whisper inference and return raw results with token scores."""
        if not self._loaded:
            raise TranscriptionError(
                "Model not loaded. Call load() before transcribe()."
            )

        import torch

        try:
            # ── Step 1: Extract log-mel features ────────────────────────────
            inputs = self._processor(
                audio,
                sampling_rate=TARGET_SAMPLE_RATE,
                return_tensors="pt",
            )
            input_features = inputs.input_features.to(self._config.device)

            # ── Step 2: Build generation kwargs ─────────────────────────────
            gen_kwargs: dict = {
                "output_scores": True,
                "return_dict_in_generate": True,
            }

            if self._config.force_language:
                # Force a specific language token (e.g. "hi" for vaani-hindi)
                forced_ids = self._processor.get_decoder_prompt_ids(
                    language=self._config.force_language,
                    task="transcribe",
                )
                gen_kwargs["forced_decoder_ids"] = forced_ids
                logger.debug(
                    "Forcing language token: '%s'", self._config.force_language
                )
            else:
                # CRITICAL for zero-stt-hinglish:
                # Removing forced_decoder_ids allows the model to generate its
                # own language token and produce mixed-script (Hinglish) output.
                # Clearing suppress_tokens prevents suppressing non-task tokens.
                gen_kwargs["forced_decoder_ids"] = None
                gen_kwargs["suppress_tokens"] = []
                logger.debug(
                    "No language forced: forced_decoder_ids=None, "
                    "suppress_tokens=[] (required for Hinglish output)."
                )

            # ── Step 3: Generate ─────────────────────────────────────────────
            with torch.no_grad():
                outputs = self._model.generate(input_features, **gen_kwargs)

            # ── Step 4: Decode text ──────────────────────────────────────────
            full_text = self._processor.batch_decode(
                outputs.sequences, skip_special_tokens=True
            )[0].strip()

            # ── Step 5: Extract token scores for confidence ──────────────────
            # outputs.scores: tuple of (batch=1, vocab_size) tensors per step
            # outputs.sequences: (batch=1, prompt_len + output_len) token IDs
            token_scores: Optional[list] = None
            chosen_ids: Optional[list] = None
            confidence_method = "unavailable"

            if outputs.scores:
                token_scores = list(outputs.scores)
                # Chosen token IDs are the generated tokens after the prompt.
                # The prompt (SOT, lang, task, no-timestamps) occupies the
                # first few positions in sequences; generated tokens follow.
                prompt_len = len(outputs.sequences[0]) - len(outputs.scores)
                generated_ids = outputs.sequences[0][prompt_len:].tolist()
                chosen_ids = generated_ids
                confidence_method = "avg_logprob_from_token_scores"
                logger.debug(
                    "Token scores extracted: %d steps, prompt_len=%d.",
                    len(token_scores),
                    prompt_len,
                )

            # ── Step 6: Attempt to detect language from generated tokens ─────
            detected_language = self._detect_language_token(outputs.sequences[0])

            # ── Step 7: Build single-segment result ──────────────────────────
            segment = RawSegment(
                text=full_text,
                avg_logprob=None,   # Not available per-segment from transformers
                start=None,
                end=None,
            )

            return RawTranscriptionResult(
                text=full_text,
                segments=[segment],
                token_scores=token_scores,
                chosen_ids=chosen_ids,
                detected_language=detected_language,
                confidence_method=confidence_method,
            )

        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError(
                f"Transcription failed for model '{self._config.model_id}': {exc}"
            ) from exc

    def _detect_language_token(self, sequence_ids) -> Optional[str]:
        """
        Inspect the first few generated tokens for a Whisper language token.

        Whisper places the language token immediately after the
        start-of-transcript (SOT) token. We scan the first 5 token IDs
        for known language markers.

        Returns the language code (e.g. 'hi', 'en') or None.
        """
        try:
            tokens = self._processor.tokenizer.convert_ids_to_tokens(
                sequence_ids[:8].tolist()
            )
            for tok in tokens:
                if tok and tok.startswith("<|") and tok.endswith("|>"):
                    lang = tok[2:-2]
                    # Only return recognised single-language codes
                    if len(lang) == 2 and lang.isalpha():
                        logger.debug(
                            "Detected language token from model: '%s'", lang
                        )
                        return lang
        except Exception:
            pass
        return None

    @property
    def is_loaded(self) -> bool:
        return self._loaded


# ─── faster-whisper backend ───────────────────────────────────────────────────

class FasterWhisperBackend(BaseASRBackend):
    """
    faster-whisper (CTranslate2) backend.

    SETUP REQUIRED — Convert the model before use:

        pip install ctranslate2
        ct2-transformers-converter \\
            --model shunyalabs/zero-stt-hinglish \\
            --output_dir ./models/zero-stt-ct2 \\
            --quantization int8

    Then set in .env:
        ASR_BACKEND=faster-whisper
        ASR_MODEL=./models/zero-stt-ct2

    IMPORTANT: After conversion, run:
        pytest tests/test_asr.py::TestSmoke::test_hinglish_mixed_script
    to verify that mixed-script (Hinglish) output is preserved.
    If the test fails, use the transformers backend instead.

    Confidence: direct from segment avg_logprob (most reliable source).
    """

    def __init__(self, config: ASRConfig) -> None:
        self._config = config
        self._model = None
        self._loaded: bool = False

    def load(self) -> None:
        """Load the CTranslate2 Whisper model."""
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ModelLoadError(
                "faster-whisper is not installed. "
                "Run: pip install faster-whisper"
            ) from exc

        logger.info(
            "Loading '%s' via faster-whisper (device=%s, compute_type=%s)...",
            self._config.model_id,
            self._config.device,
            self._config.compute_type,
        )

        try:
            self._model = WhisperModel(
                self._config.model_id,
                device=self._config.device,
                compute_type=self._config.compute_type,
            )
        except Exception as exc:
            raise ModelLoadError(
                f"Cannot load faster-whisper model '{self._config.model_id}': {exc}. "
                "If this model was not pre-converted to CTranslate2 format, "
                "run ct2-transformers-converter first, then set ASR_MODEL "
                "to the output directory path."
            ) from exc

        logger.info(
            "faster-whisper model '%s' ready.", self._config.model_id
        )
        self._loaded = True

    def transcribe(self, audio: np.ndarray) -> RawTranscriptionResult:
        """Run faster-whisper inference."""
        if not self._loaded:
            raise TranscriptionError(
                "Model not loaded. Call load() before transcribe()."
            )

        try:
            transcribe_kwargs: dict = {
                "condition_on_previous_text": False,
                "beam_size": 5,
            }

            if self._config.force_language:
                transcribe_kwargs["language"] = self._config.force_language
                logger.debug(
                    "Forcing language: '%s'", self._config.force_language
                )
            else:
                # Do not pass language at all.
                # For zero-stt-hinglish converted to CTranslate2:
                # this should allow mixed-script output.
                # VERIFY with smoke test after conversion.
                logger.debug(
                    "No language forced for faster-whisper transcription."
                )

            segments_gen, info = self._model.transcribe(audio, **transcribe_kwargs)
            segments = list(segments_gen)  # Materialize lazy generator

            full_text = " ".join(seg.text.strip() for seg in segments).strip()

            raw_segments = [
                RawSegment(
                    text=seg.text,
                    avg_logprob=seg.avg_logprob,
                    start=seg.start,
                    end=seg.end,
                )
                for seg in segments
            ]

            detected_language = getattr(info, "language", None)

            return RawTranscriptionResult(
                text=full_text,
                segments=raw_segments,
                token_scores=None,
                chosen_ids=None,
                detected_language=detected_language,
                confidence_method="avg_logprob_from_segments",
            )

        except TranscriptionError:
            raise
        except Exception as exc:
            raise TranscriptionError(
                f"faster-whisper transcription failed: {exc}"
            ) from exc

    @property
    def is_loaded(self) -> bool:
        return self._loaded


# ─── Factory ──────────────────────────────────────────────────────────────────

def create_backend(config: ASRConfig) -> BaseASRBackend:
    """
    Create and return the backend specified by ``config.backend``.

    The returned backend is NOT yet loaded — call ``.load()`` before use.

    Args:
        config: ASRConfig instance.

    Returns:
        An unloaded BaseASRBackend subclass instance.

    Raises:
        ValueError: If ``config.backend`` is not a known value.
    """
    if config.backend == "transformers":
        return TransformersBackend(config)
    elif config.backend == "faster-whisper":
        return FasterWhisperBackend(config)
    else:
        raise ValueError(
            f"Unknown backend: '{config.backend}'. "
            "Valid options: 'transformers', 'faster-whisper'."
        )
