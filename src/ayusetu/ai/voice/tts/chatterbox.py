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


DEVANAGARI_TO_ROMAN_MAP = {
    # Vowels
    'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u', 'ऊ': 'oo', 'ऋ': 'ri',
    'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au', 'अं': 'an', 'अः': 'ah',
    # Vowel signs (Matras)
    'ा': 'aa', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo', 'ृ': 'ri',
    'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ं': 'n', 'ः': 'h', 'ँ': 'n',
    # Consonants
    'क': 'ka', 'ख': 'kha', 'ग': 'ga', 'घ': 'gha', 'ङ': 'nga',
    'च': 'cha', 'छ': 'chha', 'ज': 'ja', 'झ': 'jha', 'ञ': 'nya',
    'ट': 'ta', 'ठ': 'tha', 'ड': 'da', 'ढ': 'dha', 'ण': 'na',
    'त': 'ta', 'थ': 'tha', 'द': 'da', 'ध': 'dha', 'न': 'na',
    'प': 'pa', 'फ': 'pha', 'ब': 'ba', 'भ': 'bha', 'म': 'ma',
    'य': 'ya', 'र': 'ra', 'ल': 'la', 'व': 'va', 'श': 'sha', 'ष': 'sha', 'स': 'sa', 'ह': 'ha',
    'क्ष': 'ksha', 'त्र': 'tra', 'ज्ञ': 'gya',
    'ड़': 'ra', 'ढ़': 'rha', 'फ़': 'fa', 'ज़': 'za', 'ख़': 'kha', 'ग़': 'gha', 'क़': 'qa',
    '्': '', # Halant removes inherent vowel
}

HINDI_WORD_OVERRIDES = {
    'नमस्ते': 'namaste',
    'समझ': 'samajh',
    'गया': 'gaya',
    'कृपया': 'kripya',
    'आगे': 'aage',
    'बताएं': 'batayein',
    'बताए': 'bataye',
    'बताइए': 'bataiye',
    'दर्द': 'dard',
    'पेट': 'pet',
    'दिन': 'din',
    'दो': 'do',
    'से': 'se',
    'में': 'mein',
    'हो': 'ho',
    'रहा': 'raha',
    'रही': 'rahi',
    'रहे': 'rahe',
    'है': 'hai',
    'हैं': 'hain',
    'मुझे': 'mujhe',
    'आपको': 'aapko',
    'क्या': 'kya',
    'कब': 'kab',
    'कहां': 'kahan',
    'कैसे': 'kaise',
    'कहा': 'kaha',
    'डॉक्टर': 'doctor',
    'दवा': 'dawa',
    'दवाई': 'dawai',
    'बुखार': 'bukhar',
    'खांसी': 'khansi',
    'उल्टी': 'ulti',
    'चक्कर': 'chakkar',
    'छाती': 'chhati',
    'सिर': 'sir',
}

def transliterate_devanagari_to_roman(text: str) -> str:
    """Convert Devanagari text to Romanized script for Chatterbox TTS compatibility."""
    if not text:
        return text

    has_devanagari = any('\u0900' <= char <= '\u097f' for char in text)
    if not has_devanagari:
        return text

    words = text.split()
    processed_words = []
    for w in words:
        clean_w = w.strip('.,!?।;:""\'()')
        punc_suffix = w[len(clean_w):] if len(clean_w) < len(w) else ''
        punc_prefix = w[:w.find(clean_w)] if clean_w in w and w.find(clean_w) > 0 else ''

        if clean_w in HINDI_WORD_OVERRIDES:
            transliterated = HINDI_WORD_OVERRIDES[clean_w]
            processed_words.append(f"{punc_prefix}{transliterated}{punc_suffix}")
        else:
            res = []
            i = 0
            n = len(clean_w)
            consonants = {
                'क', 'ख', 'ग', 'घ', 'ङ', 'च', 'छ', 'ज', 'झ', 'ञ',
                'ट', 'ठ', 'ड', 'ढ', 'ण', 'त', 'थ', 'द', 'ध', 'न',
                'प', 'फ', 'ब', 'भ', 'म', 'य', 'र', 'ल', 'व', 'श', 'ष', 'स', 'ह',
                'क्ष', 'त्र', 'ज्ञ', 'ड़', 'ढ़', 'फ़', 'ज़', 'ख़', 'ग़', 'क़'
            }
            vowel_matras = {'ा', 'ि', 'ी', 'ु', 'ू', 'ृ', 'े', 'ै', 'ो', 'ौ', '्'}

            while i < n:
                char = clean_w[i]
                if not ('\u0900' <= char <= '\u097f'):
                    res.append(char)
                    i += 1
                    continue
                if i + 1 < n and clean_w[i:i+2] in DEVANAGARI_TO_ROMAN_MAP:
                    char = clean_w[i:i+2]
                    i += 1

                if char in consonants:
                    base = DEVANAGARI_TO_ROMAN_MAP.get(char, char)
                    next_char = clean_w[i + 1] if i + 1 < n else None
                    if next_char in vowel_matras:
                        if base.endswith('a'):
                            base = base[:-1]
                    elif next_char is None:
                        if base.endswith('a') and len(base) > 1 and base not in {'ka', 'na', 'to', 'ho', 'ja', 'se', 'me'}:
                            base = base[:-1]
                    res.append(base)
                elif char in DEVANAGARI_TO_ROMAN_MAP:
                    res.append(DEVANAGARI_TO_ROMAN_MAP[char])
                else:
                    res.append(char)
                i += 1
            processed_words.append(f"{punc_prefix}{''.join(res)}{punc_suffix}")

    output_text = " ".join(processed_words)
    output_text = output_text.replace('।', '.')
    return output_text


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
        # Convert any Devanagari Hindi text to Romanized script before tokenization
        prompt_text = transliterate_devanagari_to_roman(text)

        try:
            torch_audio = self._model.generate(prompt_text)
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
            "[TTSDiag] Real speech synthesis completed: input text len: %d (prompt len: %d), provider: %s, output sample rate: %d, output channels: 1, output sample count: %d, output duration before WAV encoding: %.3fs",
            len(text),
            len(prompt_text),
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
