"""
API Gateway v1 REST Endpoints & Routing Stubs
=============================================
Authoritative routes per PRD v2.0 §22.5 with integrated RBAC/ABAC authorization.
"""

from typing import Any, Dict, List, Optional
import uuid
import uuid6
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from ayusetu.common.config import settings
from ayusetu.common.session_cache import SessionCache
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.gateway.auth.models import Principal, Role, Resource, Action, BreakGlassContext
from ayusetu.gateway.auth.session_auth import SessionAuthenticator, STAFF_DIRECTORY
from ayusetu.gateway.auth.dependencies import (
    get_current_principal,
    require_roles,
    require_permission,
)

router = APIRouter()
session_cache = SessionCache()
authenticator = SessionAuthenticator()


# --- Request / Response Models ---
class SessionCreateRequest(BaseModel):
    channel: str = Field(default="kiosk", pattern="^(kiosk|pwa_self|pwa_companion|assisted)$")
    department: str = Field(default="Kayachikitsa")
    visit_type: str = Field(default="new", pattern="^(new|followup_stable|followup_new|walkin)$")
    intake_depth: str = Field(default="full", pattern="^(fast|interval|delta|full)$")


class SessionCreateResponse(BaseModel):
    session_id: str
    encounter_id: str
    token: str
    ttl_seconds: int


class IdentifyRequest(BaseModel):
    auth_type: str = Field(..., pattern="^(abha|otp|provisional)$")
    identifier: Optional[str] = None
    mobile: Optional[str] = None
    name: Optional[str] = None


class ConsentRequest(BaseModel):
    purposes: Dict[str, bool] = Field(
        ...,
        json_schema_extra={"example": {"clinical": True, "abdm": True, "qi": False, "research": False}}
    )
    language: str = Field(default="hi")
    notice_version: str = Field(default="dpdp-v1.0")


class SubmitSessionRequest(BaseModel):
    confirmed_by: str = Field(..., pattern="^(patient|companion|attendant|clinician)$")
    readback_accepted: bool = True


class SummaryEditRequest(BaseModel):
    slot_path: str
    old_value: Optional[Any] = None
    new_value: Any
    reason: Optional[str] = None


class SignEncounterRequest(BaseModel):
    physician_id: str
    pin_or_token: Optional[str] = None


class AlertAcknowledgeRequest(BaseModel):
    disposition: str
    notes: Optional[str] = None


class CompanionLinkRequest(BaseModel):
    nominated_mobile: str = Field(..., min_length=10, max_length=15)
    relationship: Optional[str] = None


class DeidExportRequest(BaseModel):
    date_from: str
    date_to: str
    purpose: str = "research"
    approver_1: str
    approver_2: str


class LoginRequest(BaseModel):
    username: str
    password: Optional[str] = None


# --- Authentication & Introspection Endpoints ---

@router.post("/auth/token", status_code=status.HTTP_200_OK)
def login_for_access_token(payload: LoginRequest):
    """Staff SSO/OIDC login endpoint for role authentication."""
    staff = STAFF_DIRECTORY.get(payload.username)
    if not staff:
        raise AyuSetuGatewayError(
            ErrorCode.POLICY_DENIED,
            "Invalid staff username or credentials",
            401
        )

    token = f"staff-token-{payload.username}"
    return {
        "access_token": token,
        "token_type": "bearer",
        "actor_id": staff["actor_id"],
        "role": staff["role"].value,
        "department": staff["department"],
        "expires_in_minutes": 480  # 8 hour shift
    }


@router.get("/auth/me", status_code=status.HTTP_200_OK)
def get_current_user_profile(principal: Principal = Depends(get_current_principal)):
    """Introspect authenticated caller Principal."""
    return {
        "actor_id": principal.actor_id,
        "role": principal.role.value,
        "department": principal.department,
        "encounter_id": principal.encounter_id,
        "is_authenticated": principal.is_authenticated,
    }


