"""
Tests for De-Identification Policy and Transformation Engine
============================================================
Validates:
- Explicit PRD §21.9 18 Direct & Indirect Identifiers
- Extended Security Policy Prohibited Identifiers
- Centrally defined quasi-identifier specification
- District population >= 20,000 threshold and State aggregation
- Per-patient consistent cryptographically secure date shifting in [-30, +30]
- >3-year-old date generalization to Year-Only (YYYY)
- Age calculation with 90+ capping (without corrupting DOB computation)
- Structured coded slot extraction and free-text narrative suppression
"""

from datetime import date, datetime, timedelta
import pytest

from ayusetu.deid.engine import (
    PatientDateShifter,
    compute_age_band,
    extract_coded_slots,
    generate_pseudonym_token,
    resolve_district_or_state,
    transform_raw_encounter_to_deidentified,
)
from ayusetu.deid.policy import (
    ALL_PROHIBITED_IDENTIFIERS,
    APPROVED_QUASI_IDENTIFIERS,
    DISTRICT_POPULATION_THRESHOLD,
    EXTENDED_SECURITY_POLICY_IDENTIFIERS,
    MIN_K_ANONYMITY_THRESHOLD,
    PRD_EXPLICIT_IDENTIFIERS,
)


def test_prd_21_9_identifier_definitions():
    """Verify that PRD §21.9 explicit identifiers and extended policy are properly encoded."""
    assert len(PRD_EXPLICIT_IDENTIFIERS) == 18
    assert "patient_name" in PRD_EXPLICIT_IDENTIFIERS
    assert "phone_number" in PRD_EXPLICIT_IDENTIFIERS
    assert "dob_and_exact_dates" in PRD_EXPLICIT_IDENTIFIERS
    assert "national_id" in PRD_EXPLICIT_IDENTIFIERS
    assert "mrn" in PRD_EXPLICIT_IDENTIFIERS
    assert "biometric_identifier" in PRD_EXPLICIT_IDENTIFIERS
    assert "face_photo" in PRD_EXPLICIT_IDENTIFIERS
    assert "ip_address" in PRD_EXPLICIT_IDENTIFIERS

    # Verify extended security policy
    assert "pan_number" in EXTENDED_SECURITY_POLICY_IDENTIFIERS
    assert "voter_id_epic" in EXTENDED_SECURITY_POLICY_IDENTIFIERS
    assert "passport_number" in EXTENDED_SECURITY_POLICY_IDENTIFIERS
    assert "driving_license" in EXTENDED_SECURITY_POLICY_IDENTIFIERS
    assert "raw_patient_uuid" in EXTENDED_SECURITY_POLICY_IDENTIFIERS

    # Total prohibited set
    assert ALL_PROHIBITED_IDENTIFIERS == (PRD_EXPLICIT_IDENTIFIERS | EXTENDED_SECURITY_POLICY_IDENTIFIERS)


def test_approved_quasi_identifiers():
    """Verify approved quasi-identifiers and k threshold."""
    assert APPROVED_QUASI_IDENTIFIERS == ("age_band", "sex", "district_or_state", "department")
    assert MIN_K_ANONYMITY_THRESHOLD == 5
    assert DISTRICT_POPULATION_THRESHOLD == 20_000


def test_district_population_aggregation():
    """
    Test PRD §21.9 geography rule:
    - District >= 20,000 -> Retain district
    - District < 20,000 -> Aggregate to enclosing State
    - Unknown district -> Aggregate to State
    """
    # Large districts >= 20,000
    assert resolve_district_or_state("bengaluru_urban") == "Bengaluru_Urban"
    assert resolve_district_or_state("pune") == "Pune"
    assert resolve_district_or_state("mumbai_city") == "Mumbai_City"
    assert resolve_district_or_state("chennai") == "Chennai"

    # Boundary test: exactly 20,000 -> Retained
    assert resolve_district_or_state("test_boundary_district_20000") == "Test_Boundary_District_20000"

    # Boundary test: 19,999 -> Aggregated to State
    assert resolve_district_or_state("test_boundary_district_19999") == "Maharashtra"

    # Small districts < 20,000 -> Aggregated to State
    assert resolve_district_or_state("lahul_and_spiti_remote_block") == "Himachal Pradesh"
    assert resolve_district_or_state("dibang_valley_upper") == "Arunachal Pradesh"
    assert resolve_district_or_state("test_micro_district") == "Karnataka"

    # Unknown district with known state -> State
    assert resolve_district_or_state("non_existent_village", state="Rajasthan") == "Rajasthan"
    # Unknown district without state -> Aggregated State
    assert resolve_district_or_state("random_place") == "Aggregated State"


