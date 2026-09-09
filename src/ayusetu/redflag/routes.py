"""
Red-Flag Engine REST API Routes
===============================
Authoritative endpoints for clinical red-flag evaluation, Tier 1 emergency queues,
and clinician alert acknowledgements/escalations per PRD v2.0 §12 & §22.9.
Enforces M3 RBAC/ABAC encounter scoping and M4 clinical consent gating.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from ayusetu.gateway.auth.models import Principal, Role
from ayusetu.gateway.auth.dependencies import get_current_principal, require_roles
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.redflag.models import (
    AcknowledgeRequest,
    EscalateRequest,
    RedFlagEvaluateRequest,
    RedFlagEventDTO,
    ResolveRequest,
    Tier1AlertQueueItem,
)
from ayusetu.redflag.service import red_flag_service

router = APIRouter(prefix="/redflag", tags=["redflag"])


def _enforce_encounter_access(principal: Optional[Principal], encounter_id: str, action: str = "access") -> None:
    """Helper enforcing M3 RBAC/ABAC encounter boundary on red-flag operations."""
    if not principal or not principal.is_authenticated:
        return

    # Patient and Companion can only access their assigned encounter
    if principal.role in (Role.PATIENT, Role.COMPANION):
        if principal.encounter_id and str(principal.encounter_id) != str(encounter_id):
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Cross-encounter {action} denied: caller is not assigned to encounter {encounter_id}",
                403,
            )

    # Physician and Nurse can only access encounters in their assigned list
    if principal.role in (Role.PHYSICIAN, Role.NURSE):
        if str(encounter_id) not in principal.assigned_encounter_ids:
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Encounter authorization denied: staff {principal.actor_id} is not assigned to encounter {encounter_id}",
                403,
            )


@router.post("/evaluate", response_model=List[RedFlagEventDTO], status_code=status.HTTP_200_OK)
def evaluate_red_flags(
    request: RedFlagEvaluateRequest,
    principal: Optional[Principal] = Depends(get_current_principal),
) -> List[RedFlagEventDTO]:
    """
    Evaluate structured clinical facts against declarative red-flag rules.
    Requires active clinical consent and valid encounter authorization.
    """
    _enforce_encounter_access(principal, request.encounter_id, "red-flag evaluation")
    actor_id = principal.actor_id if principal else None
    actor_role = principal.role.value if principal and principal.role else None

    return red_flag_service.evaluate_encounter(
        encounter_id=request.encounter_id,
        facts=request.facts,
        actor_id=actor_id,
        actor_role=actor_role,
    )


@router.get("/encounter/{encounter_id}", response_model=List[RedFlagEventDTO], status_code=status.HTTP_200_OK)
def get_encounter_red_flags(
    encounter_id: str,
    principal: Optional[Principal] = Depends(get_current_principal),
) -> List[RedFlagEventDTO]:
    """
    Retrieve all red-flag alerts associated with an encounter.
    """
    _enforce_encounter_access(principal, encounter_id, "red-flag query")
    return red_flag_service.get_encounter_events(encounter_id)


@router.get("/tier1-queue", response_model=List[Tier1AlertQueueItem], status_code=status.HTTP_200_OK)
def get_tier1_alert_queue(
    principal: Principal = Depends(require_roles(Role.ATTENDANT, Role.NURSE, Role.PHYSICIAN, Role.ADMIN, Role.AUDITOR)),
) -> List[Tier1AlertQueueItem]:
    """
    Retrieve active Tier-1 Emergency Alert Queue for triage nursing and physician cockpits.
    Patients and companions are strictly forbidden (403).
    """
    return red_flag_service.get_tier1_queue()


@router.post("/{event_id}/acknowledge", response_model=RedFlagEventDTO, status_code=status.HTTP_200_OK)
def acknowledge_alert(
    event_id: str,
    body: Optional[AcknowledgeRequest] = None,
    principal: Principal = Depends(require_roles(Role.NURSE, Role.PHYSICIAN)),
) -> RedFlagEventDTO:
    """
    Clinician acknowledgement of a red-flag alert.
    Requires Nurse or Physician role assigned to the encounter.
    """
    ev = red_flag_service.get_event_by_id(event_id)
    if not ev:
        raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Red-flag event {event_id} not found", 404)

    _enforce_encounter_access(principal, ev.encounter_id, "alert acknowledgement")
    notes = body.notes if body else None

    return red_flag_service.acknowledge_event(
        event_id=event_id,
        clinician_id=principal.actor_id,
        clinician_role=principal.role.value,
        notes=notes,
    )


@router.post("/{event_id}/escalate", response_model=RedFlagEventDTO, status_code=status.HTTP_200_OK)
def escalate_alert(
    event_id: str,
    body: Optional[EscalateRequest] = None,
    principal: Principal = Depends(require_roles(Role.NURSE, Role.PHYSICIAN)),
) -> RedFlagEventDTO:
    """
    Escalate an alert to emergency triage / senior DMO.
    Requires Nurse or Physician role assigned to the encounter.
    """
    ev = red_flag_service.get_event_by_id(event_id)
    if not ev:
        raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Red-flag event {event_id} not found", 404)

    _enforce_encounter_access(principal, ev.encounter_id, "alert escalation")
    target_role = body.target_role if body else "duty_medical_officer"
    notes = body.notes if body else None

    return red_flag_service.escalate_event(
        event_id=event_id,
        clinician_id=principal.actor_id,
        clinician_role=principal.role.value,
        target_role=target_role,
        notes=notes,
    )


@router.post("/{event_id}/resolve", response_model=RedFlagEventDTO, status_code=status.HTTP_200_OK)
def resolve_alert(
    event_id: str,
    body: ResolveRequest,
    principal: Principal = Depends(require_roles(Role.NURSE, Role.PHYSICIAN)),
) -> RedFlagEventDTO:
    """
    Resolve a red-flag alert with documented outcome and clinical notes.
    Requires Nurse or Physician role assigned to the encounter.
    """
    ev = red_flag_service.get_event_by_id(event_id)
    if not ev:
        raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Red-flag event {event_id} not found", 404)

    _enforce_encounter_access(principal, ev.encounter_id, "alert resolution")

    return red_flag_service.resolve_event(
        event_id=event_id,
        clinician_id=principal.actor_id,
        clinician_role=principal.role.value,
        outcome=body.outcome,
        notes=body.notes,
    )