@router.post("/auth/logout", status_code=status.HTTP_200_OK)
def logout(
    request: Request,
    principal: Principal = Depends(get_current_principal)
):
    """Revoke active session token."""
    if principal.session_token:
        authenticator.logout_session(principal.session_token)
    elif principal.encounter_id:
        session_cache.panic_clear(principal.encounter_id)
    return {"status": "logged_out", "actor_id": principal.actor_id}


# --- Endpoints per PRD §22.5 ---

@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: Optional[SessionCreateRequest] = None,
    x_device_fingerprint: Optional[str] = Header(None)
):
    """Create an encounter session and return session token and encounter ID."""
    enc_id = uuid6.uuid7()
    channel = payload.channel if payload else "kiosk"
    
    sess_data = session_cache.create_session(
        encounter_id=enc_id,
        channel=channel,
        device_fingerprint=x_device_fingerprint
    )
    return SessionCreateResponse(
        session_id=sess_data["session_id"],
        encounter_id=sess_data["encounter_id"],
        token=sess_data["token"],
        ttl_seconds=sess_data["ttl_seconds"]
    )


@router.post("/sessions/{id}/identify", status_code=status.HTTP_200_OK)
def identify_patient(id: str, payload: IdentifyRequest):
    """Identify patient via ABHA, OTP, or provisional identity."""
    session = session_cache.get_session(id)
    if not session:
        raise AyuSetuGatewayError(ErrorCode.SESSION_EXPIRED, "Session expired or not found", 401)
    
    session_cache.update_session(id, {"status": "CONSENT", "identity_type": payload.auth_type})
    return {
        "status": "matched",
        "patient_id": str(uuid6.uuid7()),
        "provisional": payload.auth_type == "provisional",
        "match_confidence": 1.0 if payload.auth_type != "provisional" else 0.5
    }


@router.get("/mpi/candidates", status_code=status.HTTP_200_OK)
def get_mpi_candidates(
    name: Optional[str] = None,
    dob: Optional[str] = None,
    mobile: Optional[str] = None,
    principal: Optional[Principal] = None
):
    """Fetch candidate patient matches for the review queue."""
    return {"candidates": [], "count": 0}


@router.post("/sessions/{id}/consent", status_code=status.HTTP_200_OK)
def record_consent(id: str, payload: ConsentRequest):
    """Record DPDP consent with hash chain generation."""
    session = session_cache.get_session(id)
    if not session:
        raise AyuSetuGatewayError(ErrorCode.SESSION_EXPIRED, "Session expired or not found", 401)

    # Clinical consent is mandatory to proceed to interview
    if not payload.purposes.get("clinical", False):
        raise AyuSetuGatewayError(
            ErrorCode.CONSENT_REQUIRED,
            "Clinical processing consent is required to proceed with intake",
            403
        )

    from ayusetu.consent.service import consent_service
    from ayusetu.consent.models import Purposes, ConsentGrantRequest

    enc_id = session.get("encounter_id") or id
    pat_id = session.get("patient_id") or str(uuid6.uuid7())

    purposes_obj = Purposes(
        clinical=payload.purposes.get("clinical", False),
        abdm=payload.purposes.get("abdm", False),
        qi=payload.purposes.get("qi", False),
        research=payload.purposes.get("research", False),
    )

    consent_record = consent_service.grant_consent(
        ConsentGrantRequest(
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=purposes_obj,
            language=payload.language,
            notice_version=payload.notice_version,
        )
    )

    session_cache.update_session(id, {"status": "INTERVIEW", "purposes": payload.purposes, "consent_id": consent_record.id})
    return {
        "status": "recorded",
        "consent_id": consent_record.id,
        "chain_hash": consent_record.chain_hash or "sha256_mock_chain_hash_entry"
    }



