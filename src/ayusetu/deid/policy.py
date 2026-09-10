"""
De-Identification Policy Definitions & Reference Data
======================================================
Authoritative specifications for PRD v2.0 §21.9 and §21.4:
- Explicit PRD §21.9 Direct & Indirect Identifiers (HIPAA/DISHA/DPDP aligned)
- Extended Security Policy Prohibited Identifiers (India National Health Stack IDs)
- Central Quasi-Identifier Specification for k-anonymity
- Reference District Population Lookup with 20,000 threshold
"""

from typing import Dict, FrozenSet, Set, Tuple

# ---------------------------------------------------------------------------
# PRD §21.9 Explicit Identifiers (Directly Named in AyuSetu PRD v2.0 §21.9)
# ---------------------------------------------------------------------------
PRD_EXPLICIT_IDENTIFIERS: FrozenSet[str] = frozenset({
    "patient_name",               # 1. Names
    "address_below_district",     # 2. Geographic subdivisions smaller than district / state
    "dob_and_exact_dates",        # 3. All elements of dates (except year) & ages > 89 / 90+
    "phone_number",               # 4. Telephone numbers
    "fax_number",                 # 5. Fax numbers
    "email_address",              # 6. Electronic mail addresses
    "national_id",                # 7. National identification numbers (Aadhaar / ABHA)
    "mrn",                        # 8. Medical record numbers
    "health_plan_beneficiary_id", # 9. Health plan beneficiary numbers
    "account_number",             # 10. Account numbers
    "certificate_license_number", # 11. Certificate / license numbers
    "vehicle_identifier",         # 12. Vehicle identifiers and serial numbers
    "device_identifier",          # 13. Device identifiers and serial numbers
    "web_url",                    # 14. Web Universal Resource Locators (URLs)
    "ip_address",                 # 15. Internet Protocol (IP) address numbers
    "biometric_identifier",       # 16. Biometric identifiers (voice prints, fingerprints)
    "face_photo",                 # 17. Full face photographic images and comparable images
    "unique_identifying_number",  # 18. Any other unique identifying number, characteristic, or code
})

# ---------------------------------------------------------------------------
# Extended Security Policy Prohibited Identifiers (India National Stack & AyuSetu Ext)
# ---------------------------------------------------------------------------
EXTENDED_SECURITY_POLICY_IDENTIFIERS: FrozenSet[str] = frozenset({
    "pan_number",                 # Income Tax Permanent Account Number
    "voter_id_epic",              # Election Commission Voter ID
    "passport_number",            # Passport number
    "ration_card_number",         # PDS Ration Card
    "driving_license",            # State Motor Vehicle Driving License
    "ayushman_bharat_pmjay_id",   # PM-JAY Beneficiary ID
    "raw_encounter_uuid",         # AyuSetu internal raw encounter UUID
    "raw_patient_uuid",           # AyuSetu internal raw patient UUID
    "clinician_name",             # Provider / Doctor name
    "facility_name_sub_district", # Primary Health Center / Clinic specific name below district
})

# Combined prohibited identifier set
ALL_PROHIBITED_IDENTIFIERS: FrozenSet[str] = PRD_EXPLICIT_IDENTIFIERS | EXTENDED_SECURITY_POLICY_IDENTIFIERS

# ---------------------------------------------------------------------------
# Approved Quasi-Identifier Set for k-Anonymity (PRD §21.9)
# ---------------------------------------------------------------------------
APPROVED_QUASI_IDENTIFIERS: Tuple[str, ...] = (
    "age_band",
    "sex",
    "district_or_state",
    "department",
)

# Minimum k-anonymity threshold per PRD §21.9
MIN_K_ANONYMITY_THRESHOLD: int = 5

# District population aggregation threshold per PRD §21.9
DISTRICT_POPULATION_THRESHOLD: int = 20_000

# ---------------------------------------------------------------------------
# Reference District Population Lookup Table
# Districts with population >= 20,000 retain district name.
# Districts with population < 20,000 aggregate to enclosing State.
# ---------------------------------------------------------------------------
DISTRICT_POPULATION_REGISTRY: Dict[str, Tuple[int, str]] = {
    # District Name -> (Estimated Population in catchment, Enclosing State)
    # Major districts (>= 20,000)
    "bengaluru_urban": (9621551, "Karnataka"),
    "bengaluru_rural": (990923, "Karnataka"),
    "mysuru": (3001127, "Karnataka"),
    "dharwad": (1847023, "Karnataka"),
    "dakshina_kannada": (2089649, "Karnataka"),
    "belagavi": (4779661, "Karnataka"),
    "mumbai_city": (3085411, "Maharashtra"),
    "mumbai_suburban": (9356962, "Maharashtra"),
    "pune": (9429408, "Maharashtra"),
    "nagpur": (4653570, "Maharashtra"),
    "thane": (11060148, "Maharashtra"),
    "chennai": (7088000, "Tamil Nadu"),
    "coimbatore": (3458045, "Tamil Nadu"),
    "madurai": (3038252, "Tamil Nadu"),
    "hyderabad": (6809970, "Telangana"),
    "rangareddy": (5296741, "Telangana"),
    "delhi_central": (582320, "Delhi"),
    "delhi_south": (2731929, "Delhi"),
    "lucknow": (4589838, "Uttar Pradesh"),
    "varanasi": (3676841, "Uttar Pradesh"),
    "patna": (5838465, "Bihar"),
    "kolkata": (4496694, "West Bengal"),
    "jaipur": (6626178, "Rajasthan"),
    "ahmedabad": (7214225, "Gujarat"),
    "bhopal": (2371061, "Madhya Pradesh"),
    "indore": (3276697, "Madhya Pradesh"),
    "thiruvananthapuram": (3301427, "Kerala"),
    "ernakulam": (3282388, "Kerala"),
    "kamrup_metropolitan": (1253938, "Assam"),
    "ranchi": (2914253, "Jharkhand"),
    "bhubaneswar_khordha": (2251673, "Odisha"),
    
    # Boundary & Small Sparsely Populated Districts / Enclaves (< 20,000)
    "lahul_and_spiti_remote_block": (15200, "Himachal Pradesh"),
    "dibang_valley_upper": (8004, "Arunachal Pradesh"),
    "anjaw_north": (12300, "Arunachal Pradesh"),
    "nicobar_remote_tribal": (18400, "Andaman and Nicobar Islands"),
    "mahe_rural_pocket": (14800, "Puducherry"),
    "lakshadweep_minicoy": (10200, "Lakshadweep"),
    "upper_siang_remote": (19100, "Arunachal Pradesh"),
    "test_micro_district": (5000, "Karnataka"),
    "test_boundary_district_19999": (19999, "Maharashtra"),
    "test_boundary_district_20000": (20000, "Maharashtra"),
}
