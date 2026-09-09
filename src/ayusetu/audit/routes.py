"""
Audit Service REST API Routes
==============================
Authoritative routes for audit log inspection, integrity verification,
offline station synchronization, and quarantine review per PRD v2.0 §21.8 & §22.8.
Protected strictly by M3 RBAC/ABAC authorization rules.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from ayusetu.gateway.auth.models import Principal, Role
from ayusetu.gateway.auth.dependencies import get_current_principal, require_roles
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.audit.models import (
    AuditEventDTO,
    AuditHeadDTO,
    AuditVerificationResult,
    OfflineAuditSyncBatch,
    OfflineAuditSyncResponse,
    QuarantineRecordDTO,
)
from ayusetu.audit.service import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/head", response_model=AuditHeadDTO, status_code=status.HTTP_200_OK)
def get_audit_head(
    principal: Principal = Depends(require_roles(Role.AUDITOR, Role.ADMIN)),
) -> AuditHeadDTO:
    """
    Retrieve current tip/head of the global cryptographic audit chain.
    Accessible ONLY to Auditor and Admin roles.
    """
    return audit_service.get_head()


@router.get("/verify", response_model=AuditVerificationResult, status_code=status.HTTP_200_OK)
def verify_audit_chain(
    principal: Principal = Depends(require_roles(Role.AUDITOR, Role.ADMIN)),
) -> AuditVerificationResult:
    """
    Perform on-demand end-to-end cryptographic verification of the global audit chain.
    Checks sequence continuity, canonical hashes, and hash-chain links.
    Accessible ONLY to Auditor and Admin roles.
    """
    return audit_service.verify_global_chain()


@router.get("/events", response_model=List[AuditEventDTO], status_code=status.HTTP_200_OK)
def list_audit_events(
    from_seq: int = Query(1, ge=1, description="Starting sequence number"),
    to_seq: Optional[int] = Query(None, ge=1, description="Ending sequence number"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    encounter_id: Optional[str] = Query(None, description="Filter by encounter UUID"),
    patient_id: Optional[str] = Query(None, description="Filter by patient UUID"),
    actor_id: Optional[str] = Query(None, description="Filter by actor UUID"),
    action: Optional[str] = Query(None, description="Filter by action verb"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    principal: Principal = Depends(require_roles(Role.AUDITOR, Role.ADMIN)),
) -> List[AuditEventDTO]:
    """
    Query immutable audit trail records with safe metadata filtering.
    Clinical staff, patients, and companions are strictly prohibited from querying audit logs.
    """
    return audit_service.query_events(
        from_seq=from_seq,
        to_seq=to_seq,
        limit=limit,
        encounter_id=encounter_id,
        patient_id=patient_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
    )


@router.post("/offline/sync", response_model=OfflineAuditSyncResponse, status_code=status.HTTP_200_OK)
def sync_offline_audit_batch(
    batch: OfflineAuditSyncBatch,
    principal: Optional[Principal] = Depends(get_current_principal),
) -> OfflineAuditSyncResponse:
    """
    Synchronize an offline station's cryptographic audit batch to the global server chain.
    Validates station internal hash continuity, linkage to known server heads, and device authorization.
    Cross-device impersonation attempts are rejected with 403.
    """
    if principal and principal.role in (Role.PATIENT, Role.COMPANION):
        raise AyuSetuGatewayError(
            ErrorCode.POLICY_DENIED,
            f"Role {principal.role.value} is not authorized to submit station audit logs",
            403,
        )

    trusted_device_id = principal.device_fingerprint if principal else None
    return audit_service.sync_offline_batch(batch, trusted_device_id=trusted_device_id)


@router.get("/quarantine", response_model=List[QuarantineRecordDTO], status_code=status.HTTP_200_OK)
def list_quarantined_batches(
    principal: Principal = Depends(require_roles(Role.AUDITOR, Role.ADMIN)),
) -> List[QuarantineRecordDTO]:
    """
    Review quarantined invalid or tampered offline audit batches.
    Accessible ONLY to Auditor and Admin roles.
    """
    return audit_service.get_quarantined_records()
