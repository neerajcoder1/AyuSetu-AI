"""
AyuSetu Audit Package
=====================
Append-only, cryptographic hash-chained audit logging service.
"""

from ayusetu.audit.models import (
    AuditAction,
    AuditOutcome,
    AuditEventCreate,
    AuditEventDTO,
    AuditHeadDTO,
    OfflineAuditEventDTO,
    OfflineAuditSyncBatch,
    OfflineAuditSyncResponse,
    AuditVerificationResult,
    QuarantineRecordDTO,
)
from ayusetu.audit.chain import (
    GENESIS_HASH,
    GENESIS_SEQ,
    canonical_json,
    compute_payload_hash,
    compute_entry_hash,
    compute_offline_entry_hash,
)
from ayusetu.audit.repository import AuditRepository
from ayusetu.audit.verifier import AuditVerifier, audit_verifier
from ayusetu.audit.offline_chain import OfflineStationAuditChain
from ayusetu.audit.quarantine import QuarantineStore, quarantine_store
from ayusetu.audit.service import AuditService, audit_service

__all__ = [
    "AuditAction",
    "AuditOutcome",
    "AuditEventCreate",
    "AuditEventDTO",
    "AuditHeadDTO",
    "OfflineAuditEventDTO",
    "OfflineAuditSyncBatch",
    "OfflineAuditSyncResponse",
    "AuditVerificationResult",
    "QuarantineRecordDTO",
    "GENESIS_HASH",
    "GENESIS_SEQ",
    "canonical_json",
    "compute_payload_hash",
    "compute_entry_hash",
    "compute_offline_entry_hash",
    "AuditRepository",
    "AuditVerifier",
    "audit_verifier",
    "OfflineStationAuditChain",
    "QuarantineStore",
    "quarantine_store",
    "AuditService",
    "audit_service",
]
