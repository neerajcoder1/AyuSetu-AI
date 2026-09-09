"""
Consent & DPDP REST API Routes
===============================
Authoritative routes for DPDP consent lifecycle per PRD v2.0 §21.7 & §22.5.
Integrates with M3 RBAC/ABAC authorization boundaries and ErrorCode taxonomy.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from ayusetu.gateway.auth.models import Principal, Role
from ayusetu.gateway.auth.dependencies import get_current_principal
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.consent.models import (
    ConsentGrantRequest,
    ConsentWithdrawRequest,
    ConsentRecordDTO,
    ErasureRequest,
    ErasureResponse,
    OfflineConsentPayload,
    OfflineSyncResponse,
    ABDMStatusResponse,
)
from ayusetu.consent.service import consent_service
from ayusetu.consent.abdm_adapter import abdm_manager

router = APIRouter(tags=["consent"])


def _enforce_encounter_authorization(principal: Optional[Principal], encounter_id: str, action_description: str = "access") -> None:
    """Helper enforcing M3 RBAC/ABAC encounter boundary on consent operations."""
    if not principal or not principal.is_authenticated:
        return

    # Patient and Companion can only access their assigned encounter
    if principal.role in (Role.PATIENT, Role.COMPANION):
        if principal.encounter_id and str(principal.encounter_id) != str(encounter_id):
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Cross-encounter {action_description} denied: caller is not assigned to encounter {encounter_id}",
                403
            )

    # Physician and Nurse can only access encounters in their assigned list
    if principal.role in (Role.PHYSICIAN, Role.NURSE):
        if str(encounter_id) not in principal.assigned_encounter_ids:
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Encounter authorization denied: staff {principal.actor_id} is not assigned to encounter {encounter_id}",
                403
            )


@router.post("/consent", response_model=ConsentRecordDTO, status_code=status.HTTP_201_CREATED)
def grant_consent(
    payload: ConsentGrantRequest,
    principal: Optional[Principal] = Depends(get_current_principal),
    x_device_fingerprint: Optional[str] = Header(None),
):
    """
    Grant or update DPDP consent for an encounter.
    Creates an immutable, versioned consent record.
    """
    if principal and principal.is_authenticated:
        # Patient cannot grant consent for a mismatching patient ID
        if principal.role == Role.PATIENT:
            if principal.patient_id and str(principal.patient_id) != str(payload.patient_id):
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    "Patient cannot grant consent for another patient",
                    403
                )
            if principal.encounter_id and str(principal.encounter_id) != str(payload.encounter_id):
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    "Patient cannot grant consent for another encounter",
                    403
                )

        _enforce_encounter_authorization(principal, payload.encounter_id, "grant consent")

    return consent_service.grant_consent(
        request=payload,
        principal=principal,
        is_offline=False,
        device_id=x_device_fingerprint,
    )


@router.get("/consent/{encounter_id}", response_model=ConsentRecordDTO, status_code=status.HTTP_200_OK)
def get_encounter_consent(
    encounter_id: str,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Retrieve current active consent record for an encounter.
    """
    _enforce_encounter_authorization(principal, encounter_id, "consent retrieval")

    record = consent_service.get_active_consent(encounter_id)
    if not record:
        raise AyuSetuGatewayError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f"Consent record not found for encounter {encounter_id}",
            404
        )

    return record


@router.get("/consent/{encounter_id}/history", response_model=List[ConsentRecordDTO], status_code=status.HTTP_200_OK)
def get_consent_history(
    encounter_id: str,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Retrieve full immutable version audit trail of consent records for an encounter.
    """
    _enforce_encounter_authorization(principal, encounter_id, "consent history retrieval")

    history = consent_service.get_consent_history(encounter_id)
    if not history:
        raise AyuSetuGatewayError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f"Consent history not found for encounter {encounter_id}",
            404
        )

    return history


@router.post("/consent/withdraw", response_model=ConsentRecordDTO, status_code=status.HTTP_200_OK)
def withdraw_consent(
    payload: ConsentWithdrawRequest,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Withdraw specific or all consent purposes.
    Creates a new immutable versioned record while retaining historical proof.
    """
    if principal and principal.is_authenticated:
        if principal.role == Role.COMPANION:
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Companion role cannot withdraw patient consent",
                403
            )
        _enforce_encounter_authorization(principal, payload.encounter_id, "consent withdrawal")

    return consent_service.withdraw_consent(
        request=payload,
        principal=principal,
    )


