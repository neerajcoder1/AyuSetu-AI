from typing import Protocol
from contracts.tts_result import TTSResult

class TTSProvider(Protocol):
    """Provider‑agnostic interface for TTS synthesis.

    Implementations must implement ``synthesize`` returning a :class:`TTSResult`.
    """

    def synthesize(self, text: str, language: str) -> TTSResult:
        """Generate speech for *text* in *language*.

        Returns a ``TTSResult`` containing audio, sample_rate, duration and language.
        """
        ...
