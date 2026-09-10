"""
Red-Flag Engine Unit Tests
==========================
Validates fact extraction, confidence thresholds, unelicited fact safety,
tier precedence ordering, and zero-PHI trigger text generation.
"""

from ayusetu.redflag.models import StructuredClinicalFact
from ayusetu.redflag.engine import red_flag_engine


def test_engine_evaluates_matched_rules():
    """Verify engine evaluates structured facts and returns matched rules sorted by tier."""
    facts = [
        StructuredClinicalFact(path="symptoms.chest_pain", value=True),
        StructuredClinicalFact(path="symptoms.radiation", value=True),
        StructuredClinicalFact(path="vitals.sbp", value=190),
        StructuredClinicalFact(path="allergies.severe_drug_allergy", value=True),
    ]

    matched = red_flag_engine.evaluate(facts)
    assert len(matched) == 3

    # Tier 1 rule first (RF-CARD-001), then Tier 2 (RF-CARD-002), then Tier 3 (RF-ALLERGY-001)
    assert matched[0][0].rule_id == "RF-CARD-001"
    assert matched[0][0].tier.value == 1

    assert matched[1][0].rule_id == "RF-CARD-002"
    assert matched[1][0].tier.value == 2

    assert matched[2][0].rule_id == "RF-ALLERGY-001"
    assert matched[2][0].tier.value == 3


def test_engine_ignores_unelicited_facts():
    """Verify that facts with elicited=False are never treated as positive facts."""
    facts = [
        StructuredClinicalFact(path="symptoms.chest_pain", value=True, elicited=False),
        StructuredClinicalFact(path="symptoms.radiation", value=True, elicited=False),
    ]

    matched = red_flag_engine.evaluate(facts)
    assert len(matched) == 0


def test_engine_ignores_low_confidence_extractions():
    """Verify that extractions below confidence threshold (0.5) are ignored."""
    facts = [
        StructuredClinicalFact(path="symptoms.chest_pain", value=True, confidence=0.9),
        StructuredClinicalFact(path="symptoms.radiation", value=True, confidence=0.3),  # Low confidence
    ]

    matched = red_flag_engine.evaluate(facts)
    # RF-CARD-001 requires chest pain + radiation; since radiation confidence is 0.3, it is ignored
    assert len(matched) == 0


def test_engine_trigger_text_is_zero_phi_template():
    """Verify trigger text uses the declarative rule description and contains no raw transcripts."""
    facts = [
        StructuredClinicalFact(path="symptoms.stridor", value=True),
    ]

    matched = red_flag_engine.evaluate(facts)
    assert len(matched) == 1
    rule, trigger_text = matched[0]

    assert rule.rule_id == "RF-RESP-001"
    assert trigger_text == rule.description
    assert "stridor" in trigger_text.lower()
