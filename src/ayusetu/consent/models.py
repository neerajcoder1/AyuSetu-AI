"""
Consent & DPDP Domain and API Models
====================================
Data contracts and models for DPDP consent records, granular purposes,
guardian verification, offline consent payloads, erasure, and ABDM artifact status
per PRD v2.0 §21.7 & §21.8.

AUTHORITATIVE SCHEMA NOTE:
`packages/schemas/consent_record.json` is the single source of truth for the
external payload contract. Fields such as `version`, `status`, and `guardian_id`
are domain model properties that extend the base contract for versioning and verification.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Purposes(BaseModel):
    """
    Authoritative four-purpose consent structure per PRD §21.7.
    
    1. clinical: Mandatory for clinical intake and audio capture.
    2. abdm: Independently consented for ABDM external linkage. Defaults to False.
    3. qi: Opt-in for de-identified quality improvement. Defaults to False.
    4. research: Opt-in for de-identified research. Defaults to False.
    """
    clinical: bool = Field(..., description="Consent for clinical intake and speech processing")
    abdm: bool = Field(default=False, description="Consent for ABDM registry linkage (opt-in)")
    qi: bool = Field(default=False, description="Consent for de-identified quality improvement (opt-in)")
    research: bool = Field(default=False, description="Consent for de-identified research (opt-in)")

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Purposes":
        return cls(
            clinical=bool(d.get("clinical", False)),
            abdm=bool(d.get("abdm", False)),
            qi=bool(d.get("qi", False)),
            research=bool(d.get("research", False)),
        )

    def to_dict(self) -> Dict[str, bool]:
        return {
            "clinical": self.clinical,
            "abdm": self.abdm,
            "qi": self.qi,
            "research": self.research,
        }


class GuardianRelationship(str, Enum):
    PARENT = "parent"
    LEGAL_GUARDIAN = "legal_guardian"
    COURT_APPOINTED = "court_appointed"


class GuardianContext(BaseModel):
    """
    Guardian consent context for under-18 minors per PRD §21.7.
    Client-supplied booleans are NOT trusted; verification is evaluated
    strictly by GuardianVerificationAdapter.
    """
    guardian_id: str = Field(..., description="Identifier of the consenting guardian")
    guardian_name: str = Field(..., description="Full legal name of the guardian")
    relationship: GuardianRelationship = Field(..., description="Legal relationship to minor")
    is_verified: bool = Field(default=False, description="Server-computed verification status (client input ignored)")
    verification_method: Optional[str] = Field(default=None, description="e.g. 'aadhaar_otp', 'physical_id'")


class ConsentStatus(str, Enum):
    ACTIVE = "active"
    WITHDRAWN = "withdrawn"
    PARTIALLY_WITHDRAWN = "partially_withdrawn"


class ConsentRecordDTO(BaseModel):
    """Versioned immutable consent record representation."""
    id: str
    patient_id: str
    encounter_id: str
    purposes: Dict[str, bool]
    language: str
    notice_version: str
    granted_at: datetime
    withdrawn_at: Optional[datetime] = None
    abdm_artefact_id: Optional[str] = None
    chain_hash: Optional[str] = None
    version: int = 1
    status: ConsentStatus = ConsentStatus.ACTIVE
    is_offline: bool = False
    guardian_id: Optional[str] = None


class ConsentGrantRequest(BaseModel):
    """API payload for granting or updating consent."""
    patient_id: str
    encounter_id: str
    purposes: Purposes
    language: str = Field(default="hi", description="Language of notice presented")
    notice_version: str = Field(default="dpdp-v1.0", description="Version of presented DPDP notice")
    is_minor: bool = Field(default=False, description="Set True if patient is under 18 years old")
    guardian_context: Optional[GuardianContext] = None


class ConsentWithdrawRequest(BaseModel):
    """API payload for withdrawing consent."""
    encounter_id: str
    purposes_to_withdraw: List[str] = Field(
        ...,
        description="List of specific purposes to withdraw, or ['all'] to withdraw all",
        examples=[["research"], ["abdm", "qi"], ["all"]]
    )
    reason: Optional[str] = Field(default=None, description="Optional withdrawal rationale")


class ErasureRequest(BaseModel):
    """API payload for requesting erasure under DPDP."""
    patient_id: str
    encounter_id: Optional[str] = None
    reason: str = Field(default="patient_right_to_erasure", description="Erasure request reason")


class ErasureStatus(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    PROPAGATED = "propagated"


class ErasureResponse(BaseModel):
    """Response returned upon submitting an erasure request."""
    request_id: str
    patient_id: str
    encounter_id: Optional[str] = None
    status: ErasureStatus
    requested_at: datetime
    propagated_at: Optional[datetime] = None


class ABDMArtifactStatus(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    FAILED = "FAILED"


class ABDMStatusResponse(BaseModel):
    """Response model for checking ABDM consent artefact status."""
    encounter_id: str
    status: ABDMArtifactStatus
    artefact_id: Optional[str] = None
    is_external_sharing_permitted: bool = False
    last_updated: datetime


class OfflineConsentPayload(BaseModel):
    """Payload for capturing offline consent on station."""
    patient_id: str
    encounter_id: str
    purposes: Purposes
    language: str = "hi"
    notice_version: str = "dpdp-v1.0"
    device_id: str
    captured_at: datetime = Field(default_factory=utc_now)
    is_minor: bool = False
    guardian_context: Optional[GuardianContext] = None


class OfflineSyncResponse(BaseModel):
    """Response returned when syncing offline consent logs to server."""
    synced_count: int
    pending_abdm_requests: int
    chain_verified: bool
    status: str