def test_age_banding_and_90_plus_capping():
    """
    Test PRD §21.9 age calculation:
    - Standard 10-year bands
    - 90 and above MUST be represented as '90+'
    """
    ref = date(2026, 9, 10)

    # 90+ Capping (PRD §21.9)
    assert compute_age_band(date(1936, 1, 1), reference_date=ref) == "90+"
    assert compute_age_band(date(1920, 5, 15), reference_date=ref) == "90+"
    assert compute_age_band(90, reference_date=ref) == "90+"
    assert compute_age_band(95, reference_date=ref) == "90+"
    assert compute_age_band(104, reference_date=ref) == "90+"

    # Standard 10-year bands
    assert compute_age_band(date(2020, 1, 1), reference_date=ref) == "0-9"
    assert compute_age_band(date(2012, 1, 1), reference_date=ref) == "10-19"
    assert compute_age_band(date(2000, 1, 1), reference_date=ref) == "20-29"
    assert compute_age_band(date(1985, 1, 1), reference_date=ref) == "40-49"
    assert compute_age_band(date(1940, 1, 1), reference_date=ref) == "80-89"
    assert compute_age_band(25, reference_date=ref) == "20-29"


def test_patient_date_shifter_consistency_and_bounds():
    """
    Test cryptographically secure per-patient date shifting:
    - Offset drawn from [-30, +30]
    - Consistent across all dates for the same patient
    - Independent across different patients
    - >3 years old dates generalized to Year-Only (YYYY)
    """
    shifter = PatientDateShifter()
    ref = date(2026, 9, 10)

    pt1 = "patient_uuid_001"
    pt2 = "patient_uuid_002"

    offset_1 = shifter.get_offset_for_patient(pt1)
    offset_2 = shifter.get_offset_for_patient(pt2)

    assert -30 <= offset_1 <= 30
    assert -30 <= offset_2 <= 30

    # Consistency: repeated calls return same offset
    assert shifter.get_offset_for_patient(pt1) == offset_1

    # Date transformation for recent date (<= 3 years old)
    raw_d1 = date(2026, 8, 1)
    raw_d2 = date(2026, 8, 15)

    res_d1 = shifter.transform_date(raw_d1, patient_key=pt1, reference_date=ref)
    res_d2 = shifter.transform_date(raw_d2, patient_key=pt1, reference_date=ref)

    expected_d1 = (raw_d1 + timedelta(days=offset_1)).strftime("%Y-%m-%d")
    expected_d2 = (raw_d2 + timedelta(days=offset_1)).strftime("%Y-%m-%d")

    assert res_d1 == expected_d1
    assert res_d2 == expected_d2

    # Chronological preservation: res_d2 must remain 14 days after res_d1
    parsed_1 = datetime.strptime(res_d1, "%Y-%m-%d").date()
    parsed_2 = datetime.strptime(res_d2, "%Y-%m-%d").date()
    assert (parsed_2 - parsed_1).days == 14

    # Date transformation for > 3 years old date -> Year-Only (YYYY)
    old_date = date(2020, 5, 20)
    assert shifter.transform_date(old_date, patient_key=pt1, reference_date=ref) == "2020"


def test_extract_coded_slots_discards_narrative():
    """Verify that narrative text, long notes, and unstandardized free text are dropped."""
    raw_facts = [
        {"path": "symptoms.fever", "value_coded": "present", "code_system": "SNOMED", "code": "386661006"},
        {"path": "vitals.spo2", "numeric_value": 98.0},
        {"path": "clinical_note.history", "value_coded": "Patient is a 45-year-old male who presented with severe chest pain and radiating pain to left arm after climbing stairs."},  # Narrative -> DROPPED
        {"path": "symptoms.cough", "boolean_value": True},
    ]

    coded = extract_coded_slots(raw_facts)
    assert len(coded) == 3
    paths = [c.path for c in coded]
    assert "symptoms.fever" in paths
    assert "vitals.spo2" in paths
    assert "symptoms.cough" in paths
    assert "clinical_note.history" not in paths


def test_transform_raw_encounter_to_deidentified():
    """Verify end-to-end single record transformation."""
    shifter = PatientDateShifter()
    raw = {
        "patient_id": "018f0000-0000-7000-8000-000000000099",
        "dob": "1995-04-12",
        "gender": "male",
        "district": "mysuru",
        "state": "Karnataka",
        "department": "Kayachikitsa",
        "encounter_date": "2026-08-10",
        "triage_tier": 2,
        "slots": [
            {"path": "symptoms.fever", "value_coded": "high"},
            {"path": "vitals.pulse", "numeric_value": 88},
        ],
    }

    deid = transform_raw_encounter_to_deidentified(raw, shifter=shifter)
    assert deid.pseudonym_token.startswith("anon_")
    assert "018f0000" not in deid.pseudonym_token
    assert deid.age_band == "30-39"
    assert deid.sex == "male"
    assert deid.district_or_state == "Mysuru"
    assert deid.department == "kayachikitsa"
    assert deid.triage_tier == 2
    assert len(deid.coded_slots) == 2
