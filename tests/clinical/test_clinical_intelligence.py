from datetime import date

from ayusetu.ai.clinical.document_ai.contracts import EntityType, ExtractedEntity
from ayusetu.ai.clinical.document_ai import clinical_intelligence as ci


def _med(name, strength="500mg", page_no=1):
    return ExtractedEntity(
        entity_type=EntityType.MEDICATION,
        raw_text=f"{name} {strength}",
        normalised={"name": name, "strength": strength},
        confidence=0.9,
        page_no=page_no,
    )


def _lab(analyte, value, low=None, high=None, doc_date=None, page_no=1):
    normalised = {"analyte": analyte, "value": value}
    if low is not None:
        normalised["reference_low"] = low
        normalised["reference_high"] = high
    return ExtractedEntity(
        entity_type=EntityType.LAB_RESULT,
        raw_text=f"{analyte}: {value}",
        normalised=normalised,
        confidence=0.9,
        page_no=page_no,
        doc_date=doc_date,
    )


def test_flags_abnormal_value_using_printed_reference_range():
    flags = ci.flag_abnormal_values([_lab("Hemoglobin", 9.5, low=12.0, high=16.5)])
    assert len(flags) == 1
    assert flags[0].direction == "low"


def test_flags_abnormal_value_using_curated_table_when_no_printed_range():
    flags = ci.flag_abnormal_values([_lab("fbs", 180)])
    assert len(flags) == 1
    assert flags[0].direction == "high"


def test_normal_value_not_flagged():
    flags = ci.flag_abnormal_values([_lab("fbs", 90)])
    assert flags == []


def test_trend_detection_sorted_chronologically():
    entities = [
        _lab("hba1c", 7.2, doc_date=date(2025, 6, 1)),
        _lab("hba1c", 6.1, doc_date=date(2024, 6, 1)),
        _lab("hba1c", 8.0, doc_date=date(2026, 1, 1)),
    ]
    trend = ci.detect_trend(entities, "HbA1c")
    assert [p.value for p in trend] == [6.1, 7.2, 8.0]


def test_drug_drug_interaction_detected():
    entities = [_med("Warfarin"), _med("Aspirin")]
    findings = ci.check_drug_interactions(entities)
    assert len(findings) == 1
    assert findings[0].severity == "severe"


def test_no_interaction_when_only_one_drug_present():
    findings = ci.check_drug_interactions([_med("Warfarin")])
    assert findings == []


def test_herb_drug_interaction_turmeric_anticoagulant():
    entities = [_med("Turmeric"), _med("Anticoagulant")]
    findings = ci.check_herb_drug_interactions(entities)
    assert len(findings) == 1
    assert findings[0].kind == "herb_drug"
    assert findings[0].severity == "severe"


def test_herb_drug_interaction_from_patient_reported_substance():
    entities = [_med("Sedative")]
    findings = ci.check_herb_drug_interactions(entities, reported_substances=["Ashwagandha"])
    assert len(findings) == 1


def test_duplicate_therapy_detection():
    entities = [_med("Amlodipine"), _med("Cilnidipine")]
    findings = ci.detect_duplicate_therapy(entities)
    assert len(findings) == 1
    assert findings[0].drug_class == "calcium_channel_blocker"


def test_medication_reconciliation_finds_discrepancies():
    document_entities = [_med("Metformin")]
    discrepancies = ci.reconcile_medications(
        patient_reported=["metformin", "ashwagandha"], document_entities=document_entities
    )
    by_med = {d.medication: d for d in discrepancies}
    assert "metformin" not in by_med  # matches on both sides -> no discrepancy
    assert by_med["ashwagandha"].reported_by_patient is True
    assert by_med["ashwagandha"].found_in_documents is False
