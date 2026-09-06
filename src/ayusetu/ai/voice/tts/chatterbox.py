
import numpy as np
import torch
from typing import Optional

from contracts.tts_result import TTSResult
from .base import TTSProvider
from .config import TTSConfig, get_config

# Import the Chatterbox implementation from the current Python environment.
# The package should be installed in the active environment.

try:
    from chatterbox.tts import ChatterboxTTS as _ChatterboxTTS  # type: ignore
except Exception as e:
    raise ImportError(
        "Chatterbox package could not be imported. Ensure the isolated TTS "
        "benchmark environment is activated and the package is installed."
    ) from e


class ChatterboxTTS(TTSProvider):
    """Chatterbox TTS provider implementation.

    This class follows the TTSProvider protocol and returns a TTSResult instance.
    Configuration (model identifier, device etc.) is read from TTSConfig which pulls
    values from environment variables with sensible defaults.
    """
    _cached_model: Optional[object] = None
    _cached_device: Optional[str] = None


    def __init__(self, config: Optional[TTSConfig] = None) -> None:
        cfg = config or get_config()
        # Load model only once per device; reuse cached instance if possible.
        if self.__class__._cached_model is None or self.__class__._cached_device != cfg.device:
            self.__class__._cached_model = _ChatterboxTTS.from_pretrained(device=cfg.device)
            self.__class__._cached_device = cfg.device
        self._model = self.__class__._cached_model
        # The underlying class stores the sample rate on ``sr``.
        self._sample_rate: int = getattr(self._model, "sr", 24000)

    def synthesize(self, text: str, language: str) -> TTSResult:
        """Generate speech for *text* in *language*.

        Parameters
        ----------
        text: str
            The raw text to be spoken.
        language: str
            Language identifier (e.g. `"hi"`, `"en"` or `"hinglish"`).
            The current Chatterbox model does not require an explicit language
            argument, but we keep it in the contract for consistency.

        Returns
        -------
        TTSResult
            A contract object containing the audio waveform, sample rate,
            duration, and the language tag.
        """
        # The Chatterbox implementation expects ``generate`` to be called on
        # the model instance.  It returns a ``torch.Tensor`` with shape
        # ``(1, n_samples)``.
        try:
            torch_audio = self._model.generate(text)
        except Exception as exc:
            raise RuntimeError(f"Chatterbox synthesis failed: {exc}") from exc

        # Ensure the tensor is on CPU and convert to a NumPy array.
        if isinstance(torch_audio, torch.Tensor):
            audio_np = torch_audio.squeeze(0).cpu().numpy()
        else:
            audio_np = np.array(torch_audio)

        duration = float(len(audio_np) / self._sample_rate)
        return TTSResult(
            audio=audio_np,
            sample_rate=self._sample_rate,
            duration=duration,
            language=language,
        )
