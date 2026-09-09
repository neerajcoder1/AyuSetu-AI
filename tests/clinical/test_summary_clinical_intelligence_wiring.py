"""
Verifies AC-B4-1 (PRD §23.2): "GIVEN a documented thyroxine prescription and
a patient-reported Guggulu intake, WHEN intelligence runs, THEN a herb–drug
interaction advisory appears in the alerts section."

Before this wiring, ayusetu.ai.clinical.document_ai.clinical_intelligence
was correct and unit-tested in isolation but never called from
SummaryGenerator.generate() — so a real interaction never reached
ClinicalSummary.alerts. These tests exercise the wiring end-to-end through
SummaryGenerator, not the clinical_intelligence functions directly (those
already have their own coverage in test_clinical_intelligence.py).
"""

from contracts.dialogue import ClinicalSlot
from ayusetu.ai.clinical.document_ai.contracts import EntityType, ExtractedEntity
from ayusetu.ai.clinical.red_flags.contracts import RedFlagEvent, Tier
from ayusetu.ai.clinical.summary.composer import SummaryGenerator


def _med_entity(name: str) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=EntityType.MEDICATION,
        raw_text=name,
        normalised={"name": name},
        confidence=0.9,
        page_no=1,
    )


def _lab_entity(analyte: str, value: float) -> ExtractedEntity:
    return ExtractedEntity(
        entity_type=EntityType.LAB_RESULT,
        raw_text=f"{analyte}: {value}",
        normalised={"analyte": analyte, "value": value},
        confidence=0.9,
        page_no=1,
    )


def test_ac_b4_1_herb_drug_interaction_reaches_summary_alerts():
    generator = SummaryGenerator()
    collected_info = {ClinicalSlot.MEDICATIONS: "Guggulu"}
    document_entities = [_med_entity("thyroid medication")]

    summary = generator.generate(
        "enc-1", collected_info, [], document_entities=document_entities
    )

    herb_alerts = [a for a in summary.alerts if a.category == "herb_drug_interaction"]
    assert len(herb_alerts) == 1
    assert "guggulu" in herb_alerts[0].title.lower()
    assert "thyroid medication" in herb_alerts[0].title.lower()
    assert herb_alerts[0].tier is None  # informational, not red-flag-tiered


def test_no_herb_drug_alert_without_the_patient_reported_side():
    generator = SummaryGenerator()
    # Documented thyroxine only — no patient-reported Guggulu anywhere.
    document_entities = [_med_entity("thyroid medication")]

    summary = generator.generate("enc-1", {}, [], document_entities=document_entities)

    assert [a for a in summary.alerts if a.category == "herb_drug_interaction"] == []


def test_abnormal_lab_value_becomes_an_alert():
    generator = SummaryGenerator()
    document_entities = [_lab_entity("hemoglobin", 9.5)]

    summary = generator.generate("enc-1", {}, [], document_entities=document_entities)

    lab_alerts = [a for a in summary.alerts if a.category == "abnormal_lab"]
    assert len(lab_alerts) == 1
    assert "hemoglobin" in lab_alerts[0].title.lower()


def test_drug_drug_interaction_becomes_an_alert():
    generator = SummaryGenerator()
    document_entities = [_med_entity("Warfarin"), _med_entity("Aspirin")]

    summary = generator.generate("enc-1", {}, [], document_entities=document_entities)

    drug_alerts = [a for a in summary.alerts if a.category == "drug_interaction"]
    assert len(drug_alerts) == 1
    assert "severe" in drug_alerts[0].title.lower()


def test_duplicate_therapy_becomes_an_alert():
    generator = SummaryGenerator()
    document_entities = [_med_entity("Amlodipine"), _med_entity("Cilnidipine")]

    summary = generator.generate("enc-1", {}, [], document_entities=document_entities)

    dup_alerts = [a for a in summary.alerts if a.category == "duplicate_therapy"]
    assert len(dup_alerts) == 1
    assert "calcium_channel_blocker" in dup_alerts[0].title


def test_medication_reconciliation_discrepancy_becomes_an_alert():
    generator = SummaryGenerator()
    collected_info = {ClinicalSlot.MEDICATIONS: "Ashwagandha"}
    document_entities = [_med_entity("Metformin")]

    summary = generator.generate("enc-1", collected_info, [], document_entities=document_entities)

    discrepancy_alerts = [a for a in summary.alerts if a.category == "medication_discrepancy"]
    titles = " ".join(a.title.lower() for a in discrepancy_alerts)
    assert "metformin" in titles
    assert "ashwagandha" in titles


def test_no_document_entities_produces_no_intelligence_alerts_and_does_not_crash():
    generator = SummaryGenerator()
    summary = generator.generate("enc-1", {ClinicalSlot.CHIEF_COMPLAINT: "fever"}, [])
    assert summary.alerts == []


def test_red_flag_alerts_and_clinical_intelligence_alerts_coexist():
    generator = SummaryGenerator()
    red_flag_event = RedFlagEvent(
        encounter_id="enc-1",
        rule_id="RF-CARD-01",
        tier=Tier.TIER_1,
        category="cardiac",
        title="Possible acute coronary syndrome",
        trigger_text="chest pain",
        detection_layer="rule",
    )
    document_entities = [_lab_entity("fbs", 180)]

    summary = generator.generate(
        "enc-1",
        {ClinicalSlot.CHIEF_COMPLAINT: "chest pain"},
        [],
        red_flag_events=[red_flag_event],
        document_entities=document_entities,
    )

    categories = {a.category for a in summary.alerts}
    assert categories == {"red_flag", "abnormal_lab"}
    red_flag_alert = next(a for a in summary.alerts if a.category == "red_flag")
    intelligence_alert = next(a for a in summary.alerts if a.category == "abnormal_lab")
    assert red_flag_alert.tier == 1
    assert intelligence_alert.tier is None
