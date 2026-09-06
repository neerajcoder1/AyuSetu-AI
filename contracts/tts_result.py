from pydantic import BaseModel, Field
from typing import Any

class TTSResult(BaseModel):
    """Contract for TTS synthesis output.

    Contains the raw audio waveform (as a NumPy array or bytes), the sample
    rate, duration in seconds, and the language code of the synthesized text.
    Additional fields can be added later if needed.
    """

    audio: Any = Field(..., description="Audio waveform, e.g., a NumPy array or raw bytes.")
    sample_rate: int = Field(..., description="Sample rate of the audio in Hz.")
    duration: float = Field(..., description="Audio duration in seconds.")
    language: str = Field(..., description="Language identifier (hi, en, hinglish, ...)")
