"""
Consent Gating & Authorization Policy Dependencies
===================================================
Reusable FastAPI dependencies enforcing consent prerequisites per PRD v2.0 §21.7.

Clinical capture MUST NOT begin without valid clinical-intake consent.
Refusing optional purposes (ABDM, QI, research) must NEVER block clinical service.
"""

from typing import Callable, Optional
from fastapi import Header, HTTPException, Path, Request, status

from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.consent.service import consent_service


def require_clinical_consent(
    request: Request,
) -> str:
    """
    FastAPI dependency enforcing that active, non-withdrawn clinical consent
    exists for the encounter.
    
    Raises 403 CONSENT_REQUIRED if missing or withdrawn.
    """
    enc_id = (
        request.path_params.get("id")
        or request.path_params.get("encounter_id")
        or request.headers.get("x-encounter-id")
        or request.query_params.get("encounter_id")
    )
    if not enc_id:
        raise AyuSetuGatewayError(
            ErrorCode.BAD_REQUEST,
            "Encounter ID is required for consent verification",
            400
        )

    has_consent = consent_service.check_clinical_consent(enc_id)
    if not has_consent:
        raise AyuSetuGatewayError(
            ErrorCode.CONSENT_REQUIRED,
            f"Clinical processing consent is required to proceed with encounter {enc_id}",
            403
        )

    return enc_id


def require_purpose_consent(purpose: str) -> Callable:
    """
    Factory creating FastAPI dependencies that gate specific purpose access.
    e.g. require_purpose_consent('research') or require_purpose_consent('qi')
    """
    def _dependency(request: Request) -> str:
        enc_id = (
            request.path_params.get("id")
            or request.path_params.get("encounter_id")
            or request.headers.get("x-encounter-id")
            or request.query_params.get("encounter_id")
        )
        if not enc_id:
            raise AyuSetuGatewayError(
                ErrorCode.BAD_REQUEST,
                "Encounter ID is required for purpose consent verification",
                400
            )

        if not consent_service.check_purpose_consent(enc_id, purpose):
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Consent for purpose '{purpose}' has not been granted for encounter {enc_id}",
                403
            )
        return enc_id

    return _dependency

