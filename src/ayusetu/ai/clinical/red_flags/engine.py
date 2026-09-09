"""
RedFlagEngine: unions the deterministic rule set and the classifier layer
(PRD §12.1) into a single list of RedFlagEvent for an encounter.
"""

from typing import Any, Dict, List, Optional

from ayusetu.ai.clinical.red_flags.classifier import KeywordParaphraseClassifier, RedFlagClassifier
from ayusetu.ai.clinical.red_flags.contracts import RedFlagEvent, RedFlagRule
from ayusetu.ai.clinical.red_flags.dsl import evaluate_condition
from ayusetu.ai.clinical.red_flags.rules_catalogue import TIER1_RULES_RAW


class RedFlagEngine:
    def __init__(
        self,
        rules: Optional[List[RedFlagRule]] = None,
        classifier: Optional[RedFlagClassifier] = None,
    ):
        self.rules = rules if rules is not None else [RedFlagRule(**r) for r in TIER1_RULES_RAW]
        self.classifier = classifier or KeywordParaphraseClassifier()

    def evaluate(self, encounter_id: str, context: Dict[str, Any], utterance: str = "") -> List[RedFlagEvent]:
        """
        `context` is a flat slot-path -> value dict (typically built from
        DialogueState.collected_info, keyed by ClinicalSlot.value). It should
        also include "utterance" -> the current/aggregated patient text if
        that isn't already one of the named slots, since several catalogue
        rules match against raw text.
        """
        full_context = {**context, "utterance": context.get("utterance", utterance)}
        events: List[RedFlagEvent] = []

        for rule in self.rules:
            if evaluate_condition(rule.when, full_context):
                events.append(
                    RedFlagEvent(
                        encounter_id=encounter_id,
                        rule_id=rule.id,
                        tier=rule.tier,
                        category=rule.category,
                        title=rule.title,
                        trigger_text=utterance or full_context.get("utterance", ""),
                        detection_layer="rule",
                    )
                )

        for flag in self.classifier.classify(utterance):
            events.append(
                RedFlagEvent(
                    encounter_id=encounter_id,
                    rule_id=f"CLASSIFIER-{flag.category.upper()}",
                    tier=flag.tier,
                    category=flag.category,
                    title=flag.title,
                    trigger_text=flag.matched_phrase,
                    detection_layer="classifier",
                )
            )

        return _dedupe_by_category(events)


def _dedupe_by_category(events: List[RedFlagEvent]) -> List[RedFlagEvent]:
    """
    A rule and the classifier can both fire for the same underlying clinical
    concern (e.g. cardiac): escalation must not be triggered twice for one
    concern within a single evaluation, so events are collapsed to one per
    category — keeping the lowest tier number (most severe), and preferring
    the rule-layer event as canonical when tiers are equal.
    """
    best: Dict[str, RedFlagEvent] = {}
    for event in events:
        current = best.get(event.category)
        if current is None:
            best[event.category] = event
            continue
        if event.tier < current.tier:
            best[event.category] = event
        elif event.tier == current.tier and current.detection_layer == "classifier" and event.detection_layer == "rule":
            best[event.category] = event
    return sorted(best.values(), key=lambda e: e.tier)
