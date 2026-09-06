"""
AyuSetu AI — ASR Output Contract
==================================
Shared data contract between:
  - Neeraj's ASR module (producer)
  - Sai's clinical extraction, red-flag, and summary modules (consumers)

Schema is FROZEN. Do not modify without team agreement.

Contract version: 1.0
Last agreed: 2026-09-06
"""

from pydantic import BaseModel, Field, field_validator


class ASROutput(BaseModel):
    """
    Structured output from the AyuSetu ASR pipeline.

    This is the ONLY data structure that crosses the boundary between the
    ASR module (Neeraj) and the clinical modules (Sai). All fields are
    required — never None.

    Fields
    ------
    text : str
        Raw transcribed text. May contain mixed Devanagari and Latin script
        for Hindi-English code-switched (Hinglish) utterances.
        Examples:
            "मुझे दो दिन से पेट में दर्द है"         (pure Hindi)
            "I have had a fever for two days"          (pure English)
            "मुझे दो दिन से fever है"                  (Hinglish)

    language : str
        Inferred language code. One of:
            "hi"      → Primarily Hindi (Devanagari script)
            "en"      → Primarily English (Latin script)
            "hinglish"   → Hindi-English code-switched (Hinglish / mixed script)
            "unknown" → Script composition could not be determined

    confidence : float
        Utterance-level transcription confidence in [0.0, 1.0].

        IMPORTANT: This value is backend-dependent and is NOT a calibrated
        probability. Use only for deciding whether to re-prompt the patient.
            - faster-whisper backend: derived from segment avg_logprob
            - transformers backend:   estimated from sequence log probability
        Do not use as a clinical quality metric.
    """

    text: str = Field(
        ...,
        description=(
            "Transcribed text. May be mixed Devanagari + Latin for Hinglish."
        ),
    )
    language: str = Field(
        ...,
        description='Language code: "hi", "en", "hinglish", or "unknown".',
    )
    confidence: float = Field(
        ...,
        description="Confidence score in [0.0, 1.0]. Method depends on backend.",
        ge=0.0,
        le=1.0,
    )

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        allowed = {"hi", "en", "hinglish", "unknown"}
        if v not in allowed:
            raise ValueError(
                f"language must be one of {allowed}, got '{v}'. "
                "Do not add new language codes without team agreement."
            )
        return v

    def is_low_confidence(self, threshold: float = 0.60) -> bool:
        """
        Return True if confidence falls below the given threshold.

        Used by the conversation engine to decide whether to re-prompt
        the patient with "क्या आप दोबारा बोल सकते हैं?" (Can you repeat?)

        Args:
            threshold: Minimum acceptable confidence. Default from config.

        Returns:
            True if confidence < threshold.
        """
        return self.confidence < threshold

    def to_dict(self) -> dict:
        """
        Return a plain dict matching the agreed JSON contract.

        Output format:
            {
                "text": "...",
                "language": "...",
                "confidence": 0.0
            }
        """
        return {
            "text": self.text,
            "language": self.language,
            "confidence": round(self.confidence, 4),
        }
