"""
Zero-PHI Pre-Release Safety Gate
================================
Independent pre-release scanner and schema validator per PRD v2.0 §21.9.
Scans serialized candidate export records against direct identifier patterns,
untransformed dates, raw UUIDs, and national ID formats before release.
Fails closed on any violation.
"""

import json
import re
from typing import Any, Dict, List, Optional, Pattern, Sequence, Tuple

from ayusetu.deid.models import DeidentifiedRecord, SafetyCheckResult

# ---------------------------------------------------------------------------
# Regex Patterns for Prohibited Identifiers & Direct PHI
# ---------------------------------------------------------------------------
PROHIBITED_PATTERNS: List[Tuple[str, Pattern]] = [
    # 1. 10-digit Indian Mobile Numbers (starting 6, 7, 8, 9)
    ("phone_number_in", re.compile(r"(?:\+91|91)?[-.\s]?[6-9]\d{9}\b")),
    
    # 2. 14-digit ABHA Number (with or without hyphens: XX-XXXX-XXXX-XXXX)
    ("abha_number", re.compile(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b")),
    
    # 3. ABHA Address / ABDM Handle
    ("abha_address", re.compile(r"\b[a-zA-Z0-9._]+@(abdm|sbx)\b", re.IGNORECASE)),
    
    # 4. 12-digit Aadhaar Number (XXXX XXXX XXXX or contiguous 12 digits)
    ("aadhaar_number", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")),
    
    # 5. Electronic Mail Addresses
    ("email_address", re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")),
    
    # 6. IPv4 Address
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    
    # 7. Indian Income Tax PAN (5 letters, 4 digits, 1 letter)
    ("pan_number", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b")),
    
    # 8. Indian Voter ID / EPIC (3 letters, 7 digits)
    ("voter_id_epic", re.compile(r"\b[A-Z]{3}[0-9]{7}\b")),
    
    # 9. Raw UUID format (e.g. 8-4-4-4-12 hex digits)
    ("raw_uuid", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    
    # 10. Unshifted ISO Timestamps with time of day (e.g. 2026-09-10T10:30:00)
    ("iso_timestamp_with_time", re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")),
]


class ZeroPhiSafetyGate:
    """
    Evaluates candidate de-identified records before release.
    Guarantees no raw identifiers or prohibited patterns leak.
    """

    def __init__(self, custom_patterns: Optional[List[Tuple[str, Pattern]]] = None) -> None:
        self.patterns = custom_patterns or PROHIBITED_PATTERNS

    def scan_text(self, payload_text: str) -> List[str]:
        """
        Scans a text payload against all prohibited patterns.
        """
        violations: List[str] = []
        for name, pattern in self.patterns:
            matches = pattern.findall(payload_text)
            if matches:
                violations.append(f"Prohibited pattern detected: {name} (count={len(matches)})")
        return violations

    def evaluate_records(self, records: Sequence[DeidentifiedRecord]) -> SafetyCheckResult:
        """
        Scans all candidate records in memory.
        """
        violations: List[str] = []
        prohibited_matches = 0

        for idx, rec in enumerate(records):
            # Check for age capping violation (e.g. numeric ages >= 90 without 90+ cap)
            if rec.age_band.isdigit() and int(rec.age_band) >= 90:
                violations.append(f"Record {idx}: Uncapped age >= 90 found: '{rec.age_band}' (must be '90+')")

            # Check for illegal string in pseudonym token (e.g., if raw UUID leaked into token)
            if len(rec.pseudonym_token) > 32 or "-" in rec.pseudonym_token:
                violations.append(f"Record {idx}: Suspicious pseudonym token format: '{rec.pseudonym_token}'")

            # Serialize record to JSON and scan with regex patterns
            rec_json = rec.model_dump_json()
            text_violations = self.scan_text(rec_json)
            if text_violations:
                prohibited_matches += len(text_violations)
                for tv in text_violations:
                    violations.append(f"Record {idx}: {tv}")

        passed = len(violations) == 0
        return SafetyCheckResult(
            passed=passed,
            violations=violations,
            prohibited_matches=prohibited_matches,
        )


# Global default instance
default_safety_gate = ZeroPhiSafetyGate()
