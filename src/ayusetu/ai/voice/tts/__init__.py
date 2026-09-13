import os
import logging
from typing import Optional
from .base import TTSProvider
from .config import TTSConfig, get_config

logger = logging.getLogger(__name__)

# Lazy import of optional ChatterboxTTS backend. If unavailable, define a placeholder that raises informative error when instantiated.
try:
    from .chatterbox import ChatterboxTTS
except Exception as e:
    logger.error(f"Failed to import ChatterboxTTS at module load: {e}")
    class ChatterboxTTS:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Chatterbox TTS backend is not installed. Install 'chatterbox-tts' to use this provider."
            )



def get_tts_provider(config: Optional[TTSConfig] = None) -> TTSProvider:
    """
    Factory function to retrieve configured TTS provider based on environment.

    Environment variable:
        TTS_BACKEND="chatterbox" (default) | "indic" | "indic-f5"
    """
    backend = os.getenv("TTS_BACKEND", "chatterbox").lower().strip()
    cfg = config or get_config()

    if backend in {"indic", "indic-f5", "ai4bharat/indicf5"}:
        try:
            from .indic import IndicF5TTSProvider
        except Exception as e:
            logger.error(f"Failed to import IndicF5TTSProvider: {e}")
            raise
        logger.info("[TTSFactory] Selected Indic-native TTS provider: IndicF5TTSProvider")
        return IndicF5TTSProvider(cfg)
    else:
        # Try to import ChatterboxTTS lazily; if unavailable, provide a placeholder that raises informative error.
        try:
            from .chatterbox import ChatterboxTTS
        except Exception as e:
            logger.error(f"Failed to import ChatterboxTTS: {e}")
            class _MissingChatterboxTTS:
                def __init__(self, *args, **kwargs):
                    raise ImportError(
                        "Chatterbox TTS backend is not installed. Install 'chatterbox-tts' to use this provider."
                    )
            ChatterboxTTS = _MissingChatterboxTTS
        logger.info("[TTSFactory] Selected default TTS provider: ChatterboxTTS")
        return ChatterboxTTS(cfg)

__all__ = [
    "TTSProvider",
    "TTSConfig",
    "get_config",
    "ChatterboxTTS",
    "IndicF5TTSProvider",
    "get_tts_provider",
]
