import os
import logging
from typing import Optional
from .base import TTSProvider
from .config import TTSConfig, get_config
from .chatterbox import ChatterboxTTS
from .indic import IndicF5TTSProvider

logger = logging.getLogger(__name__)

def get_tts_provider(config: Optional[TTSConfig] = None) -> TTSProvider:
    """
    Factory function to retrieve configured TTS provider based on environment.

    Environment variable:
        TTS_BACKEND="chatterbox" (default) | "indic" | "indic-f5"
    """
    backend = os.getenv("TTS_BACKEND", "chatterbox").lower().strip()
    cfg = config or get_config()

    if backend in {"indic", "indic-f5", "ai4bharat/indicf5"}:
        logger.info("[TTSFactory] Selected Indic-native TTS provider: IndicF5TTSProvider")
        return IndicF5TTSProvider(cfg)
    else:
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
