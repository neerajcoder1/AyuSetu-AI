import sys
import os
import logging
import numpy as np
import torch
from typing import Optional

from contracts.tts_result import TTSResult
from .base import TTSProvider
from .config import TTSConfig, get_config

logger = logging.getLogger(__name__)


def _load_real_chatterbox_class():
    """
    Import the real ``chatterbox-tts`` package from Python site-packages,
    bypassing local workspace directory collisions with ``chatterbox/``.
    """
    cwd = os.path.abspath(os.getcwd())
    orig_path = sys.path[:]
    try:
        # Exclude workspace root directory from sys.path to force site-packages lookup
        sys.path = [p for p in sys.path if os.path.abspath(p or ".") != cwd]
        # Purge local mock from sys.modules if present
        if "chatterbox" in sys.modules and getattr(sys.modules["chatterbox"], "__file__", "").startswith(cwd):
            del sys.modules["chatterbox"]
        if "chatterbox.tts" in sys.modules and getattr(sys.modules["chatterbox.tts"], "__file__", "").startswith(cwd):
            del sys.modules["chatterbox.tts"]
        from chatterbox.tts import ChatterboxTTS as _RealChatterboxTTS  # type: ignore
        return _RealChatterboxTTS
    except Exception as exc:
        raise ImportError(
            "Real Chatterbox TTS package could not be imported from site-packages. "
            "Ensure chatterbox-tts is installed in the active environment."
        ) from exc
    finally:
        sys.path = orig_path


_ChatterboxTTS = _load_real_chatterbox_class()


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
        """Generate real intelligible speech for *text* in *language*.

        Parameters
        ----------
        text: str
            The raw text to be spoken.
        language: str
            Language identifier (e.g. `"hi"`, `"en"` or `"hinglish"`).

        Returns
        -------
        TTSResult
            A contract object containing the audio waveform, sample rate,
            duration, and the language tag.
        """
        try:
            torch_audio = self._model.generate(text)
        except Exception as exc:
            raise RuntimeError(f"Chatterbox real speech synthesis failed: {exc}") from exc

        # Ensure the tensor is on CPU and convert to a NumPy array.
        if isinstance(torch_audio, torch.Tensor):
            audio_np = torch_audio.squeeze(0).cpu().numpy()
        else:
            audio_np = np.array(torch_audio)

        duration = float(len(audio_np) / self._sample_rate)

        # Fail clearly if output audio is empty or zero-duration
        if len(audio_np) == 0 or duration <= 0.0:
            raise RuntimeError("Chatterbox TTS returned 0 samples or invalid duration.")

        logger.info(
            "[TTSDiag] Real speech synthesis completed: input text len: %d, provider: %s, output sample rate: %d, output channels: 1, output sample count: %d, output duration before WAV encoding: %.3fs",
            len(text),
            self.__class__.__name__,
            self._sample_rate,
            len(audio_np),
            duration,
        )

        return TTSResult(
            audio=audio_np,
            sample_rate=self._sample_rate,
            duration=duration,
            language=language,
        )
