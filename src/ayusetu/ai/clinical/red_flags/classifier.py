"""
Classifier layer over the utterance stream (PRD §12.1: "Two layers, unioned.
A curated deterministic rule set... and a classifier over the utterance
stream that catches phrasings the rules miss.").

RedFlagClassifierLayer here is a keyword/phrase classifier — a stand-in for
a trained model. It is deliberately seeded with PARAPHRASES of the Tier 1
catalogue's literal wording (rules_catalogue.py), not the same phrases,
since its entire purpose is to catch what the exact-wording rules don't.
Swap `_PARAPHRASE_PATTERNS` for a real classifier's predict() call without
changing RedFlagEngine, which only depends on the `classify` Protocol.
"""

from typing import List, Protocol

from ayusetu.ai.clinical.red_flags.contracts import Tier

# category -> (title, [paraphrase keywords/phrases])
# Every entry is a rewording that would NOT match rules_catalogue.py's
# literal keyword lists, by construction.
_PARAPHRASE_PATTERNS = {
    "cardiac": (
        "Possible acute coronary syndrome",
        ["elephant sitting on my chest", "tightness in my chest going to my arm", "crushing feeling in chest"],
    ),
    "neurological": (
        "Possible acute stroke / neurological emergency",
        ["my face feels numb on one side", "can't hold my cup", "words are coming out wrong"],
    ),
    "respiratory": (
        "Severe respiratory distress",
        ["gasping for air", "lips look blue", "struggling for every breath"],
    ),
    "psychiatric": (
        "Self-harm disclosure",
        ["don't want to wake up tomorrow", "everyone would be better off without me", "planning to end things"],
    ),
    "paediatric": (
        "Paediatric emergency",
        ["baby won't wake up properly", "baby stopped drinking milk", "child looks blue around lips"],
    ),
}


class ClassifiedFlag:
    def __init__(self, category: str, title: str, matched_phrase: str, tier: Tier = Tier.TIER_1):
        self.category = category
        self.title = title
        self.matched_phrase = matched_phrase
        self.tier = tier


class RedFlagClassifier(Protocol):
    def classify(self, utterance: str) -> List[ClassifiedFlag]:
        ...


class KeywordParaphraseClassifier:
    """Deterministic stand-in classifier: matches curated paraphrase lists."""

    def classify(self, utterance: str) -> List[ClassifiedFlag]:
        text = utterance.lower()
        findings: List[ClassifiedFlag] = []
        for category, (title, phrases) in _PARAPHRASE_PATTERNS.items():
            for phrase in phrases:
                if phrase in text:
                    findings.append(ClassifiedFlag(category=category, title=title, matched_phrase=phrase))
        return findings
