"""
AyuSetu AI — ASR Configuration
================================
All runtime configuration is read from environment variables.
No model IDs, device settings, or thresholds are hard-coded anywhere else.

To switch models (e.g., for evaluation), change ASR_MODEL in .env.
The rest of the codebase reads config.model_id — zero changes needed.

Usage
-----
    from ayusetu.ai.asr.config import get_config
    config = get_config()
    print(config.model_id)          # shunyalabs/zero-stt-hinglish
    print(config.backend)           # transformers

Environment variables
---------------------
    ASR_MODEL                   HuggingFace model ID
    ASR_BACKEND                 "transformers" or "faster-whisper"
    ASR_DEVICE                  "cpu" or "cuda"
    ASR_COMPUTE_TYPE            "int8", "float16", or "float32"
    ASR_FORCE_LANGUAGE          Leave empty for zero-stt-hinglish.
                                Set to "hi" for ARTPARK vaani-hindi.
    ASR_CONFIDENCE_THRESHOLD    Float 0.0–1.0 (default 0.60)
    ASR_MAX_DURATION_SECONDS    Float, default 120.0
    HF_TOKEN                    HuggingFace access token (never log)
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from the project root (three levels up from this file:
# ayusetu.ai/asr/config.py → ayusetu.ai/asr/ → ayusetu.ai/ → project root)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=_ENV_FILE, override=False)

_VALID_BACKENDS = {"transformers", "faster-whisper"}
_VALID_DEVICES = {"cpu", "cuda"}
_VALID_COMPUTE_TYPES = {"int8", "float16", "float32"}


@dataclass(frozen=True)
class ASRConfig:
    """
    Immutable ASR runtime configuration.

    Frozen dataclass: values cannot change after construction.
    Create a new instance to change configuration.
    """

    # --- Model ---
    model_id: str
    """HuggingFace model ID or local path. Example: 'shunyalabs/zero-stt-hinglish'"""

    backend: str
    """Inference backend. One of: 'transformers', 'faster-whisper'"""

    # --- Hardware ---
    device: str
    """Compute device. One of: 'cpu', 'cuda'"""

    compute_type: str
    """Quantization level. One of: 'int8', 'float16', 'float32'"""

    # --- Language ---
    force_language: Optional[str]
    """
    If set, forces a specific decoder language token.

    CRITICAL: For shunyalabs/zero-stt-hinglish, leave as None.
    Setting this to 'hi' or 'en' forces monolingual decoding and will
    suppress the mixed-script (Hinglish) output the model is designed for.

    For ARTPARK-IISc/whisper-large-v3-vaani-hindi: set to 'hi' (per model card).
    For openai/whisper-large-v3-turbo baseline: leave as None.
    """

    # --- Quality ---
    confidence_threshold: float
    """Utterances below this threshold are flagged as low-confidence."""

    max_duration_seconds: float
    """Maximum audio file duration. Files exceeding this are rejected."""

    # --- Auth ---
    hf_token: Optional[str]
    """HuggingFace token for private/gated model access. Never log this."""


def get_config() -> ASRConfig:
    """
    Build and return an ASRConfig from environment variables.

    Raises
    ------
    ValueError
        If a required environment variable has an invalid value.
    """
    model_id = os.environ.get("ASR_MODEL", "shunyalabs/zero-stt-hinglish").strip()
    if not model_id:
        raise ValueError("ASR_MODEL must not be empty.")

    backend = os.environ.get("ASR_BACKEND", "transformers").strip()
    if backend not in _VALID_BACKENDS:
        raise ValueError(
            f"ASR_BACKEND='{backend}' is not valid. "
            f"Must be one of: {sorted(_VALID_BACKENDS)}"
        )

    device = os.environ.get("ASR_DEVICE", "cpu").strip()
    if device not in _VALID_DEVICES:
        raise ValueError(
            f"ASR_DEVICE='{device}' is not valid. "
            f"Must be one of: {sorted(_VALID_DEVICES)}"
        )

    compute_type = os.environ.get("ASR_COMPUTE_TYPE", "int8").strip()
    if compute_type not in _VALID_COMPUTE_TYPES:
        raise ValueError(
            f"ASR_COMPUTE_TYPE='{compute_type}' is not valid. "
            f"Must be one of: {sorted(_VALID_COMPUTE_TYPES)}"
        )

    # Language forcing: empty string or unset → None (no forcing)
    _force_lang_raw = os.environ.get("ASR_FORCE_LANGUAGE", "").strip()
    force_language: Optional[str] = _force_lang_raw if _force_lang_raw else None

    try:
        confidence_threshold = float(
            os.environ.get("ASR_CONFIDENCE_THRESHOLD", "0.60")
        )
        if not (0.0 <= confidence_threshold <= 1.0):
            raise ValueError("Must be in [0.0, 1.0].")
    except ValueError as exc:
        raise ValueError(
            f"ASR_CONFIDENCE_THRESHOLD is invalid: {exc}"
        ) from exc

    try:
        max_duration = float(os.environ.get("ASR_MAX_DURATION_SECONDS", "120.0"))
        if max_duration <= 0:
            raise ValueError("Must be positive.")
    except ValueError as exc:
        raise ValueError(
            f"ASR_MAX_DURATION_SECONDS is invalid: {exc}"
        ) from exc

    _hf_raw = os.environ.get("HF_TOKEN", "").strip()
    hf_token: Optional[str] = _hf_raw if _hf_raw else None

    return ASRConfig(
        model_id=model_id,
        backend=backend,
        device=device,
        compute_type=compute_type,
        force_language=force_language,
        confidence_threshold=confidence_threshold,
        max_duration_seconds=max_duration,
        hf_token=hf_token,
    )
