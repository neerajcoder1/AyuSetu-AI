"""
AyuSetu Consent & DPDP Module
=============================
Authoritative Consent and DPDP package implementing 4-purpose consent,
versioning, gating, offline hash chaining, erasure, and ABDM lifecycle.
"""

from ayusetu.consent.models import (
    Purposes,
    GuardianContext,
    GuardianRelationship,
    ConsentRecordDTO,
    ConsentStatus,
    ConsentGrantRequest,
    ConsentWithdrawRequest,
    ErasureRequest,
    ErasureResponse,
    OfflineConsentPayload,
    OfflineSyncResponse,
    ABDMArtifactStatus,
    ABDMStatusResponse,
)
from ayusetu.consent.service import ConsentService, consent_service
from ayusetu.consent.offline_chain import ConsentHashChain, station_consent_chain
from ayusetu.consent.policy import require_clinical_consent, require_purpose_consent
from ayusetu.consent.abdm_adapter import ABDMConsentManagerAdapter, abdm_manager
