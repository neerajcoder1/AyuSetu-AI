"""
Red-Flag Declarative Clinical Rules Unit Tests
==============================================
Validates deterministic evaluation of each PRD-backed clinical safety rule.
Tests positive matching, negative matching, missing facts, and threshold boundaries.
"""

from ayusetu.redflag.rules import get_clinical_rules_registry, get_rule_by_id, reset_rules_registry_for_testing
from ayusetu.redflag.models import RedFlagTier


def test_registry_contains_authoritative_rules():
    """Verify registry contains all 15 authoritative rules across 3 tiers."""
    reset_rules_registry_for_testing(None)
    rules = get_clinical_rules_registry()
    assert len(rules) == 15
    tier1_rules = [r for r in rules if r.tier == RedFlagTier.TIER_1]
    tier2_rules = [r for r in rules if r.tier == RedFlagTier.TIER_2]
    tier3_rules = [r for r in rules if r.tier == RedFlagTier.TIER_3]

    assert len(tier1_rules) == 12
    assert len(tier2_rules) == 2
    assert len(tier3_rules) == 1


def test_rf_card_001_acute_coronary_warning():
    """RF-CARD-001: Chest pain/pressure with radiation, diaphoresis, dyspnea, sweating, or exertional pattern triggers Tier 1."""
    rule = get_rule_by_id("RF-CARD-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    # Positive match: chest pain + radiation
    assert rule.predicate({"symptoms.chest_pain": True, "symptoms.radiation": True}) is True

    # Positive match: chest pain + diaphoresis / sweating
    assert rule.predicate({"symptoms.chest_pain": "true", "symptoms.diaphoresis": "yes"}) is True
    assert rule.predicate({"symptoms.chest_pain": True, "symptoms.sweating": True}) is True

    # Positive match: chest pressure + exertional pattern
    assert rule.predicate({"symptoms.chest_pressure": True, "symptoms.exertional_pattern": True}) is True

    # Positive match: chest pressure + dyspnea
    assert rule.predicate({"hpi.chest_pressure": True, "hpi.dyspnea": True}) is True

    # Negative match: chest pain without associated symptoms
    assert rule.predicate({"symptoms.chest_pain": True}) is False

    # Negative match: radiation without chest pain/pressure
    assert rule.predicate({"symptoms.radiation": True}) is False

    # Missing facts: empty dict
    assert rule.predicate({}) is False


def test_rf_resp_001_respiratory_distress_and_hypoxia():
    """RF-RESP-001: Stridor, severe dyspnea, SpO2 < 90, breathlessness at rest, inability to complete sentence, or cyanosis triggers Tier 1."""
    rule = get_rule_by_id("RF-RESP-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    # Positive: stridor
    assert rule.predicate({"symptoms.stridor": True}) is True

    # Positive: SpO2 = 88%
    assert rule.predicate({"vitals.spo2": 88}) is True
    assert rule.predicate({"vitals.spo2": "89.5"}) is True

    # Positive: breathlessness at rest
    assert rule.predicate({"symptoms.breathlessness_at_rest": True}) is True

    # Positive: inability to complete sentence
    assert rule.predicate({"symptoms.inability_to_complete_sentence": True}) is True

    # Positive: cyanosis
    assert rule.predicate({"symptoms.cyanosis": True}) is True

    # Negative: SpO2 = 96%
    assert rule.predicate({"vitals.spo2": 96}) is False

    # Negative: mild dyspnea
    assert rule.predicate({"symptoms.dyspnea_mild": True}) is False


def test_rf_neuro_001_stroke_signs():
    """RF-NEURO-001: Focal deficit, facial droop, slurred speech, altered sensorium, unilateral weakness/numbness, worst headache, new seizure."""
    rule = get_rule_by_id("RF-NEURO-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    assert rule.predicate({"symptoms.facial_droop": True}) is True
    assert rule.predicate({"symptoms.speech_slur": True}) is True
    assert rule.predicate({"symptoms.altered_sensorium": True}) is True
    assert rule.predicate({"symptoms.focal_deficit": True}) is True
    assert rule.predicate({"symptoms.unilateral_weakness": True}) is True
    assert rule.predicate({"symptoms.unilateral_numbness": True}) is True
    assert rule.predicate({"symptoms.worst_ever_headache": True}) is True
    assert rule.predicate({"symptoms.thunderclap_headache": True}) is True
    assert rule.predicate({"symptoms.new_seizure": True}) is True
    assert rule.predicate({"symptoms.seizure": True}) is True

    # Negative match: mild headache or dizziness without red flags
    assert rule.predicate({"symptoms.headache": True}) is False
    assert rule.predicate({"symptoms.dizziness": True}) is False


def test_rf_imm_001_anaphylaxis():
    """RF-IMM-001: Acute anaphylaxis or laryngeal edema."""
    rule = get_rule_by_id("RF-IMM-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1
    assert rule.predicate({"allergies.acute_anaphylaxis": True}) is True
    assert rule.predicate({"symptoms.laryngeal_edema": True}) is True
    assert rule.predicate({"allergies.seasonal_rhinitis": True}) is False


def test_rf_hem_001_hemorrhage():
    """RF-HEM-001: Massive active bleeding, haematemesis, melaena, heavy vaginal bleeding, uncontrolled bleeding."""
    rule = get_rule_by_id("RF-HEM-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1
    assert rule.predicate({"symptoms.active_hemorrhage": True}) is True
    assert rule.predicate({"symptoms.haematemesis": True}) is True
    assert rule.predicate({"symptoms.hematemesis": True}) is True
    assert rule.predicate({"symptoms.melaena": True}) is True
    assert rule.predicate({"symptoms.melena": True}) is True
    assert rule.predicate({"symptoms.heavy_vaginal_bleeding": True}) is True
    assert rule.predicate({"symptoms.uncontrolled_bleeding": True}) is True

    # Negative: minor cut or nosebleed
    assert rule.predicate({"symptoms.minor_cut": True}) is False
    assert rule.predicate({"symptoms.minor_epistaxis": True}) is False


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
    """RF-INF-001: Fever AND neck stiffness (Tier 2)."""
    rule = get_rule_by_id("RF-INF-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_2

    assert rule.predicate({"symptoms.fever": True, "symptoms.neck_stiffness": True}) is True
    assert rule.predicate({"symptoms.fever": True, "symptoms.neck_stiffness": False}) is False
    assert rule.predicate({"symptoms.fever": False, "symptoms.neck_stiffness": True}) is False


def test_rf_gi_001_acute_abdomen():
    """RF-GI-001: Severe abdominal pain AND rigidity / obstipation (Tier 1)."""
    rule = get_rule_by_id("RF-GI-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    assert rule.predicate({"symptoms.abdominal_pain": True, "symptoms.abdominal_rigidity": True}) is True
    assert rule.predicate({"symptoms.abdominal_pain": True, "symptoms.obstipation_with_vomiting": True}) is True
    assert rule.predicate({"symptoms.abdominal_pain": True}) is False


def test_rf_endo_001_hyperglycemic_crisis():
    """RF-ENDO-001: Known diabetes AND (severe vomiting OR altered sensorium OR drowsiness/confusion) (Tier 1)."""
    rule = get_rule_by_id("RF-ENDO-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    assert rule.predicate({"past_history.diabetes": True, "symptoms.severe_vomiting": True}) is True
    assert rule.predicate({"past_history.diabetes": True, "symptoms.altered_sensorium": True}) is True
    assert rule.predicate({"past_history.diabetes": True, "symptoms.confusion": True}) is True
    assert rule.predicate({"past_history.diabetes": True, "symptoms.drowsiness": True}) is True
    assert rule.predicate({"symptoms.severe_vomiting": True}) is False  # Missing diabetes


def test_rf_allergy_001_severe_drug_allergy():
    """RF-ALLERGY-001: Documented severe drug allergy (Tier 3)."""
    rule = get_rule_by_id("RF-ALLERGY-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_3

    assert rule.predicate({"allergies.severe_drug_allergy": True}) is True
    assert rule.predicate({"allergies.anaphylaxis_history": True}) is True
    assert rule.predicate({}) is False


def test_rf_ob_001_pregnancy_emergency():
    """RF-OB-001: Pregnancy AND (bleeding OR severe headache OR reduced fetal movement OR convulsions) (Tier 1)."""
    rule = get_rule_by_id("RF-OB-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    assert rule.predicate({"patient.is_pregnant": True, "symptoms.pregnancy_bleeding": True}) is True
    assert rule.predicate({"patient.is_pregnant": True, "symptoms.severe_headache": True}) is True
    assert rule.predicate({"patient.is_pregnant": True, "symptoms.reduced_fetal_movement": True}) is True
    assert rule.predicate({"patient.is_pregnant": True, "symptoms.convulsions": True}) is True
    assert rule.predicate({"patient.is_pregnant": True}) is False


def test_rf_sepsis_001_severe_sepsis():
    """RF-SEPSIS-001: Fever AND (confusion OR oliguria/low urine output OR rigors) (Tier 1)."""
    rule = get_rule_by_id("RF-SEPSIS-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    assert rule.predicate({"symptoms.fever": True, "symptoms.confusion": True}) is True
    assert rule.predicate({"symptoms.fever": True, "symptoms.low_urine_output": True}) is True
    assert rule.predicate({"symptoms.fever": True, "symptoms.rigors": True}) is True
    assert rule.predicate({"symptoms.fever": True}) is False
    assert rule.predicate({"symptoms.rigors": True}) is False


def test_rf_paed_001_paediatric_emergency():
    """RF-PAED-001: Infant/child refusing feeds, lethargy, convulsion, fast breathing (Tier 1)."""
    rule = get_rule_by_id("RF-PAED-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    assert rule.predicate({"symptoms.infant_refusing_feeds": True}) is True
    assert rule.predicate({"symptoms.pediatric_lethargy": True}) is True
    assert rule.predicate({"symptoms.pediatric_convulsion": True}) is True
    assert rule.predicate({"symptoms.pediatric_fast_breathing": True}) is True
    assert rule.predicate({"symptoms.mild_cough": True}) is False


def test_rf_psych_001_self_harm_emergency():
    """RF-PSYCH-001: Self-harm ideation, plan, or recent attempt (Tier 1)."""
    rule = get_rule_by_id("RF-PSYCH-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    assert rule.predicate({"symptoms.self_harm_ideation": True}) is True
    assert rule.predicate({"symptoms.self_harm_plan": True}) is True
    assert rule.predicate({"symptoms.self_harm_attempt": True}) is True
    assert rule.predicate({"symptoms.sadness": True}) is False
    assert rule.action.patient_message_key == "tele_manas_support"


def test_rf_trauma_001_head_injury():
    """RF-TRAUMA-001: Head injury AND (vomiting OR loss of consciousness) (Tier 1)."""
    rule = get_rule_by_id("RF-TRAUMA-001")
    assert rule is not None
    assert rule.tier == RedFlagTier.TIER_1

    assert rule.predicate({"symptoms.head_injury": True, "symptoms.vomiting": True}) is True
    assert rule.predicate({"symptoms.head_injury": True, "symptoms.loss_of_consciousness": True}) is True
    assert rule.predicate({"symptoms.head_injury": True}) is False
    assert rule.predicate({"symptoms.vomiting": True}) is False