@router.post("/sessions/{id}/documents", status_code=status.HTTP_202_ACCEPTED)
def upload_document(id: str, request: Request):
    """Upload physical document image / PDF."""
    session = session_cache.get_session(id)
    if not session:
        raise AyuSetuGatewayError(ErrorCode.SESSION_EXPIRED, "Session expired or not found", 401)

    doc_id = str(uuid6.uuid7())
    return {
        "document_id": doc_id,
        "quality_score": 0.95,
        "ocr_status": "processing",
        "page_no": 1
    }


@router.get("/sessions/{id}/documents/{doc_id}", status_code=status.HTTP_200_OK)
def get_document_extraction(id: str, doc_id: str):
    """Fetch document extraction status and entities."""
    return {
        "document_id": doc_id,
        "ocr_status": "completed",
        "quality_score": 0.95,
        "entities": []
    }


@router.post("/sessions/{id}/submit", status_code=status.HTTP_202_ACCEPTED)
def submit_session(
    id: str,
    payload: SubmitSessionRequest,
    request: Request,
):
    """Seal session, persist Encounter/Slots to PostgreSQL, and purge session cache."""
    from ayusetu.clinical.service import clinical_service

    auth_header = request.headers.get("Authorization")
    actor_id = None
    actor_role = "patient"
    if auth_header:
        try:
            principal = authenticator.authenticate_token(auth_header)
            if principal and principal.is_authenticated:
                actor_id = principal.actor_id
                actor_role = principal.role.value
        except Exception:
            pass

    ip = request.client.host if request.client else None

    res = clinical_service.submit_session(
        session_id=id,
        confirmed_by=payload.confirmed_by,
        readback_accepted=payload.readback_accepted,
        actor_id=actor_id,
        actor_role=actor_role,
        ip_address=ip,
    )

    return {
        "encounter_id": res.encounter_id,
        "status": res.status,
        "summary_status": res.summary_status,
        "poll_after_ms": res.poll_after_ms,
        "session_purged": res.session_purged,
        "slots_persisted": res.slots_persisted,
        "utterances_persisted": res.utterances_persisted,
        "redflags_detected": res.redflags_detected,
    }


@router.post("/sessions/{id}/panic-clear", status_code=status.HTTP_200_OK)
def panic_clear_session(id: str):
    """Immediate station purge (<2s) per PRD §21.6."""
    cleared = session_cache.panic_clear(id)
    return {
        "status": "cleared",
        "session_id": id,
        "purged": cleared
    }


@router.get(
    "/encounters/{id}/summary",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(Resource.SIGNED_CLINICAL_RECORD, Action.READ))]
)
def get_encounter_summary(id: str):
    """Fetch physician-facing clinical summary with provenance citations."""
    from ayusetu.clinical.service import clinical_service
    return clinical_service.get_or_generate_summary(id)


@router.patch(
    "/encounters/{id}/summary",
    status_code=status.HTTP_200_OK,
)
def patch_encounter_summary(
    id: str,
    payload: SummaryEditRequest,
    principal: Principal = Depends(require_permission(Resource.SIGNED_CLINICAL_RECORD, Action.UPDATE)),
):
    """Apply physician edits and record diff in summary_edit."""
    from ayusetu.clinical.service import clinical_service
    return clinical_service.apply_physician_patch(
        encounter_id=id,
        slot_path=payload.slot_path,
        new_value=payload.new_value,
        old_value=payload.old_value,
        reason=payload.reason,
        physician_id=principal.actor_id,
        physician_role=principal.role.value,
    )


@router.post(
    "/encounters/{id}/sign",
    status_code=status.HTTP_200_OK,
)
def sign_encounter_summary(
    id: str,
    payload: SignEncounterRequest,
    request: Request,
    principal: Principal = Depends(require_permission(Resource.SIGNED_CLINICAL_RECORD, Action.SIGN)),
):
    """Sign summary: preliminary -> final."""
    from ayusetu.clinical.service import clinical_service
    physician_id = payload.physician_id or principal.actor_id
    client_ip = request.client.host if request.client else None
    return clinical_service.sign_summary(
        encounter_id=id,
        physician_id=physician_id,
        physician_role=principal.role.value,
        ip_address=client_ip,
    )


