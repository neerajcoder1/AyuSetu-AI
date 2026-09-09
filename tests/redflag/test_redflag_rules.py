"""
Red-Flag Declarative Clinical Rules Unit Tests
==============================================
Validates deterministic evaluation of each PRD-backed clinical safety rule.
Tests positive matching, negative matching, missing facts, and threshold boundaries.
"""

from ayusetu.redflag.rules import CLINICAL_RULES_REGISTRY, get_rule_by_id
from ayusetu.redflag.models import RedFlagTier


def test_registry_contains_authoritative_rules():
    """Verify registry contains all 11 authoritative rules across 3 tiers."""
    assert len(CLINICAL_RULES_REGISTRY) == 11
    tier1_rules = [r for r in CLINICAL_RULES_REGISTRY if r.tier == RedFlagTier.TIER_1]
    tier2_rules = [r for r in CLINICAL_RULES_REGISTRY if r.tier == RedFlagTier.TIER_2]
    tier3_rules = [r for r in CLINICAL_RULES_REGISTRY if r.tier == RedFlagTier.TIER_3]

    assert len(tier1_rules) == 5  # RF-CARD-001, RF-RESP-001, RF-NEURO-001, RF-IMM-001, RF-HEM-001
    assert len(tier2_rules) == 4  # RF-CARD-002, RF-INF-001, RF-GI-001, RF-ENDO-001
    assert len(tier3_rules) == 2  # RF-ALLERGY-001, RF-OB-001


def test_rf_card_001_acute_coronary_warning():
    """RF-CARD-001: Chest pain with radiation or diaphoresis or dyspnea triggers Tier 1."""
    rule = get_rule_by_id("RF-CARD-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    # Positive match: chest pain + radiation
    assert rule.predicate({"symptoms.chest_pain": True, "symptoms.radiation": True}) is True

    # Positive match: chest pain + diaphoresis
    assert rule.predicate({"symptoms.chest_pain": "true", "symptoms.diaphoresis": "yes"}) is True

    # Negative match: chest pain without radiation or diaphoresis or dyspnea
    assert rule.predicate({"symptoms.chest_pain": True}) is False

    # Negative match: radiation without chest pain
    assert rule.predicate({"symptoms.radiation": True}) is False

    # Missing facts: empty dict
    assert rule.predicate({}) is False


def test_rf_resp_001_respiratory_distress_and_hypoxia():
    """RF-RESP-001: Stridor or severe dyspnea or SpO2 < 90 triggers Tier 1."""
    rule = get_rule_by_id("RF-RESP-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    # Positive: stridor
    assert rule.predicate({"symptoms.stridor": True}) is True

    # Positive: SpO2 = 88%
    assert rule.predicate({"vitals.spo2": 88}) is True
    assert rule.predicate({"vitals.spo2": "89.5"}) is True

    # Negative: SpO2 = 96%
    assert rule.predicate({"vitals.spo2": 96}) is False

    # Negative: mild dyspnea
    assert rule.predicate({"symptoms.dyspnea_mild": True}) is False


def test_rf_neuro_001_stroke_signs():
    """RF-NEURO-001: Focal deficit, facial droop, slurred speech, altered sensorium."""
    rule = get_rule_by_id("RF-NEURO-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    assert rule.predicate({"symptoms.facial_droop": True}) is True
    assert rule.predicate({"symptoms.speech_slur": True}) is True
    assert rule.predicate({"symptoms.altered_sensorium": True}) is True
    assert rule.predicate({"symptoms.focal_deficit": True}) is True
    assert rule.predicate({"symptoms.headache": True}) is False


def test_rf_imm_001_anaphylaxis():
    """RF-IMM-001: Acute anaphylaxis or laryngeal edema."""
    rule = get_rule_by_id("RF-IMM-001")
    assert rule is not None
    assert rule.predicate({"allergies.acute_anaphylaxis": True}) is True
    assert rule.predicate({"symptoms.laryngeal_edema": True}) is True
    assert rule.predicate({"allergies.seasonal_rhinitis": True}) is False


def test_rf_hem_001_hemorrhage():
    """RF-HEM-001: Massive active bleeding."""
    rule = get_rule_by_id("RF-HEM-001")
    assert rule is not None
    assert rule.predicate({"symptoms.active_hemorrhage": True}) is True
    assert rule.predicate({"symptoms.minor_cut": True}) is False


def test_rf_card_002_hypertensive_urgency():
    """RF-CARD-002: SBP >= 180 or DBP >= 110 triggers Tier 2."""
    rule = get_rule_by_id("RF-CARD-002")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_2

    # SBP = 185
    assert rule.predicate({"vitals.sbp": 185, "vitals.dbp": 90}) is True

    # DBP = 115
    assert rule.predicate({"vitals.sbp": 140, "vitals.dbp": 115}) is True

    # Normal / mild hypertension (150/95)
    assert rule.predicate({"vitals.sbp": 150, "vitals.dbp": 95}) is False


def test_rf_inf_001_meningism():
    """RF-INF-001: Fever AND neck stiffness."""
    rule = get_rule_by_id("RF-INF-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_2

    assert rule.predicate({"symptoms.fever": True, "symptoms.neck_stiffness": True}) is True
    assert rule.predicate({"symptoms.fever": True, "symptoms.neck_stiffness": False}) is False
    assert rule.predicate({"symptoms.fever": False, "symptoms.neck_stiffness": True}) is False


def test_rf_gi_001_acute_abdomen():
    """RF-GI-001: Severe abdominal pain AND rigidity."""
    rule = get_rule_by_id("RF-GI-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_2

    assert rule.predicate({"symptoms.abdominal_pain": True, "symptoms.abdominal_rigidity": True}) is True
    assert rule.predicate({"symptoms.abdominal_pain": True}) is False


def test_rf_endo_001_hyperglycemic_crisis():
    """RF-ENDO-001: Known diabetes AND (severe vomiting OR altered sensorium)."""
    rule = get_rule_by_id("RF-ENDO-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_2

    assert rule.predicate({"past_history.diabetes": True, "symptoms.severe_vomiting": True}) is True
    assert rule.predicate({"past_history.diabetes": True, "symptoms.altered_sensorium": True}) is True
    assert rule.predicate({"symptoms.severe_vomiting": True}) is False  # Missing diabetes


def test_rf_allergy_001_severe_drug_allergy():
    """RF-ALLERGY-001: Documented severe drug allergy."""
    rule = get_rule_by_id("RF-ALLERGY-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_3

    assert rule.predicate({"allergies.severe_drug_allergy": True}) is True
    assert rule.predicate({"allergies.anaphylaxis_history": True}) is True
    assert rule.predicate({}) is False


def test_rf_ob_001_pregnancy_caution():
    """RF-OB-001: Pregnancy AND (bleeding OR severe headache)."""
    rule = get_rule_by_id("RF-OB-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_3

    assert rule.predicate({"patient.is_pregnant": True, "symptoms.pregnancy_bleeding": True}) is True
    assert rule.predicate({"patient.is_pregnant": True, "symptoms.severe_headache": True}) is True
    assert rule.predicate({"patient.is_pregnant": True}) is False
