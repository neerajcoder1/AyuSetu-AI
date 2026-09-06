import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class TTSConfig:
    """Configuration for TTS providers.

    Reads from environment variables. Allows overriding via constructor for tests.
    """
    model_id: str = os.getenv("TTS_MODEL_ID", "ResembleAI/chatterbox")
    device: str = os.getenv("TTS_DEVICE", "cpu")
    # Additional generation parameters could be added here (e.g., temperature)

def get_config() -> TTSConfig:
    """Return a TTSConfig instance.

    In production this reads environment variables; tests can monkey‑patch them
    or instantiate TTSConfig directly.
    """
    return TTSConfig()
