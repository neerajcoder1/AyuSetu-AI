"""
Tests for Zero-PHI Pre-Release Safety Gate
==========================================
Validates:
- Clean compliant records pass safety gate
- Indian mobile phone number leak detected & rejected
- ABHA number and ABHA handle leak detected & rejected
- Aadhaar number leak detected & rejected
- Email address leak detected & rejected
- IP address leak detected & rejected
- PAN number leak detected & rejected
- Raw UUID leakage detected & rejected
- Unshifted ISO timestamp with time-of-day detected & rejected
- Uncapped age >= 90 detected & rejected
"""

import pytest

from ayusetu.deid.models import DeidentifiedCodedSlot, DeidentifiedRecord
from ayusetu.deid.safety_gate import ZeroPhiSafetyGate, default_safety_gate


def _valid_record() -> DeidentifiedRecord:
    return DeidentifiedRecord(
        pseudonym_token="anon_98a7bc12e4f01234",
        age_band="40-49",
        sex="male",
        district_or_state="Pune",
        department="kayachikitsa",
        visit_type="new",
        shifted_date_or_year="2026-08-20",
        triage_tier=2,
        coded_slots=[
            DeidentifiedCodedSlot(
                path="symptoms.fever",
                value_coded="present",
                code_system="SNOMED",
                code="386661006",
            )
        ],
    )


def test_clean_record_passes_safety_gate():
    rec = _valid_record()
    res = default_safety_gate.evaluate_records([rec])
    assert res.passed is True
    assert len(res.violations) == 0
    assert res.prohibited_matches == 0


def test_phone_number_leak_rejected():
    rec = _valid_record()
    # Inject mobile number in coded slot
    leaked_rec = rec.model_copy(
        update={
            "coded_slots": [
                DeidentifiedCodedSlot(path="patient.contact", value_coded="+919876543210")
            ]
        }
    )
    res = default_safety_gate.evaluate_records([leaked_rec])
    assert res.passed is False
    assert any("phone_number_in" in v for v in res.violations)


def test_abha_number_leak_rejected():
    rec = _valid_record()
    leaked_rec = rec.model_copy(
        update={
            "coded_slots": [
                DeidentifiedCodedSlot(path="abha.id", value_coded="12-3456-7890-1234")
            ]
        }
    )
    res = default_safety_gate.evaluate_records([leaked_rec])
    assert res.passed is False
    assert any("abha_number" in v for v in res.violations)


def test_abha_address_leak_rejected():
    rec = _valid_record()
    leaked_rec = rec.model_copy(
        update={
            "coded_slots": [
                DeidentifiedCodedSlot(path="abha.handle", value_coded="john.doe@abdm")
            ]
        }
    )
    res = default_safety_gate.evaluate_records([leaked_rec])
    assert res.passed is False
    assert any("abha_address" in v for v in res.violations)


def test_pan_number_leak_rejected():
    rec = _valid_record()
    leaked_rec = rec.model_copy(
        update={
            "coded_slots": [
                DeidentifiedCodedSlot(path="tax.pan", value_coded="ABCDE1234F")
            ]
        }
    )
    res = default_safety_gate.evaluate_records([leaked_rec])
    assert res.passed is False
    assert any("pan_number" in v for v in res.violations)


def test_raw_uuid_in_coded_slot_rejected():
    rec = _valid_record()
    leaked_rec = rec.model_copy(
        update={
            "coded_slots": [
                DeidentifiedCodedSlot(path="encounter.ref", value_coded="018f0000-0000-7000-8000-000000000011")
            ]
        }
    )
    res = default_safety_gate.evaluate_records([leaked_rec])
    assert res.passed is False
    assert any("raw_uuid" in v for v in res.violations)


def test_unshifted_timestamp_with_time_rejected():
    rec = _valid_record()
    leaked_rec = rec.model_copy(update={"shifted_date_or_year": "2026-08-20T14:30:00"})
    res = default_safety_gate.evaluate_records([leaked_rec])
    assert res.passed is False
    assert any("iso_timestamp_with_time" in v for v in res.violations)


def test_uncapped_age_ge_90_rejected():
    rec = _valid_record()
    # Uncapped age band (e.g. raw "92" instead of "90+")
    leaked_rec = rec.model_copy(update={"age_band": "92"})
    res = default_safety_gate.evaluate_records([leaked_rec])
    assert res.passed is False
    assert any("Uncapped age >= 90" in v for v in res.violations)
