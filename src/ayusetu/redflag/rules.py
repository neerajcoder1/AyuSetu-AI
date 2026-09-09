"""
Red-Flag Declarative Clinical Rules Catalog
===========================================
Deterministic, versioned clinical safety rules per PRD v2.0 §12 & §22.9.
Evaluates ONLY structured facts. Does NOT accept free-form LLM outputs or
unelicited assumptions.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from ayusetu.redflag.models import RedFlagTier


@dataclass(frozen=True)
class ClinicalRule:
    """Declarative definition of a clinical red-flag rule."""
    rule_id: str
    title: str
    description: str  # Deterministic non-PHI template
    tier: RedFlagTier
    required_paths: List[str]
    predicate: Callable[[Dict[str, Any]], bool]


def get_fact_value(facts: Dict[str, Any], path: str) -> Optional[Any]:
    """Retrieve structured fact value, returning None if missing or unelicited."""
    return facts.get(path)


def is_truthy(val: Any) -> bool:
    """Explicit truthiness helper: returns True ONLY if value is explicitly True or 'true'."""
    if val is True:
        return True
    if isinstance(val, str) and val.strip().lower() in ("true", "yes", "positive", "present"):
        return True
    return False


# ==============================================================================
# Rule Predicates (Deterministic & Non-Diagnostic)
# ==============================================================================

def _match_rf_card_001(facts: Dict[str, Any]) -> bool:
    """RF-CARD-001: Acute chest pain with radiation to arm/jaw or associated diaphoresis/dyspnea."""
    has_chest_pain = is_truthy(get_fact_value(facts, "symptoms.chest_pain")) or is_truthy(get_fact_value(facts, "hpi.chest_pain"))
    if not has_chest_pain:
        return False
    
    has_radiation = is_truthy(get_fact_value(facts, "symptoms.radiation")) or is_truthy(get_fact_value(facts, "hpi.radiation"))
    has_diaphoresis = is_truthy(get_fact_value(facts, "symptoms.diaphoresis")) or is_truthy(get_fact_value(facts, "hpi.diaphoresis"))
    has_dyspnea = is_truthy(get_fact_value(facts, "symptoms.dyspnea")) or is_truthy(get_fact_value(facts, "hpi.dyspnea"))

    return has_radiation or has_diaphoresis or has_dyspnea


def _match_rf_resp_001(facts: Dict[str, Any]) -> bool:
    """RF-RESP-001: Severe acute respiratory distress, stridor, or documented SpO2 < 90%."""
    has_stridor = is_truthy(get_fact_value(facts, "symptoms.stridor")) or is_truthy(get_fact_value(facts, "hpi.stridor"))
    has_severe_dyspnea = is_truthy(get_fact_value(facts, "symptoms.dyspnea_severe")) or is_truthy(get_fact_value(facts, "hpi.dyspnea_severe"))
    
    spo2 = get_fact_value(facts, "vitals.spo2")
    has_hypoxia = False
    if spo2 is not None:
        try:
            has_hypoxia = float(spo2) < 90.0
        except (ValueError, TypeError):
            pass

    return has_stridor or has_severe_dyspnea or has_hypoxia


def _match_rf_neuro_001(facts: Dict[str, Any]) -> bool:
    """RF-NEURO-001: Acute focal neurological deficit, FAST stroke signs, or sudden altered sensorium."""
    has_focal_deficit = is_truthy(get_fact_value(facts, "symptoms.focal_deficit")) or is_truthy(get_fact_value(facts, "hpi.focal_deficit"))
    has_altered_sensorium = is_truthy(get_fact_value(facts, "symptoms.altered_sensorium")) or is_truthy(get_fact_value(facts, "hpi.altered_sensorium"))
    has_facial_droop = is_truthy(get_fact_value(facts, "symptoms.facial_droop")) or is_truthy(get_fact_value(facts, "hpi.facial_droop"))
    has_speech_slur = is_truthy(get_fact_value(facts, "symptoms.speech_slur")) or is_truthy(get_fact_value(facts, "hpi.speech_slur"))

    return has_focal_deficit or has_altered_sensorium or has_facial_droop or has_speech_slur


def _match_rf_imm_001(facts: Dict[str, Any]) -> bool:
    """RF-IMM-001: Acute anaphylaxis signs with laryngeal/facial edema or airway compromise."""
    has_anaphylaxis = is_truthy(get_fact_value(facts, "allergies.acute_anaphylaxis")) or is_truthy(get_fact_value(facts, "hpi.acute_anaphylaxis"))
    has_laryngeal_edema = is_truthy(get_fact_value(facts, "symptoms.laryngeal_edema")) or is_truthy(get_fact_value(facts, "hpi.laryngeal_edema"))

    return has_anaphylaxis or has_laryngeal_edema


def _match_rf_hem_001(facts: Dict[str, Any]) -> bool:
    """RF-HEM-001: Massive active hemorrhage or acute hemodynamic instability."""
    return is_truthy(get_fact_value(facts, "symptoms.active_hemorrhage")) or is_truthy(get_fact_value(facts, "hpi.active_hemorrhage"))


def _match_rf_card_002(facts: Dict[str, Any]) -> bool:
    """RF-CARD-002: Severe hypertensive urgency (Systolic BP >= 180 or Diastolic BP >= 110)."""
    sbp = get_fact_value(facts, "vitals.sbp")
    dbp = get_fact_value(facts, "vitals.dbp")

    sbp_high = False
    if sbp is not None:
        try:
            sbp_high = float(sbp) >= 180.0
        except (ValueError, TypeError):
            pass

    dbp_high = False
    if dbp is not None:
        try:
            dbp_high = float(dbp) >= 110.0
        except (ValueError, TypeError):
            pass

    return sbp_high or dbp_high


def _match_rf_inf_001(facts: Dict[str, Any]) -> bool:
    """RF-INF-001: High fever with neck stiffness / meningism warning cluster."""
    has_fever = is_truthy(get_fact_value(facts, "symptoms.fever")) or is_truthy(get_fact_value(facts, "hpi.fever"))
    has_neck_stiffness = is_truthy(get_fact_value(facts, "symptoms.neck_stiffness")) or is_truthy(get_fact_value(facts, "hpi.neck_stiffness"))

    return has_fever and has_neck_stiffness


def _match_rf_gi_001(facts: Dict[str, Any]) -> bool:
    """RF-GI-001: Severe acute abdominal pain with rigidity or involuntary guarding."""
    has_abdo_pain = is_truthy(get_fact_value(facts, "symptoms.abdominal_pain")) or is_truthy(get_fact_value(facts, "hpi.abdominal_pain"))
    has_rigidity = is_truthy(get_fact_value(facts, "symptoms.abdominal_rigidity")) or is_truthy(get_fact_value(facts, "hpi.abdominal_rigidity"))

    return has_abdo_pain and has_rigidity


def _match_rf_endo_001(facts: Dict[str, Any]) -> bool:
    """RF-ENDO-001: Hyperglycemic crisis / diabetic warning cluster (known diabetic with severe vomiting/altered sensorium)."""
    is_diabetic = is_truthy(get_fact_value(facts, "past_history.diabetes")) or is_truthy(get_fact_value(facts, "hpi.diabetes"))
    has_vomiting = is_truthy(get_fact_value(facts, "symptoms.severe_vomiting")) or is_truthy(get_fact_value(facts, "hpi.severe_vomiting"))
    has_altered = is_truthy(get_fact_value(facts, "symptoms.altered_sensorium")) or is_truthy(get_fact_value(facts, "hpi.altered_sensorium"))

    return is_diabetic and (has_vomiting or has_altered)


def _match_rf_allergy_001(facts: Dict[str, Any]) -> bool:
    """RF-ALLERGY-001: Documented severe drug allergy match."""
    return is_truthy(get_fact_value(facts, "allergies.severe_drug_allergy")) or is_truthy(get_fact_value(facts, "allergies.anaphylaxis_history"))


def _match_rf_ob_001(facts: Dict[str, Any]) -> bool:
    """RF-OB-001: High-risk pregnancy clinical caution indicator."""
    is_pregnant = is_truthy(get_fact_value(facts, "patient.is_pregnant")) or is_truthy(get_fact_value(facts, "hpi.is_pregnant"))
    has_complication = is_truthy(get_fact_value(facts, "symptoms.pregnancy_bleeding")) or is_truthy(get_fact_value(facts, "symptoms.severe_headache"))

    return is_pregnant and has_complication


# ==============================================================================
# Authoritative Rules Registry
# ==============================================================================

CLINICAL_RULES_REGISTRY: List[ClinicalRule] = [
    # Tier 1 Emergency Rules
    ClinicalRule(
        rule_id="RF-CARD-001",
        title="Acute Coronary Warning Cluster",
        description="Severe acute chest pain radiating to arm/jaw or associated with diaphoresis/dyspnea",
        tier=RedFlagTier.TIER_1,
        required_paths=["symptoms.chest_pain", "symptoms.radiation", "symptoms.diaphoresis", "symptoms.dyspnea"],
        predicate=_match_rf_card_001,
    ),
    ClinicalRule(
        rule_id="RF-RESP-001",
        title="Acute Respiratory Compromise",
        description="Acute severe dyspnea, stridor, or documented hypoxia (SpO2 < 90%)",
        tier=RedFlagTier.TIER_1,
        required_paths=["symptoms.stridor", "symptoms.dyspnea_severe", "vitals.spo2"],
        predicate=_match_rf_resp_001,
    ),
    ClinicalRule(
        rule_id="RF-NEURO-001",
        title="Acute Neurological Deficit / Stroke Signs",
        description="Sudden focal neurological deficit, facial droop, slurred speech, or acute altered sensorium",
        tier=RedFlagTier.TIER_1,
        required_paths=["symptoms.focal_deficit", "symptoms.facial_droop", "symptoms.speech_slur", "symptoms.altered_sensorium"],
        predicate=_match_rf_neuro_001,
    ),
    ClinicalRule(
        rule_id="RF-IMM-001",
        title="Acute Anaphylaxis / Airway Edema",
        description="Acute severe allergic reaction with laryngeal edema or respiratory compromise",
        tier=RedFlagTier.TIER_1,
        required_paths=["allergies.acute_anaphylaxis", "symptoms.laryngeal_edema"],
        predicate=_match_rf_imm_001,
    ),
    ClinicalRule(
        rule_id="RF-HEM-001",
        title="Massive Active Hemorrhage",
        description="Massive active hemorrhage or acute hemodynamic instability",
        tier=RedFlagTier.TIER_1,
        required_paths=["symptoms.active_hemorrhage"],
        predicate=_match_rf_hem_001,
    ),

    # Tier 2 Urgent Rules
    ClinicalRule(
        rule_id="RF-CARD-002",
        title="Severe Hypertensive Urgency",
        description="Documented blood pressure exceeding SBP >= 180 mmHg or DBP >= 110 mmHg",
        tier=RedFlagTier.TIER_2,
        required_paths=["vitals.sbp", "vitals.dbp"],
        predicate=_match_rf_card_002,
    ),
    ClinicalRule(
        rule_id="RF-INF-001",
        title="Meningism / Severe Infection Warning",
        description="Fever accompanied by acute neck stiffness or signs of meningeal irritation",
        tier=RedFlagTier.TIER_2,
        required_paths=["symptoms.fever", "symptoms.neck_stiffness"],
        predicate=_match_rf_inf_001,
    ),
    ClinicalRule(
        rule_id="RF-GI-001",
        title="Acute Peritoneal / Abdominal Rigidity",
        description="Severe acute abdominal pain presenting with involuntary guarding or abdominal wall rigidity",
        tier=RedFlagTier.TIER_2,
        required_paths=["symptoms.abdominal_pain", "symptoms.abdominal_rigidity"],
        predicate=_match_rf_gi_001,
    ),
    ClinicalRule(
        rule_id="RF-ENDO-001",
        title="Hyperglycemic Crisis Cluster",
        description="Known diabetes presenting with severe acute vomiting or altered consciousness",
        tier=RedFlagTier.TIER_2,
        required_paths=["past_history.diabetes", "symptoms.severe_vomiting", "symptoms.altered_sensorium"],
        predicate=_match_rf_endo_001,
    ),

    # Tier 3 Clinical Warning Rules
    ClinicalRule(
        rule_id="RF-ALLERGY-001",
        title="Severe Drug Allergy Precaution",
        description="Documented patient history of severe medication allergy or prior anaphylaxis",
        tier=RedFlagTier.TIER_3,
        required_paths=["allergies.severe_drug_allergy", "allergies.anaphylaxis_history"],
        predicate=_match_rf_allergy_001,
    ),
    ClinicalRule(
        rule_id="RF-OB-001",
        title="High-Risk Pregnancy Caution",
        description="Active pregnancy with acute complication indicators requiring obstetric review",
        tier=RedFlagTier.TIER_3,
        required_paths=["patient.is_pregnant", "symptoms.pregnancy_bleeding", "symptoms.severe_headache"],
        predicate=_match_rf_ob_001,
    ),
]


def get_rule_by_id(rule_id: str) -> Optional[ClinicalRule]:
    """Look up a clinical rule by its authoritative identifier."""
    for rule in CLINICAL_RULES_REGISTRY:
        if rule.rule_id == rule_id:
            return rule
    return None
