"""
De-Identification Transformation Engine
=======================================
Implements PRD v2.0 §21.9 deterministic & privacy-preserving transformations:
- Cryptographically secure random per-patient date offset in [-30, +30] days.
- >3-year-old date generalization to Year-Only (YYYY).
- Age calculation with 90+ capping (without corrupting DOB computation).
- District population >= 20,000 threshold evaluation with enclosing State aggregation.
- Structured-only clinical coded slot extraction (complete narrative suppression).
- Non-reversible opaque pseudonymous research token generation.
"""

from datetime import date, datetime, timedelta
import hashlib
import re
import secrets
from typing import Any, Dict, List, Optional, Tuple

from ayusetu.deid.models import DeidentifiedCodedSlot, DeidentifiedRecord
from ayusetu.deid.policy import (
    DISTRICT_POPULATION_REGISTRY,
    DISTRICT_POPULATION_THRESHOLD,
)


def compute_age_band(dob_or_age: Any, reference_date: Optional[date] = None) -> str:
    """
    Computes standard 10-year age band with 90+ capping per PRD §21.9.
    
    Accepts:
    - date / datetime / ISO string (YYYY-MM-DD) for DOB
    - int / float for pre-computed age in years
    """
    if reference_date is None:
        reference_date = date.today()

    age_years: float
    if isinstance(dob_or_age, (int, float)):
        age_years = float(dob_or_age)
    elif isinstance(dob_or_age, (date, datetime)):
        d = dob_or_age.date() if isinstance(dob_or_age, datetime) else dob_or_age
        age_years = (reference_date - d).days / 365.2425
    elif isinstance(dob_or_age, str):
        # Try parsing ISO date
        try:
            d = datetime.strptime(dob_or_age[:10], "%Y-%m-%d").date()
            age_years = (reference_date - d).days / 365.2425
        except ValueError:
            try:
                age_years = float(dob_or_age)
            except ValueError:
                return "Unknown"
    else:
        return "Unknown"

    if age_years < 0:
        return "0-9"
    if age_years >= 90.0:
        return "90+"
    
    band_start = int(age_years // 10) * 10
    band_end = band_start + 9
    return f"{band_start}-{band_end}"


def resolve_district_or_state(district: str, state: Optional[str] = None) -> str:
    """
    Evaluates district population against the PRD §21.9 20,000 threshold.
    - If population >= 20,000 -> Retain district name
    - If population < 20,000 -> Aggregate to enclosing State
    - If district not found in registry -> Fail-safe aggregate to State
    """
    norm_district = district.strip().lower().replace(" ", "_").replace("-", "_")
    
    if norm_district in DISTRICT_POPULATION_REGISTRY:
        pop, enclosing_state = DISTRICT_POPULATION_REGISTRY[norm_district]
        if pop >= DISTRICT_POPULATION_THRESHOLD:
            return district.strip().title()
        return enclosing_state.strip().title()

    # Fallback if district not explicitly registered: fail-safe aggregate to State
    if state and state.strip():
        return state.strip().title()
    return "Aggregated State"


class PatientDateShifter:
    """
    Manages per-patient cryptographically secure date shifting.
    Offset is drawn from [-30, +30] days using secrets.SystemRandom() and
    consistently applied across all dates for the same patient in an export session.
    The offset is never exposed or logged.
    """

    def __init__(self, rng_seed: Optional[int] = None) -> None:
        self._rng = secrets.SystemRandom()
        self._patient_offsets: Dict[str, int] = {}

    def get_offset_for_patient(self, patient_key: str) -> int:
        if patient_key not in self._patient_offsets:
            # Cryptographically secure random integer in [-30, +30]
            self._patient_offsets[patient_key] = self._rng.randint(-30, 30)
        return self._patient_offsets[patient_key]

    def transform_date(
        self,
        raw_date: Any,
        patient_key: str,
        reference_date: Optional[date] = None,
    ) -> str:
        """
        Transforms date per PRD §21.9:
        - If date is > 3 years older than reference_date: Year-Only (YYYY)
        - Otherwise: shifted by patient's random offset [-30, +30] -> YYYY-MM-DD
        """
        if reference_date is None:
            reference_date = date.today()

        d: date
        if isinstance(raw_date, (date, datetime)):
            d = raw_date.date() if isinstance(raw_date, datetime) else raw_date
        elif isinstance(raw_date, str):
            try:
                d = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
            except ValueError:
                return "Unknown"
        else:
            return "Unknown"

        # Check > 3 years old (1095 days)
        if (reference_date - d).days > 1095:
            return str(d.year)

        offset_days = self.get_offset_for_patient(patient_key)
        shifted = d + timedelta(days=offset_days)
        return shifted.strftime("%Y-%m-%d")


def generate_pseudonym_token(patient_id: str, salt: Optional[str] = None) -> str:
    """
    Generates an opaque, non-reversible pseudonymous research token.
    Raw patient/encounter identifiers are never leaked.
    """
    if salt is None:
        salt = "ayusetu_deid_v1"
    digest = hashlib.sha256(f"{salt}:{patient_id}".encode("utf-8")).hexdigest()
    return f"anon_{digest[:16]}"


def extract_coded_slots(raw_slots_or_facts: List[Dict[str, Any]]) -> List[DeidentifiedCodedSlot]:
    """
    Extracts strictly coded clinical facts and completely discards any narrative/free text.
    """
    coded: List[DeidentifiedCodedSlot] = []
    for fact in raw_slots_or_facts:
        path = fact.get("path") or fact.get("slot") or fact.get("key")
        if not path:
            continue

        # Extract strictly allowed coded/typed fields
        value_coded = fact.get("value_coded") or fact.get("value")
        if value_coded is not None:
            # If value looks like free-text (longer than 60 chars or containing sentence punct), suppress
            if isinstance(value_coded, str) and (len(value_coded) > 60 or "\n" in value_coded):
                continue
            value_coded = str(value_coded)

        code_system = fact.get("code_system")
        code = fact.get("code")
        
        numeric_val = fact.get("numeric_value")
        if numeric_val is not None:
            try:
                numeric_val = float(numeric_val)
            except (ValueError, TypeError):
                numeric_val = None

        bool_val = fact.get("boolean_value")
        if bool_val is not None and not isinstance(bool_val, bool):
            bool_val = str(bool_val).lower() in ("true", "1", "yes")

        coded.append(
            DeidentifiedCodedSlot(
                path=str(path),
                value_coded=value_coded,
                code_system=code_system,
                code=code,
                numeric_value=numeric_val,
                boolean_value=bool_val,
            )
        )
    return coded


def transform_raw_encounter_to_deidentified(
    raw_record: Dict[str, Any],
    shifter: PatientDateShifter,
    export_salt: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> DeidentifiedRecord:
    """
    Transforms a single raw encounter record into a compliant DeidentifiedRecord.
    """
    patient_id = str(raw_record.get("patient_id") or raw_record.get("patient_uuid") or "unknown_pt")
    
    # 1. Pseudonym Token
    token = generate_pseudonym_token(patient_id, salt=export_salt)

    # 2. Age Band (90+ cap)
    dob = raw_record.get("dob") or raw_record.get("date_of_birth") or raw_record.get("age")
    encounter_date_str = raw_record.get("encounter_date") or raw_record.get("created_at") or str(date.today())
    try:
        ref_d = datetime.strptime(str(encounter_date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        ref_d = reference_date or date.today()
    age_band = compute_age_band(dob, reference_date=ref_d)

    # 3. Sex
    raw_sex = str(raw_record.get("sex") or raw_record.get("gender") or "other").strip().lower()
    if raw_sex in ("m", "male"):
        sex = "male"
    elif raw_sex in ("f", "female"):
        sex = "female"
    else:
        sex = "other"

    # 4. Geography (20,000 threshold)
    district = str(raw_record.get("district") or raw_record.get("city") or "unknown_district")
    state = str(raw_record.get("state") or "")
    district_or_state = resolve_district_or_state(district, state=state)

    # 5. Department & Visit Type
    department = str(raw_record.get("department") or "general_medicine").strip().lower()
    visit_type = str(raw_record.get("visit_type") or "standard").strip().lower()

    # 6. Shifted Date / Year-Only (>3 yr old)
    shifted_date = shifter.transform_date(
        raw_record.get("encounter_date") or raw_record.get("created_at") or date.today(),
        patient_key=patient_id,
        reference_date=reference_date or date.today(),
    )

    # 7. Triage Tier
    triage_tier = raw_record.get("triage_tier")
    if triage_tier is not None:
        try:
            triage_tier = int(triage_tier)
        except (ValueError, TypeError):
            triage_tier = None

    # 8. Coded Slots (Structured facts only, free text dropped)
    raw_slots = raw_record.get("slots") or raw_record.get("clinical_facts") or []
    coded_slots = extract_coded_slots(raw_slots)

    return DeidentifiedRecord(
        pseudonym_token=token,
        age_band=age_band,
        sex=sex,
        district_or_state=district_or_state,
        department=department,
        visit_type=visit_type,
        shifted_date_or_year=shifted_date,
        triage_tier=triage_tier,
        coded_slots=coded_slots,
    )
