"""
AyuSetu AI — Confidence Estimation
=====================================
Compute utterance-level confidence from ASR model outputs.

Confidence semantics by backend
---------------------------------
faster-whisper backend
    Each transcribed segment exposes ``avg_logprob`` (average log probability
    per output token, computed by CTranslate2). This is the most direct signal
    available from Whisper-family models.
    Method label: ``"avg_logprob_from_segments"``

transformers backend
    The standard ``transformers`` pipeline does not expose per-token log probs.
    When using ``WhisperForConditionalGeneration.generate()`` with
    ``output_scores=True``, the per-step logits are available in
    ``outputs.scores``. We convert each step's logit for the chosen token
    into a log probability and average across all generated tokens.
    This is a genuine (not invented) log probability, but it is an ESTIMATE
    of the same quantity that faster-whisper reports directly.
    Method label: ``"avg_logprob_from_token_scores"``

Important caveats
-----------------
- Neither value is a calibrated probability.
- Do not use as a clinical quality metric.
- Use only to decide whether to re-prompt the patient.
- The sigmoid mapping parameters (_CENTER, _SCALE) are engineering choices,
  not statistically validated. They will be recalibrated after Phase 1C eval.
"""

import logging
import math
import re
import unicodedata
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Curated Romanized Hinglish vocabulary sets for fallback detection
_HINGLISH_STRONG_MARKERS = {
    "mera", "meri", "mere", "mujhe", "mujhko", "naam", "bukhar", "pet",
    "dard", "takleef", "bataiye", "batayein", "kya", "kahan", "kab",
    "kaise", "kaisa", "raha", "rahi", "rahe", "thik", "theek", "dawa",
    "dawai", "goli", "ulti", "ultee", "chakkar", "chhati", "gala",
    "khansi", "nahin", "nhi", "aaya", "aayi", "aaye", "gaya", "gayi", "gaye",
    "namaste", "namaskar", "dhanyavaad", "shukriya", "kripya", "kripaya",
}

_HINGLISH_GRAMMAR_MARKERS = {
    "hai", "hain", "ho", "se", "mein", "me", "ko", "par", "ne",
    "ka", "ki", "ke", "aur", "ya", "toh", "bhi",
}

# ─── Sigmoid mapping parameters ───────────────────────────────────────────────
# Whisper avg_logprob typically ranges from ~-0.2 (excellent) to ~-1.5 (poor).
# CENTER: the avg_logprob value that maps to confidence ≈ 0.5.
# SCALE:  controls the steepness of the sigmoid curve.
# These defaults are reasonable starting points; recalibrate after evaluation.
_SIGMOID_CENTER: float = -0.8
_SIGMOID_SCALE: float = 5.0


def logprob_to_confidence(avg_logprob: float) -> float:
    """
    Map an average log probability to a [0.0, 1.0] confidence score.

    Uses a sigmoid function:
        confidence = sigmoid(SCALE * (avg_logprob - CENTER))

    Calibration:
        avg_logprob = -0.20 → confidence ≈ 0.95   (excellent)
        avg_logprob = -0.80 → confidence ≈ 0.50   (marginal)
        avg_logprob = -1.40 → confidence ≈ 0.05   (poor)

    Args:
        avg_logprob: Average log probability per token. Expected range [-2.0, 0.0].

    Returns:
        float in [0.0, 1.0].
    """
    x = _SIGMOID_SCALE * (avg_logprob - _SIGMOID_CENTER)
    # Use math.exp for scalar; clip guards against overflow at extremes
    try:
        value = 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        value = 0.0 if x < 0 else 1.0
    return float(np.clip(value, 0.0, 1.0))


