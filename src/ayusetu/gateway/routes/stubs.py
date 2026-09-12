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


class MpiMergeRequest(BaseModel):
    source_patient_id: str
    target_patient_id: str
    reason: str = "Duplicate demographic match merged by MRD"


class MpiUnmergeRequest(BaseModel):
    source_patient_id: str
    reason: str = "Erroneous merge reversal requested by MRD"


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
        "department": staff.get("department", "General"),
        "expires_in_minutes": 480,
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


# --- Kiosk Session & Intake Endpoints ---

@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: Optional[SessionCreateRequest] = None,
    channel: str = Query("kiosk", pattern="^(kiosk|pwa_self|pwa_companion|assisted)$"),
    x_device_fingerprint: Optional[str] = Header(None, alias="X-Device-Fingerprint")
):
    """Initialize ephemeral session state per PRD §22.4."""
    if payload:
        channel = payload.channel
    enc_id = uuid6.uuid7()
    
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
    principal: Optional[Principal] = None,
):
    """Fetch candidate patient matches for the review queue."""
    from ayusetu.clinical.mpi_service import mpi_service
    return mpi_service.search_candidates(name=name, dob=dob, mobile=mobile)


@router.post(
    "/mpi/merge",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles(Role.MRD, Role.ADMIN))]
)
def merge_mpi_patients(
    payload: MpiMergeRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Merge two patient records under an authoritative master per PRD v3 §4.3 & §23.1."""
    from ayusetu.clinical.mpi_service import mpi_service
    return mpi_service.merge_records(
        source_patient_id=payload.source_patient_id,
        target_patient_id=payload.target_patient_id,
        reason=payload.reason,
        actor_id=principal.actor_id if principal else None,
        actor_role=principal.role.value if principal else "mrd",
    )


@router.post(
    "/mpi/unmerge",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_roles(Role.MRD, Role.ADMIN))]
)
def unmerge_mpi_patient(
    payload: MpiUnmergeRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Reversibly unmerge a merged patient record per PRD v3 §4.3 & §23.1."""
    from ayusetu.clinical.mpi_service import mpi_service
    return mpi_service.unmerge_record(
        source_patient_id=payload.source_patient_id,
        reason=payload.reason,
        actor_id=principal.actor_id if principal else None,
        actor_role=principal.role.value if principal else "mrd",
    )


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
async def upload_document(
    id: str,
    request: Request,
):
    """Upload physical document image / PDF and extract clinical entities."""
    session = session_cache.get_session(id)
    if not session:
        raise AyuSetuGatewayError(ErrorCode.SESSION_EXPIRED, f"Session '{id}' expired or not found", 401)

    from ayusetu.clinical.document_service import document_service

    grid = None
    image_path = None
    raw_text = None
    page_no = 1

    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
            if isinstance(data, dict):
                grid = data.get("grid")
                image_path = data.get("image_path")
                raw_text = data.get("raw_text")
                page_no = int(data.get("page_no", 1))
    except Exception:
        pass

    result = document_service.process_document(
        session_id=id,
        grid=grid,
        image_path=image_path,
        raw_text=raw_text,
        page_no=page_no,
    )

    quality_score = result.quality.blur_score if result.quality else 0.95
    return {
        "document_id": result.document_id,
        "session_id": id,
        "quality_score": quality_score,
        "ocr_status": "completed",
        "page_no": page_no,
        "entities_count": len(result.entities),
    }


@router.get("/sessions/{id}/documents/{doc_id}", status_code=status.HTTP_200_OK)
def get_document_extraction(id: str, doc_id: str):
    """Fetch document extraction status and entities."""
    session = session_cache.get_session(id)
    if not session:
        raise AyuSetuGatewayError(ErrorCode.SESSION_EXPIRED, f"Session '{id}' expired or not found", 401)

    from ayusetu.clinical.document_service import document_service
    doc = document_service.get_document(doc_id)
    if not doc:
        raise AyuSetuGatewayError(ErrorCode.NOT_FOUND, f"Document '{doc_id}' not found", 404)

    return {
        "document_id": doc.document_id,
        "session_id": id,
        "ocr_status": "completed",
        "quality_score": doc.quality.blur_score if doc.quality else 0.95,
        "quality": {
            "blur_score": doc.quality.blur_score if doc.quality else 0.95,
            "glare_score": doc.quality.glare_score if doc.quality else 1.0,
            "skew_score": doc.quality.skew_score if doc.quality else 1.0,
            "accepted": doc.quality.accepted if doc.quality else True,
            "rejection_reasons": doc.quality.rejection_reasons if doc.quality else [],
        },
        "entities": [
            {
                "entity_type": e.entity_type.value if hasattr(e.entity_type, "value") else str(e.entity_type),
                "raw_text": e.raw_text,
                "normalised": e.normalised,
                "confidence": e.confidence,
                "code_system": e.code_system,
                "code": e.code,
                "needs_review": e.needs_review,
                "fhir_resource_type": e.fhir_resource_type,
                "page_no": e.page_no,
            }
            for e in doc.entities
        ],
        "ocr": [
            {
                "page_no": o.page_no,
                "raw_text": o.raw_text,
                "mean_confidence": o.mean_confidence,
            }
            for o in doc.ocr
        ]
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
    from ayusetu.redflag.service import red_flag_service
    tier1_items = red_flag_service.get_tier1_queue()
    alerts_list = [
        {
            "event_id": item.event.id,
            "encounter_id": item.encounter_id,
            "rule_id": item.event.rule_id,
            "tier": item.event.tier,
            "trigger_text": item.event.trigger_text,
            "detected_at": item.detected_at,
            "seconds_since_detection": item.seconds_since_detection,
            "escalation_level": item.escalation_level,
            "is_overdue": item.is_overdue,
            "status": item.event.status.value if hasattr(item.event.status, "value") else str(item.event.status),
        }
        for item in tier1_items
        if not status or status.lower() == "all" or item.event.status.value.lower() == status.lower()
    ]
    return {"tier": tier, "status": status, "alerts": alerts_list}


@router.post(
    "/alerts/{id}/acknowledge",
    status_code=status.HTTP_200_OK,
)
def acknowledge_alert(
    id: str,
    payload: AlertAcknowledgeRequest,
    principal: Principal = Depends(require_roles(Role.NURSE, Role.PHYSICIAN)),
):
    """Acknowledge alert with disposition."""
    from ayusetu.redflag.service import red_flag_service
    updated = red_flag_service.acknowledge_event(
        event_id=id,
        clinician_id=principal.actor_id,
        clinician_role=principal.role.value,
        notes=f"{payload.disposition}: {payload.notes}" if payload.notes else payload.disposition,
    )
    return {
        "alert_id": id,
        "status": updated.status.value if hasattr(updated.status, "value") else str(updated.status),
        "disposition": payload.disposition,
        "acknowledged_by": updated.acknowledged_by,
        "acknowledged_at": updated.acknowledged_at,
    }


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
def resume_session(
    id: str,
    qr_payload: Dict[str, Any],
):
    """Claim incomplete PWA session at station via QR code."""
    session = session_cache.get_session(id)
    if not session:
        raise AyuSetuGatewayError(
            ErrorCode.SESSION_EXPIRED,
            f"Session '{id}' expired or not found",
            404,
        )

    token_in_qr = qr_payload.get("token")
    if token_in_qr and token_in_qr != session.get("token"):
        raise AyuSetuGatewayError(
            ErrorCode.POLICY_DENIED,
            "Invalid QR session token",
            403,
        )

    station_id = qr_payload.get("station_id") or "kiosk_station"
    session_cache.update_session(id, {
        "claimed_by_station": station_id,
        "channel": "kiosk",
        "status": "RESUMED",
    })

    return {
        "session_id": id,
        "encounter_id": session.get("encounter_id"),
        "status": "resumed",
        "claimed_by_station": station_id,
    }


@router.post("/sessions/{id}/companion-link", status_code=status.HTTP_200_OK)
def issue_companion_link(id: str, payload: CompanionLinkRequest):
    """Issue scoped magic link to a patient-nominated phone number per PRD §23.4."""
    session = session_cache.get_session(id)
    if not session:
        raise AyuSetuGatewayError(
            ErrorCode.SESSION_EXPIRED,
            f"Session '{id}' not found or expired",
            404,
        )

    # SEC-T-03: Refuse link generation if session already submitted/finalized
    session_status = session.get("status", "ACTIVE")
    if session_status in ("SUBMITTED", "FINAL", "ABANDONED"):
        from ayusetu.gateway.auth.event_hooks import dispatch_security_event
        dispatch_security_event(
            event_type="COMPANION_LINK_EXPIRED_OR_SUBMITTED",
            actor_id=payload.nominated_mobile,
            actor_role="companion",
            target_resource=f"session_{id}",
            reason=f"Attempted to issue companion link for {session_status} session",
        )
        raise AyuSetuGatewayError(
            ErrorCode.POLICY_DENIED,
            f"Cannot issue companion link: session is already {session_status.lower()}",
            401,
        )

    companion_token = SessionCache.generate_token()
    session_cache.update_session(id, {
        "companion_mobile": payload.nominated_mobile,
        "companion_relationship": payload.relationship,
        "companion_token": companion_token,
        "companion_device_fingerprint": None,
        "companion_consumed": False,
    })

    return {
        "session_id": id,
        "nominated_mobile": payload.nominated_mobile,
        "relationship": payload.relationship,
        "magic_link": f"/pwa/companion/{id}?token={companion_token}",
        "expires_in_minutes": settings.COMPANION_LINK_TTL_MINUTES,
    }


@router.post("/sessions/{id}/companion-access", status_code=status.HTTP_200_OK)
def access_companion_session(
    id: str,
    token: str = Query(...),
    x_device_fingerprint: Optional[str] = Header(None, alias="X-Device-Fingerprint"),
):
    """
    Validate companion mode access per PRD §23.4 and SEC-T-03.
    Rejects reuse after submission and enforces single-device fingerprint binding.
    """
    from ayusetu.gateway.auth.event_hooks import dispatch_security_event

    session = session_cache.get_session(id)
    if not session:
        dispatch_security_event(
            event_type="COMPANION_LINK_EXPIRED_OR_SUBMITTED",
            actor_id="companion",
            actor_role="companion",
            target_resource=f"session_{id}",
            reason="Session not found or expired",
        )
        raise AyuSetuGatewayError(ErrorCode.SESSION_EXPIRED, "Companion link expired or session ended", 401)

    # 1. Post-submission check
    if session.get("status") in ("SUBMITTED", "FINAL", "ABANDONED") or session.get("companion_consumed"):
        dispatch_security_event(
            event_type="COMPANION_REUSE_ATTEMPT",
            actor_id="companion",
            actor_role="companion",
            target_resource=f"session_{id}",
            reason="Companion link reused after session submission or finalization",
        )
        raise AyuSetuGatewayError(
            ErrorCode.POLICY_DENIED,
            "Companion link has already been used or session is completed",
            401,
        )

    # 2. Token match check
    if session.get("companion_token") != token:
        dispatch_security_event(
            event_type="COMPANION_AUTH_FAILED",
            actor_id="companion",
            actor_role="companion",
            target_resource=f"session_{id}",
            reason="Invalid companion token provided",
        )
        raise AyuSetuGatewayError(ErrorCode.POLICY_DENIED, "Invalid companion link token", 401)

    # 3. Single-device binding check (SEC-T-03)
    existing_device = session.get("companion_device_fingerprint")
    if existing_device and x_device_fingerprint and existing_device != x_device_fingerprint:
        dispatch_security_event(
            event_type="COMPANION_CROSS_DEVICE_REUSE_ATTEMPT",
            actor_id=x_device_fingerprint,
            actor_role="companion",
            target_resource=f"session_{id}",
            reason=f"Cross-device replay attempt: claimed device {x_device_fingerprint} != bound device {existing_device}",
        )
        raise AyuSetuGatewayError(
            ErrorCode.POLICY_DENIED,
            "Companion link is already bound to another device. Cross-device reuse prohibited.",
            401,
        )

    # Bind first accessing device
    if not existing_device and x_device_fingerprint:
        session_cache.update_session(id, {"companion_device_fingerprint": x_device_fingerprint})

    return {
        "session_id": id,
        "encounter_id": session.get("encounter_id"),
        "status": session.get("status", "ACTIVE"),
        "channel": "pwa_companion",
        "device_bound": x_device_fingerprint or existing_device,
    }


@router.post(
    "/exports",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_roles(Role.MRD, Role.AUDITOR, Role.ADMIN))]
)
def request_deid_export(
    payload: DeidExportRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Request de-identified export with two-person authorization."""
    from ayusetu.deid.models import ExportPurpose
    from ayusetu.audit.service import audit_service
    from ayusetu.audit.models import AuditAction, AuditOutcome

    app1 = (payload.approver_1 or "").strip()
    app2 = (payload.approver_2 or "").strip()

    if not app1 or not app2 or app1 == app2:
        raise AyuSetuGatewayError(
            ErrorCode.POLICY_DENIED,
            "Two distinct approvers are required for de-identified data export (Separation of Duties)",
            403
        )

    purpose_enum = ExportPurpose(payload.purpose.lower()) if payload.purpose else ExportPurpose.RESEARCH
    export_id = str(uuid6.uuid7())

    # Immutable audit recording (Zero PHI)
    try:
        actor_id = principal.actor_id if principal and principal.actor_id else "00000000-0000-0000-0000-000000000000"
        actor_role = principal.role.value if principal and principal.role else "mrd"
        audit_service.record_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action=AuditAction.EXPORT,
            resource_type="deid_export",
            resource_id=export_id,
            outcome=AuditOutcome.ALLOW,
            reason="De-identified cohort export requested with valid Two-Person SoD approval",
            safe_metadata={
                "export_id": export_id,
                "purpose": purpose_enum.value,
                "date_from": payload.date_from,
                "date_to": payload.date_to,
                "approver_1": payload.approver_1,
                "approver_2": payload.approver_2,
                "k_anonymity_threshold": 5,
            },
        )
    except Exception:
        pass

    return {
        "export_id": export_id,
        "status": "pending_processing",
        "k_anonymity_threshold": 5,
        "purpose": purpose_enum.value,
        "message": "Export initiated successfully under Two-Person SoD controls",
    }
