"""
AyuSetu AI — Clinical Extraction Utilities
==========================================
Pure helper functions used by the rule-based clinical extractor.
No external dependencies beyond Python's standard library.
No LLM calls. No clinical decision-making.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

# Maps Hindi/Hinglish/English number words to integer day equivalents.
# Keys are lower-cased.
_NUMBER_WORDS: dict[str, int] = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30,
    # Hindi Devanagari cardinal numbers (1–10 most common)
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5,
    "पांच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    # Hindi romanised (Hinglish)
    "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5,
    "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
}

# Unit aliases → canonical English unit and multiplier to days.
_UNIT_MAP: list[Tuple[re.Pattern, str, float]] = [
    # Hours
    (re.compile(r"\b(घंटे?|घण्टे?|ghante?|hour?s?)\b", re.I | re.U), "hour(s)", 1 / 24),
    # Days
    (re.compile(r"\b(दिन|din|day?s?)\b", re.I | re.U), "day(s)", 1.0),
    # Weeks
    (re.compile(r"\b(हफ्ते?|हफ़्ते?|hafte?|week?s?)\b", re.I | re.U), "week(s)", 7.0),
    # Months
    (re.compile(r"\b(महीने?|mahine?|month?s?)\b", re.I | re.U), "month(s)", 30.0),
    # Years
    (re.compile(r"\b(साल|वर्ष|saal|year?s?)\b", re.I | re.U), "year(s)", 365.0),
]


def parse_duration(text: str) -> Optional[Tuple[str, float]]:
    """
    Attempt to extract a duration expression from *text*.

    Returns
    -------
    (canonical_string, confidence) if a duration is detected, else None.

    Example
    -------
    >>> parse_duration("मुझे दो दिन से बुखार है")
    ("2 day(s)", 0.90)
    >>> parse_duration("I have had pain for 3 weeks")
    ("3 week(s)", 0.90)
    """
    text_lower = text.lower()

    # Try numeric + unit first (e.g., "2 din", "3 weeks")
    for unit_pattern, unit_label, _ in _UNIT_MAP:
        # Number immediately before or after unit word
        m = re.search(
            r"(\d+)\s*" + unit_pattern.pattern,
            text_lower,
            re.I | re.U,
        )
        if m:
            quantity = m.group(1)
            return f"{quantity} {unit_label}", 0.90

    # Try word number + unit (e.g., "do din", "two days")
    for word, value in _NUMBER_WORDS.items():
        for unit_pattern, unit_label, _ in _UNIT_MAP:
            combined = re.compile(
                r"\b" + re.escape(word) + r"\s+" + unit_pattern.pattern,
                re.I | re.U,
            )
            if combined.search(text):
                return f"{value} {unit_label}", 0.87

    # Vague temporal expressions — lower confidence
    vague_patterns = [
        (re.compile(r"\b(kuch din|kuch time|thodi der|कुछ दिन|कुछ समय)\b", re.I | re.U),
         "a few days", 0.55),
        (re.compile(r"\b(kaafi time|kaafi dinon|काफ़ी दिनों?|काफी समय)\b", re.I | re.U),
         "a long time", 0.50),
        (re.compile(r"\b(recently|haal hi mein|हाल ही में)\b", re.I | re.U),
         "recently", 0.45),
    ]
    for pattern, label, conf in vague_patterns:
        if pattern.search(text):
            return label, conf

    return None


# ---------------------------------------------------------------------------
# Severity parsing
# ---------------------------------------------------------------------------

def parse_severity(text: str) -> Optional[Tuple[str, float]]:
    """
    Extract a severity description from *text*.

    Returns (canonical_label, confidence) or None.
    """
    # Numeric scale (e.g., "7 out of 10", "7/10")
    m = re.search(r"\b([1-9]|10)\s*(?:out\s*of\s*10|\/\s*10)\b", text, re.I)
    if m:
        return f"{m.group(1)}/10", 0.93

    text_lower = text.lower()

    severity_map = [
        # Very severe
        (re.compile(
            r"\b(unbearable|intolerable|bahut zyada|bahut tez|बहुत तेज़?|असहनीय)\b",
            re.I | re.U), "very severe", 0.88),
        # Severe
        (re.compile(
            r"\b(severe|bad|badly|tez|तेज़?|zyada|ज़्यादा|बहुत दर्द)\b",
            re.I | re.U), "severe", 0.82),
        # Moderate
        (re.compile(
            r"\b(moderate|medium|thoda|थोड़ा|kam zyada|ठीक[-\s]?ठाक)\b",
            re.I | re.U), "moderate", 0.78),
        # Mild
        (re.compile(
            r"\b(mild|slight|thodi si|थोड़ी\s*सी|halka|हल्का)\b",
            re.I | re.U), "mild", 0.78),
    ]
    for pattern, label, conf in severity_map:
        if pattern.search(text):
            return label, conf

    return None


# ---------------------------------------------------------------------------
# Onset parsing
# ---------------------------------------------------------------------------

def parse_onset(text: str) -> Optional[Tuple[str, float]]:
    """
    Extract onset description from *text*.

    Returns (canonical_label, confidence) or None.
    """
    # 1. Specific onset keywords (e.g. kal/yesterday, parson, last night, etc.)
    patterns = [
        (re.compile(r"\b(last night|kal raat|कल रात)\b", re.I | re.U), "last night", 0.90),
        (re.compile(r"\b(parson|parso|परसों|day before yesterday)\b", re.I | re.U), "2 days ago", 0.90),
        (re.compile(r"\b(yesterday|kal|कल)\b", re.I | re.U), "yesterday", 0.90),
        (re.compile(r"\b(this morning|aaj subah|aaj savere|आज सुबह)\b", re.I | re.U), "this morning", 0.90),
        (re.compile(r"\b(today|aaj|आज)\b", re.I | re.U), "today", 0.85),
        (re.compile(r"\b(last week|pichle hafte|पिछले हफ्ते)\b", re.I | re.U), "last week", 0.88),
        (re.compile(r"\b(last month|pichle mahine|पिछले महीने)\b", re.I | re.U), "last month", 0.88),
        (re.compile(r"\b(suddenly|achanak|अचानक|out of nowhere)\b", re.I | re.U), "sudden onset", 0.85),
        (re.compile(r"\b(gradually|धीरे[-\s]?धीरे|dheere dheere|slowly|over time)\b", re.I | re.U), "gradual onset", 0.82),
    ]
    for pattern, label, conf in patterns:
        if pattern.search(text):
            return label, conf

    # 2. Relative onset with duration + ago/pehle (e.g. "3 days ago", "teen din pehle", "तीन दिन पहले")
    num_keys = "|".join(re.escape(k) for k in _NUMBER_WORDS.keys())
    rel_ago_pattern = re.compile(
        r"\b(?:(\d+|" + num_keys + r")\s+)?"
        r"(घंटे?|ghante?|hours?|दिन|din|days?|हफ्ते?|हफ़्ते?|hafte?|weeks?|महीने?|mahine?|months?|साल|saal|years?)\s*"
        r"(?:पहले|pahle|pehle|ago)\b",
        re.I | re.U,
    )
    m_ago = rel_ago_pattern.search(text)
    if m_ago:
        return m_ago.group(0), 0.90

    # 3. Temporal phrases indicating start/onset: "last N days", "from last N days", "for the past N days", "since N days", "over the last N days", "in the last N days", "pichle N din"
    since_last_pattern = re.compile(
        r"\b(?:since|from\s+last|for\s+the\s+past|over\s+the\s+last|in\s+the\s+last|last|pichle|पिछले)\s+"
        r"(?:(\d+|" + num_keys + r")\s+)?"
        r"(घंटे?|ghante?|hours?|दिन|din|days?|हफ्ते?|हफ़्ते?|hafte?|weeks?|महीने?|mahine?|months?|साल|saal|years?)\b",
        re.I | re.U,
    )
    m_since_last = since_last_pattern.search(text)
    if m_since_last:
        return m_since_last.group(0), 0.90

    # 4. Verb/discovery phrases with onset indicator (e.g. "noticed", "first noticed", "first time", "started", "began", "appeared", "shuru", "pehli baar")
    start_pattern = re.compile(
        r"\b(notice[ds]?|first\s*notice[ds]?|first\s*time|shuru\s*(?:hui|hua|huye|ho\s*gaya)?|शुरू\s*(?:हुआ|हुई|हो\s*गया)?|started?|first\s*started|began|first\s*began|appeared?|first\s*appeared|pehli\s*baar|पहली\s*बार)\b",
        re.I | re.U,
    )
    if start_pattern.search(text):
        dur = parse_duration(text)
        if dur:
            return f"{dur[0]} ago", 0.88
        m_start = start_pattern.search(text)
        if m_start:
            return text.strip()[:60], 0.82

    return None


# ---------------------------------------------------------------------------
# Location parsing
# ---------------------------------------------------------------------------

def parse_location(text: str) -> Optional[Tuple[str, float]]:
    """
    Extract body-location description from *text*.

    Returns (canonical_label, confidence) or None.
    """
    locations = [
        # Head
        (re.compile(
            r"\b(head|sir|सिर|forehead|maatha|माथा|temple|kaanpati|कनपटी)\b",
            re.I | re.U), "head/forehead", 0.90),
        # Chest
        (re.compile(
            r"\b(chest|seena|सीना|छाती|chhati)\b",
            re.I | re.U), "chest", 0.90),
        # Stomach / abdomen
        (re.compile(
            r"\b(stomach|abdomen|pet|पेट|belly|navel|naabhi|नाभि)\b",
            re.I | re.U), "abdomen/stomach", 0.90),
        # Back
        (re.compile(
            r"\b(back|kamar|कमर|spine|peeth|पीठ)\b",
            re.I | re.U), "back", 0.88),
        # Throat / neck
        (re.compile(
            r"\b(throat|gala|gale|गला|neck|gardan|गर्दन)\b",
            re.I | re.U), "throat/neck", 0.88),
        # Joints / limbs (generic)
        (re.compile(
            r"\b(knee|ghutna|घुटना|leg|pair|पैर|arm|haath|हाथ|joint|jod|जोड़)\b",
            re.I | re.U), "limb/joint", 0.85),
        # Ear
        (re.compile(r"\b(ear|kaan|कान)\b", re.I | re.U), "ear", 0.90),
        # Eye
        (re.compile(r"\b(eye|aankh|आँख|aankhein)\b", re.I | re.U), "eye", 0.90),
    ]
    for pattern, label, conf in locations:
        if pattern.search(text):
            return label, conf
    return None