@router.post("/consent/{consent_id}/withdraw", response_model=ConsentRecordDTO, status_code=status.HTTP_200_OK)
def withdraw_consent_by_id(
    consent_id: str,
    payload: ConsentWithdrawRequest,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Withdraw consent by consent ID endpoint alias.
    """
    if principal and principal.is_authenticated:
        if principal.role == Role.COMPANION:
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Companion role cannot withdraw patient consent",
                403
            )
        _enforce_encounter_authorization(principal, payload.encounter_id, "consent withdrawal")

    return consent_service.withdraw_consent(
        request=payload,
        principal=principal,
    )


@router.post("/erasure", response_model=ErasureResponse, status_code=status.HTTP_202_ACCEPTED)
def request_erasure(
    payload: ErasureRequest,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Submit DPDP Right to Erasure request. Idempotent and emits propagation event.
    """
    if principal and principal.is_authenticated:
        if principal.role == Role.PATIENT:
            if principal.patient_id and str(principal.patient_id) != str(payload.patient_id):
                raise AyuSetuGatewayError(
                    ErrorCode.POLICY_DENIED,
                    "Cannot request erasure for another patient's records",
                    403
                )
        elif principal.role == Role.COMPANION:
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Companion role cannot request erasure of patient records",
                403
            )
        elif principal.role in (Role.PHYSICIAN, Role.NURSE) and payload.encounter_id:
            _enforce_encounter_authorization(principal, payload.encounter_id, "erasure request")

    return consent_service.request_erasure(
        request=payload,
        principal=principal,
    )


@router.get("/erasure/{request_id}", response_model=ErasureResponse, status_code=status.HTTP_200_OK)
def get_erasure_status(
    request_id: str,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Query status of a submitted erasure request.
    """
    res = consent_service.get_erasure_status(request_id)
    if not res:
        raise AyuSetuGatewayError(
            ErrorCode.RESOURCE_NOT_FOUND,
            f"Erasure request {request_id} not found",
            404
        )

    if principal and principal.is_authenticated and principal.role == Role.PATIENT:
        if principal.patient_id and str(principal.patient_id) != str(res.patient_id):
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Cannot view another patient's erasure request",
                403
            )

    return res


@router.post("/consent/offline", response_model=ConsentRecordDTO, status_code=status.HTTP_201_CREATED)
def record_offline_consent(
    payload: OfflineConsentPayload,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Record offline DPDP consent with local cryptographic hash chain integrity.
    Valid immediately for hospital clinical intake; does NOT create ABDM artefact.
    """
    return consent_service.capture_offline_consent(
        payload=payload,
        principal=principal,
    )


@router.post("/consent/sync", response_model=OfflineSyncResponse, status_code=status.HTTP_200_OK)
def sync_offline_consent(
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Synchronize offline consent hash chain to cloud and queue pending ABDM requests.
    """
    return consent_service.sync_offline_consent()


@router.get("/abdm/{encounter_id}/status", response_model=ABDMStatusResponse, status_code=status.HTTP_200_OK)
def get_abdm_status(
    encounter_id: str,
    principal: Optional[Principal] = Depends(get_current_principal),
):
    """
    Query ABDM Consent Artefact status and external data sharing authorization.
    """
    _enforce_encounter_authorization(principal, encounter_id, "ABDM status check")
    return abdm_manager.get_status(encounter_id)
