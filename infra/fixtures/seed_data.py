"""
Seed Fixtures for AyuSetu Development and Testing
==================================================
Deterministic synthetic records based on PRD v2.0 §6.1 and §24.1 Step 2.
"""

from datetime import date, datetime, timezone, timedelta
import uuid6

# Fixed deterministic UUIDs for reproducible testing
PATIENT_1_ID = uuid6.UUID("018f0000-0000-7000-8000-000000000001")
PATIENT_2_ID = uuid6.UUID("018f0000-0000-7000-8000-000000000002")
PATIENT_3_ID = uuid6.UUID("018f0000-0000-7000-8000-000000000003")

ENCOUNTER_1_ID = uuid6.UUID("018f0000-0000-7000-8000-000000000011")
ENCOUNTER_2_ID = uuid6.UUID("018f0000-0000-7000-8000-000000000012")
ENCOUNTER_3_ID = uuid6.UUID("018f0000-0000-7000-8000-000000000013")

NOW = datetime.now(timezone.utc)

SEED_PATIENTS = [
    {
        "id": PATIENT_1_ID,
        "abha_id": None,  # Provisional, no ABHA
        "mrn": "MRN-AIIA-2026-001",
        "name_enc": b"Kamala Devi (Encrypted)",
        "mobile_enc": b"+919876543210 (Encrypted)",
        "dob": date(1963, 5, 12),
        "sex": "female",
        "district": "Patna",
        "is_provisional": True,
        "created_at": NOW - timedelta(days=2),
        "merged_into": None,
    },
    {
        "id": PATIENT_2_ID,
        "abha_id": "91-1234-5678-9012",
        "mrn": "MRN-AIIA-2026-002",
        "name_enc": b"Rakesh Kumar (Encrypted)",
        "mobile_enc": b"+919811223344 (Encrypted)",
        "dob": date(1998, 8, 20),
        "sex": "male",
        "district": "South Delhi",
        "is_provisional": False,
        "created_at": NOW - timedelta(days=30),
        "merged_into": None,
    },
    {
        "id": PATIENT_3_ID,
        "abha_id": "91-9876-5432-1098",
        "mrn": "MRN-AIIA-2026-003",
        "name_enc": b"Arun Sharma (Encrypted)",
        "mobile_enc": b"+919988776655 (Encrypted)",
        "dob": date(1992, 11, 4),
        "sex": "male",
        "district": "Patna",
        "is_provisional": False,
        "created_at": NOW - timedelta(days=5),
        "merged_into": None,
    }
]

SEED_ENCOUNTERS = [
    {
        "id": ENCOUNTER_1_ID,
        "patient_id": PATIENT_1_ID,
        "department": "Kayachikitsa",
        "visit_type": "new",
        "intake_depth": "full",
        "channel": "kiosk",
        "reported_by": "companion",
        "language": "hi",
        "started_at": NOW - timedelta(minutes=45),
        "submitted_at": NOW - timedelta(minutes=35),
        "status": "submitted",
    },
    {
        "id": ENCOUNTER_2_ID,
        "patient_id": PATIENT_2_ID,
        "department": "Panchakarma",
        "visit_type": "followup_stable",
        "intake_depth": "interval",
        "channel": "pwa_self",
        "reported_by": "patient",
        "language": "en",
        "started_at": NOW - timedelta(hours=2),
        "submitted_at": NOW - timedelta(hours=2, minutes=-5),
        "status": "final",
    },
    {
        "id": ENCOUNTER_3_ID,
        "patient_id": PATIENT_3_ID,
        "department": "Shalya Tantra",
        "visit_type": "walkin",
        "intake_depth": "fast",
        "channel": "assisted",
        "reported_by": "attendant",
        "language": "hi",
        "started_at": NOW - timedelta(minutes=15),
        "submitted_at": None,
        "status": "draft",
    }
]

SEED_SLOTS = [
    {
        "id": uuid6.uuid7(),
        "encounter_id": ENCOUNTER_1_ID,
        "path": "chief_complaint",
        "value": {"text": "पेट में जलन और खट्टी डकारें", "duration": "3 months"},
        "value_coded": "Amlapitta",
        "confidence": 0.94,
        "source": "utterance",
        "reported_by": "companion",
        "elicited": True,
    },
    {
        "id": uuid6.uuid7(),
        "encounter_id": ENCOUNTER_1_ID,
        "path": "ayush.prakriti",
        "value": {"vata": 0.44, "pitta": 0.38, "kapha": 0.18, "dominant": "vata-pitta"},
        "value_coded": "vata-pitta",
        "confidence": 0.72,
        "source": "derived",
        "reported_by": "companion",
        "elicited": True,
    },
    {
        "id": uuid6.uuid7(),
        "encounter_id": ENCOUNTER_1_ID,
        "path": "allergies",
        "value": {"drug": "none known", "food": "none known"},
        "value_coded": None,
        "confidence": 0.99,
        "source": "touch",
        "reported_by": "companion",
        "elicited": True,
    }
]

SEED_CONSENTS = [
    {
        "id": uuid6.uuid7(),
        "patient_id": PATIENT_1_ID,
        "encounter_id": ENCOUNTER_1_ID,
        "purposes": {"clinical": True, "abdm": True, "qi": False, "research": False},
        "language": "hi",
        "notice_version": "dpdp-v1.0-2026",
        "granted_at": NOW - timedelta(minutes=44),
        "withdrawn_at": None,
        "abdm_artefact_id": None,
        "chain_hash": b"dummy_hash_chain_entry_1",
    },
    {
        "id": uuid6.uuid7(),
        "patient_id": PATIENT_2_ID,
        "encounter_id": ENCOUNTER_2_ID,
        "purposes": {"clinical": True, "abdm": True, "qi": True, "research": True},
        "language": "en",
        "notice_version": "dpdp-v1.0-2026",
        "granted_at": NOW - timedelta(hours=2),
        "withdrawn_at": None,
        "abdm_artefact_id": "ABDM-ART-2026-000921",
        "chain_hash": b"dummy_hash_chain_entry_2",
    }
]