@router.get(
    "/encounters/{id}/fhir",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles(Role.PHYSICIAN, Role.MRD))]
)
def get_encounter_fhir(
    id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Retrieve FHIR R4 document bundle."""
    from ayusetu.clinical.fhir_engine import fhir_bundle_engine
    return fhir_bundle_engine.generate_bundle(
        encounter_id=id,
        actor_id=principal.actor_id if principal else None,
        actor_role=principal.role.value if principal else "physician",
    )


@router.get(
    "/alerts",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles(Role.ATTENDANT, Role.NURSE, Role.PHYSICIAN, Role.ADMIN, Role.AUDITOR))]
)
def get_alerts(tier: int = Query(1, ge=1, le=3), status: str = "open"):
    """Tier 1/2/3 alert queue for the Ops Console."""
    return {"tier": tier, "status": status, "alerts": []}


@router.post(
    "/alerts/{id}/acknowledge",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles(Role.NURSE, Role.PHYSICIAN))]
)
def acknowledge_alert(id: str, payload: AlertAcknowledgeRequest):
    """Acknowledge alert with disposition."""
    return {"alert_id": id, "status": "acknowledged", "disposition": payload.disposition}


@router.post("/terminology/$translate", status_code=status.HTTP_200_OK)
def translate_terminology(
    code: str,
    system: str = "NAMASTE",
    target_system: Optional[str] = None,
):
    """NAMASTE to ICD-11 TM2/MMS and LOINC dual-coding translation."""
    from ayusetu.clinical.terminology import terminology_service
    return terminology_service.translate(code=code, system=system, target_system=target_system)


@router.get("/terminology/interactions", status_code=status.HTTP_200_OK)
def check_interactions(drugs: List[str] = Query(...)):
    """Herb-drug and drug-drug interaction check."""
    from ayusetu.clinical.terminology import terminology_service
    return terminology_service.check_interactions(drugs=drugs)


@router.get(
    "/encounters/{id}/prior",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles(Role.PHYSICIAN, Role.NURSE, Role.MRD))]
)
def get_prior_records(
    id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Fetch prior records and longitudinal patient timeline."""
    from ayusetu.clinical.terminology import terminology_service
    return terminology_service.get_prior_records(
        encounter_id=id,
        actor_id=principal.actor_id if principal else None,
        actor_role=principal.role.value if principal else "physician",
    )


@router.post("/sessions/{id}/resume", status_code=status.HTTP_200_OK)
def resume_session(id: str, qr_payload: Dict[str, Any]):
    """Claim incomplete PWA session at station via QR code."""
    return {"session_id": id, "status": "resumed"}


@router.post("/sessions/{id}/companion-link", status_code=status.HTTP_200_OK)
def issue_companion_link(id: str, payload: CompanionLinkRequest):
    """Issue scoped magic link to a patient-nominated phone number."""
    return {
        "session_id": id,
        "nominated_mobile": payload.nominated_mobile,
        "magic_link": f"/pwa/companion/{id}?token={SessionCache.generate_token()}",
        "expires_in_minutes": settings.COMPANION_LINK_TTL_MINUTES
    }


@router.post(
    "/exports",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(Role.MRD, Role.AUDITOR))]
)
def request_deid_export(payload: DeidExportRequest):
    """Request de-identified export with two-person authorization."""
    if payload.approver_1 == payload.approver_2:
        raise AyuSetuGatewayError(
            ErrorCode.POLICY_DENIED,
            "Two distinct approvers are required for de-identified data export (Separation of Duties)",
            403
        )
    return {
        "export_id": str(uuid6.uuid7()),
        "status": "pending_processing",
        "k_anonymity_threshold": 5
    }
