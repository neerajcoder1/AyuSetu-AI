import sys
import os
import logging
import numpy as np
import torch
from typing import Optional
import requests
import base64

from contracts.tts_result import TTSResult
from .base import TTSProvider
from .config import TTSConfig, get_config

logger = logging.getLogger(__name__)

DEVANAGARI_TO_ROMAN_MAP = {
    # Vowels
    '?': 'a', '?': 'aa', '?': 'i', '?': 'ee', '?': 'u', '?': 'oo', '?': 'ri',
    '?': 'e', '?': 'ai', '?': 'o', '?': 'au', '??': 'an', '??': 'ah',
    # Vowel signs (Matras)
    '?': 'aa', '?': 'i', '?': 'ee', '?': 'u', '?': 'oo', '?': 'ri',
    '?': 'e', '?': 'ai', '?': 'o', '?': 'au', '?': 'n', '?': 'h', '?': 'n',
    # Consonants
    '?': 'ka', '?': 'kha', '?': 'ga', '?': 'gha', '?': 'nga',
    '?': 'cha', '?': 'chha', '?': 'ja', '?': 'jha', '?': 'nya',
    '?': 'ta', '?': 'tha', '?': 'da', '?': 'dha', '?': 'na',
    '?': 'ta', '?': 'tha', '?': 'da', '?': 'dha', '?': 'na',
    '?': 'pa', '?': 'pha', '?': 'ba', '?': 'bha', '?': 'ma',
    '?': 'ya', '?': 'ra', '?': 'la', '?': 'va', '?': 'sha', '?': 'sha', '?': 'sa', '?': 'ha',
    '???': 'ksha', '???': 'tra', '???': 'gya',
    '??': 'ra', '??': 'rha', '??': 'fa', '??': 'za', '??': 'kha', '??': 'gha', '??': 'qa',
    '?': '', # Halant removes inherent vowel
}

HINDI_WORD_OVERRIDES = {
    '??????': 'namaste',
    '???': 'samajh',
    '???': 'gaya',
    '?????': 'kripya',
    '???': 'aage',
    '?????': 'batayein',
    '????': 'bataye',
    '?????': 'bataiye',
    '????': 'dard',
    '???': 'pet',
    '???': 'din',
    '??': 'do',
    '??': 'se',
    '???': 'mein',
    '??': 'ho',
    '???': 'raha',
    '???': 'rahi',
    '???': 'rahe',
    '??': 'hai',
    '???': 'hain',
    '????': 'mujhe',
    '????': 'aapko',
    '????': 'kya',
    '??': 'kab',
    '????': 'kahan',
    '????': 'kaise',
    '???': 'kaha',
    '??????': 'doctor',
    '???': 'dawa',
    '????': 'dawai',
    '?????': 'bukhar',
    '?????': 'khansi',
    '?????': 'ulti',
    '?????': 'chakkar',
    '????': 'chhati',
    '???': 'sir',
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
        clean_w = w.strip('.,!? ?;:""\'()')
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
                '?', '?', '?', '?', '?', '?', '?', '?', '?', '?',
                '?', '?', '?', '?', '?', '?', '?', '?', '?', '?',
                '?', '?', '?', '?', '?', '?', '?', '?', '?', '?', '?', '?', '?',
                '???', '???', '???', '??', '??', '??', '??', '??', '??', '??'
            }
            vowel_matras = {'?', '?', '?', '?', '?', '?', '?', '?', '?', '?', '?'}

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
    output_text = output_text.replace('?', '.')
    return output_text


class ChatterboxTTS(TTSProvider):
    """Chatterbox TTS provider implementation connecting to local dedicated service."""
    
    def __init__(self, config: Optional[TTSConfig] = None) -> None:
        pass

    def synthesize(self, text: str, language: str) -> TTSResult:
        prompt_text = transliterate_devanagari_to_roman(text)
        
        try:
            resp = requests.post(
                "http://localhost:8001/synthesize",
                json={"text": prompt_text, "language": language},
                timeout=180
            )
            resp.raise_for_status()
            data = resp.json()
            audio_bytes = base64.b64decode(data["audio_b64"])
            audio_np = np.frombuffer(audio_bytes, dtype=np.float32)
            
            logger.info(f"[TTSDiag] Local Chatterbox Service synthesis completed. {len(audio_np)} samples.")
            
            return TTSResult(
                audio=audio_np,
                sample_rate=data["sample_rate"],
                duration=data["duration"],
                language=language,
            )
        except Exception as exc:
            logger.warning(f"Failed to connect to local Chatterbox TTS service: {exc}")
            raise NotImplementedError(f"Chatterbox service synthesis failed: {exc}") from exc
