"""
Red-Flag Deterministic Rule Evaluator Engine
============================================
Evaluates structured clinical facts against declarative safety rules.
Non-diagnostic: does not diagnose disease or infer unelicited clinical facts.
"""

from typing import Any, Dict, List, Tuple

from ayusetu.redflag.models import StructuredClinicalFact
from ayusetu.redflag.rules import ClinicalRule, get_clinical_rules_registry


class RedFlagEngine:
    """
    Deterministic rule evaluation engine for clinical safety red flags.
    Evaluates versioned declarative clinical-content rules.
    """

    @classmethod
    def extract_facts_map(cls, facts: List[StructuredClinicalFact]) -> Dict[str, Any]:
        """
        Convert structured facts into a clean key-value lookup.
        Filters out unelicited facts or zero-confidence claims.
        """
        facts_map: Dict[str, Any] = {}
        for f in facts:
            if not f.elicited:
                continue
            if f.confidence is not None and f.confidence < 0.5:
                continue  # Ignore low-confidence extractions
            facts_map[f.path] = f.value
        return facts_map

    @classmethod
    def evaluate(cls, facts: List[StructuredClinicalFact]) -> List[Tuple[ClinicalRule, str]]:
        """
        Evaluate structured facts against all registered clinical safety rules.
        Returns a list of matched (ClinicalRule, deterministic_trigger_text) tuples.
        """
        facts_map = cls.extract_facts_map(facts)
        matched_rules: List[Tuple[ClinicalRule, str]] = []

        for rule in get_clinical_rules_registry():
            try:
                is_matched = rule.predicate(facts_map)
                if is_matched:
                    # trigger_text uses the rule's deterministic description template, never raw transcripts
                    matched_rules.append((rule, rule.description))
            except Exception:
                # Fail-safe: unexpected rule evaluation exceptions fail closed without match
                continue

        # Sort by tier precedence (Tier 1 first, then Tier 2, then Tier 3)
        matched_rules.sort(key=lambda r: r[0].tier.value)
        return matched_rules


red_flag_engine = RedFlagEngine()