def confidence_from_token_scores(
    scores: list,
    chosen_ids: list,
) -> tuple[float, str]:
    """
    Compute confidence from per-step logit tensors (transformers backend).

    Uses the model's output logits to compute the log probability of each
    chosen output token, then averages across all tokens. This mirrors the
    avg_logprob that faster-whisper reports from CTranslate2.

    Args:
        scores: List of per-step logit tensors from ``generate(output_scores=True)``.
                Each tensor has shape ``(batch_size, vocab_size)``.
                Corresponds to ``outputs.scores`` from transformers.
        chosen_ids: List of chosen token IDs at each step.
                    Must have the same length as ``scores``.

    Returns:
        Tuple of (confidence: float, method: str).
        method = "avg_logprob_from_token_scores"
    """
    import torch
    import torch.nn.functional as F

    if not scores or not chosen_ids:
        logger.warning(
            "Empty scores or chosen_ids; cannot compute confidence. "
            "Returning 0.0."
        )
        return 0.0, "avg_logprob_from_token_scores"

    log_probs: list[float] = []
    for step_logits, token_id in zip(scores, chosen_ids):
        # step_logits shape: (batch_size=1, vocab_size)
        log_prob_dist = F.log_softmax(step_logits[0], dim=-1)
        token_log_prob = float(log_prob_dist[token_id].item())
        log_probs.append(token_log_prob)

    if not log_probs:
        return 0.0, "avg_logprob_from_token_scores"

    avg_logprob = sum(log_probs) / len(log_probs)
    confidence = logprob_to_confidence(avg_logprob)

    logger.debug(
        "Confidence from token scores: tokens=%d, avg_logprob=%.4f, confidence=%.4f",
        len(log_probs),
        avg_logprob,
        confidence,
    )
    return confidence, "avg_logprob_from_token_scores"


def confidence_from_segments(segments: list) -> tuple[float, str]:
    """
    Compute confidence from faster-whisper segment avg_logprob values.

    Computes a text-length-weighted average of per-segment avg_logprob,
    then maps to [0.0, 1.0].

    Args:
        segments: List of faster-whisper Segment objects.
                  Each must have .avg_logprob (float) and .text (str).

    Returns:
        Tuple of (confidence: float, method: str).
        method = "avg_logprob_from_segments"
    """
    if not segments:
        logger.warning("No segments provided; confidence = 0.0.")
        return 0.0, "avg_logprob_from_segments"

    total_weight = 0.0
    weighted_sum = 0.0
    for seg in segments:
        # Weight by token count approximation (text character length)
        weight = max(1, len(seg.text.strip()))
        weighted_sum += seg.avg_logprob * weight
        total_weight += weight

    avg_logprob = weighted_sum / total_weight if total_weight > 0 else -1.0
    confidence = logprob_to_confidence(avg_logprob)

    logger.debug(
        "Confidence from %d segment(s): avg_logprob=%.4f, confidence=%.4f",
        len(segments),
        avg_logprob,
        confidence,
    )
    return confidence, "avg_logprob_from_segments"


def infer_language_from_text(text: str) -> str:
    """
    Infer the language code from the script composition of transcribed text.

    This is a heuristic based on Unicode script categories. It is NOT model-level
    language detection. It is used as a fallback and as a cross-check against
    the model's own language detection (to catch cases where the model reports
    a monolingual code but the output contains mixed script — the expected
    behavior for Hinglish with zero-stt-hinglish).

    Script rules
    ------------
    Devanagari (U+0900–U+097F):  Hindi characters
    ASCII alphabetic:             English characters
    Spaces, digits, punctuation: Ignored

    Thresholds
    ----------
    >= 85% Devanagari → "hi"
    >= 85% Latin      → "en"
    mixed             → "hinglish"
    nothing matched   → "unknown"

    Args:
        text: Transcribed text string (possibly mixed script).

    Returns:
        "hi", "en", "hinglish", or "unknown".
    """
    if not text or not text.strip():
        return "unknown"

    devanagari_count = 0
    latin_count = 0

    for char in text:
        # Skip non-letter characters (spaces, digits, punctuation)
        if not char.isalpha():
            continue
        char_name = unicodedata.name(char, "")
        if "DEVANAGARI" in char_name:
            devanagari_count += 1
        elif char.isascii():
            latin_count += 1
        # Other scripts (Gujarati, Bengali, etc.) are ignored for now

    total = devanagari_count + latin_count
    if total == 0:
        return "unknown"

    devanagari_ratio = devanagari_count / total

    # Thresholds chosen to be generous — err toward detecting code-switching
    if devanagari_ratio >= 0.85:
        return "hi"
    elif devanagari_ratio <= 0.15:
        # Check for Romanized Hinglish markers in Latin text before defaulting to "en"
        words = re.findall(r"\b[a-z]+\b", text.lower())
        strong_hits = sum(1 for w in words if w in _HINGLISH_STRONG_MARKERS)
        grammar_hits = sum(1 for w in words if w in _HINGLISH_GRAMMAR_MARKERS)
        score = (strong_hits * 2) + grammar_hits
        if strong_hits >= 1 or (grammar_hits >= 2 and score >= 3):
            return "hinglish"
        return "en"
    else:
        return "hinglish"
