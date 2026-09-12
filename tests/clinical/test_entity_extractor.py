from ayusetu.ai.clinical.document_ai.contracts import EntityType
from ayusetu.ai.clinical.document_ai.entity_extractor import extract_entities


def test_extracts_medication_with_strength_and_frequency():
    text = "Tab. Metformin 500mg 1-0-1 x 5 days"
    entities = extract_entities(text)
    meds = [e for e in entities if e.entity_type == EntityType.MEDICATION]
    assert len(meds) == 1
    assert meds[0].normalised["name"] == "Metformin"
    assert meds[0].normalised["strength"] == "500mg"
    assert meds[0].fhir_resource_type == "MedicationStatement"


def test_extracts_lab_result_with_reference_range_and_flag():
    text = "Hemoglobin: 10.2 g/dL (12.0-15.5) L"
    entities = extract_entities(text)
    labs = [e for e in entities if e.entity_type == EntityType.LAB_RESULT]
    assert len(labs) == 1
    lab = labs[0]
    assert lab.normalised["value"] == 10.2
    assert lab.normalised["reference_low"] == 12.0
    assert lab.normalised["reference_high"] == 15.5
    assert lab.fhir_resource_type == "Observation"
    assert lab.needs_review is False  # full match: range + flag -> high confidence


def test_extracts_vitals():
    text = "BP: 130/85 mmHg  Pulse: 88/min  Temp: 99.2 F  SpO2: 96%"
    entities = extract_entities(text)
    vitals = {e.normalised["vital"]: e for e in entities if e.entity_type == EntityType.VITAL_SIGN}
    assert "blood_pressure" in vitals
    assert vitals["blood_pressure"].normalised["systolic"] == "130"
    assert "pulse" in vitals
    assert "spo2" in vitals


def test_extracts_allergy_with_reaction():
    text = "Allergy: Penicillin - rash"
    entities = extract_entities(text)
    allergies = [e for e in entities if e.entity_type == EntityType.ALLERGY]
    assert len(allergies) == 1
    assert allergies[0].normalised["substance"] == "Penicillin"
    assert allergies[0].normalised["reaction"] == "rash"
    assert allergies[0].fhir_resource_type == "AllergyIntolerance"


def test_no_known_allergies_recorded_as_explicit_negative():
    text = "No known allergies"
    entities = extract_entities(text)
    allergies = [e for e in entities if e.entity_type == EntityType.ALLERGY]
    assert len(allergies) == 1
    assert allergies[0].normalised["status"] == "none_reported"


def test_extracts_diagnosis_with_code():
    text = "Dx: Essential Hypertension (I10)"
    entities = extract_entities(text)
    dx = [e for e in entities if e.entity_type == EntityType.DIAGNOSIS]
    assert len(dx) == 1
    assert dx[0].code == "I10"
    assert dx[0].code_system == "ICD-11"
    assert dx[0].fhir_resource_type == "Condition"


def test_extracts_provider():
    text = "Dr. Ramesh Kumar, Reg No: MCI-12345, City Hospital"
    entities = extract_entities(text)
    providers = [e for e in entities if e.entity_type == EntityType.PROVIDER]
    assert len(providers) == 1
    assert providers[0].normalised["name"].startswith("Ramesh Kumar")
    assert providers[0].fhir_resource_type == "Practitioner"


def test_low_confidence_entities_flagged_for_review():
    # Diagnosis without a code -> partial match -> confidence below threshold.
    text = "Dx: viral fever"
    entities = extract_entities(text)
    dx = [e for e in entities if e.entity_type == EntityType.DIAGNOSIS][0]
    assert dx.confidence < 0.80
    assert dx.needs_review is True


def test_bare_capitalised_word_without_dose_is_not_treated_as_medication():
    text = "Patient reports mild Headache in the morning."
    entities = extract_entities(text)
    meds = [e for e in entities if e.entity_type == EntityType.MEDICATION]
    assert meds == []
