"""
De-Identification REST API Endpoints
====================================
Mounts de-identification and secure cohort export endpoints under /api/v1/deid.
Enforces Role.MRD / Role.AUDITOR RBAC and PRD §21.4 Two-Person Authorization.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode
from ayusetu.deid.models import DeidExportRequest, DeidExportResponse
from ayusetu.deid.service import deid_export_service
from ayusetu.gateway.auth.models import Principal, Role
from ayusetu.gateway.auth.dependencies import require_roles, get_current_principal

router = APIRouter(prefix="/deid", tags=["De-Identification & Export"])


class DirectCohortExportRequest(BaseModel):
    export_request: DeidExportRequest
    candidate_records: List[Dict[str, Any]] = Field(default_factory=list)


@router.post(
    "/export",
    response_model=DeidExportResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles(Role.MRD, Role.AUDITOR, Role.ADMIN))]
)
def export_deidentified_cohort(
    payload: DirectCohortExportRequest,
    principal: Principal = Depends(get_current_principal),
) -> DeidExportResponse:
    """
    Executes a complete PRD §21.9 compliant de-identified dataset export
    with strict k-anonymity (k >= 5), Zero-PHI safety gate, and immutable audit logging.
    """
    return deid_export_service.export_cohort(
        request=payload.export_request,
        principal=principal,
        candidate_records=payload.candidate_records,
    )
