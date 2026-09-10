"""
Tests for k-Anonymity Evaluator (PRD §21.9)
===========================================
Validates:
- Exact equivalence class computation over the complete approved quasi-identifier set:
  (age_band, sex, district_or_state, department)
- Cohort with all classes >= 5 passes (k_anonymity_achieved = True)
- Cohort with any class < 5 fails closed (k_anonymity_achieved = False)
- Empty or undersized cohort fails closed
"""

import pytest

from ayusetu.deid.k_anonymity import evaluate_k_anonymity
from ayusetu.deid.models import DeidentifiedRecord


def _make_record(age_band: str, sex: str, district: str, dept: str, token_idx: int) -> DeidentifiedRecord:
    return DeidentifiedRecord(
        pseudonym_token=f"anon_{token_idx:04d}",
        age_band=age_band,
        sex=sex,
        district_or_state=district,
        department=dept,
        visit_type="new",
        shifted_date_or_year="2026-08-15",
        triage_tier=3,
        coded_slots=[],
    )


def test_k_anonymity_passes_when_all_classes_ge_5():
    """Verify that when every quasi-identifier equivalence class has >= 5 members, k >= 5 passes."""
    records = []
    idx = 1
    # Class 1: (30-39, male, Bengaluru_Urban, kayachikitsa) -> 6 members
    for _ in range(6):
        records.append(_make_record("30-39", "male", "Bengaluru_Urban", "kayachikitsa", idx))
        idx += 1

    # Class 2: (40-49, female, Pune, panchakarma) -> 5 members
    for _ in range(5):
        records.append(_make_record("40-49", "female", "Pune", "panchakarma", idx))
        idx += 1

    # Class 3: (90+, female, Chennai, shalya_tantra) -> 5 members
    for _ in range(5):
        records.append(_make_record("90+", "female", "Chennai", "shalya_tantra", idx))
        idx += 1

    result = evaluate_k_anonymity(records, k_threshold=5)
    assert result.is_compliant is True
    assert result.min_class_size == 5
    assert result.total_records == 16
    assert result.total_classes == 3


def test_k_anonymity_fails_closed_when_any_class_lt_5():
    """Verify fail-closed behavior when at least one equivalence class has < 5 members."""
    records = []
    idx = 1
    # Class 1: 10 members
    for _ in range(10):
        records.append(_make_record("30-39", "male", "Bengaluru_Urban", "kayachikitsa", idx))
        idx += 1

    # Class 2: Only 2 members (< 5)
    for _ in range(2):
        records.append(_make_record("90+", "male", "Maharashtra", "general_medicine", idx))
        idx += 1

    result = evaluate_k_anonymity(records, k_threshold=5)
    assert result.is_compliant is False
    assert result.min_class_size == 2
    assert result.total_records == 12
    assert result.total_classes == 2


def test_k_anonymity_empty_or_small_dataset():
    """Verify that empty dataset or dataset with < 5 total records fails closed."""
    res_empty = evaluate_k_anonymity([])
    assert res_empty.is_compliant is False
    assert res_empty.min_class_size == 0
    assert res_empty.total_records == 0

    small_records = [_make_record("20-29", "female", "Delhi_South", "kayachikitsa", 1)]
    res_small = evaluate_k_anonymity(small_records, k_threshold=5)
    assert res_small.is_compliant is False
    assert res_small.min_class_size == 1
    assert res_small.total_records == 1
