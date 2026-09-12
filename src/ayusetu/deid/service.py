"""
De-Identification Export Service & Two-Person Coordinator
=========================================================
Implements PRD v2.0 §21.4 (Two-Person Authorization / Separation of Duties)
and PRD v2.0 §21.9 (De-Identification, k-anonymity k>=5, and Zero-PHI Safety Gate).
Logs all export operations immutably to PostgreSQL via AuditService.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

import uuid6

from ayusetu.audit.models import AuditAction, AuditOutcome
from ayusetu.audit.service import AuditService
from ayusetu.gateway.errors import AyuSetuGatewayError, ErrorCode
from ayusetu.consent.service import ConsentService
from ayusetu.deid.engine import PatientDateShifter, transform_raw_encounter_to_deidentified
from ayusetu.deid.k_anonymity import evaluate_k_anonymity
from ayusetu.deid.models import (
    DeidExportRequest,
    DeidExportResponse,
    DeidentifiedRecord,
    ExportPurpose,
)
from ayusetu.deid.policy import MIN_K_ANONYMITY_THRESHOLD
from ayusetu.deid.safety_gate import ZeroPhiSafetyGate, default_safety_gate
from ayusetu.gateway.auth.models import Principal, Role

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeidExportService:
    """
    Authoritative coordinator for de-identified cohort exports.
    """

    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
        consent_service: Optional[ConsentService] = None,
        safety_gate: Optional[ZeroPhiSafetyGate] = None,
    ) -> None:
        self._audit_service = audit_service
        self._consent_service = consent_service
        self._safety_gate = safety_gate or default_safety_gate
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def get_job(self, export_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve export job state by export ID."""
        return self._jobs.get(export_id)

    def register_job(self, export_id: str, job_data: Dict[str, Any]) -> None:
        """Register or update an export job in the registry."""
        self._jobs[export_id] = job_data

    def get_download_bundle(self, export_id: str) -> Dict[str, Any]:
        """Fetch sanitized download bundle for an approved completed export."""
        job = self._jobs.get(export_id)
        if not job:
            raise AyuSetuGatewayError(
                ErrorCode.NOT_FOUND,
                f"Export job '{export_id}' not found",
                404,
            )
        if job.get("status") != "completed":
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Export job '{export_id}' is not yet completed (current status: {job.get('status')})",
                400,
            )
        return job.get("bundle", {})

    def clear(self) -> None:
        """Clear job store for testing."""
        self._jobs.clear()

    @property
    def audit_service(self) -> AuditService:
        if self._audit_service is None:
            self._audit_service = AuditService()
        return self._audit_service

    @property
    def consent_service(self) -> ConsentService:
        if self._consent_service is None:
            self._consent_service = ConsentService()
        return self._consent_service

    def validate_two_person_authorization(
        self,
        request: DeidExportRequest,
        principal: Principal,
    ) -> None:
        """
        Enforces PRD §21.4 Separation of Duties:
        - Requester / Exporter must have Role.MRD or Role.AUDITOR
        - approver_1 and approver_2 must be non-empty and distinct
        - approver_1 and approver_2 must be distinct from the caller (requester != approver_1 != approver_2)
        """
        if principal.role not in (Role.MRD, Role.AUDITOR, Role.ADMIN):
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Role '{principal.role.value}' is not authorized to request de-identified exports (requires MRD or AUDITOR)",
                403,
            )

        app1 = (request.approver_1 or "").strip()
        app2 = (request.approver_2 or "").strip()
        caller_id = (principal.actor_id or "").strip()

        if not app1 or not app2:
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Two distinct approvers are required for de-identified data export (Separation of Duties)",
                400,
            )

        if app1 == app2:
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Approver 1 and Approver 2 cannot be the same individual (Separation of Duties)",
                403,
            )

        if caller_id and (caller_id == app1 or caller_id == app2):
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Exporter cannot approve their own export request (Separation of Duties)",
                403,
            )

    def export_cohort(
        self,
        request: DeidExportRequest,
        principal: Principal,
        candidate_records: List[Dict[str, Any]],
        export_salt: Optional[str] = None,
    ) -> DeidExportResponse:
        """
        Executes end-to-end de-identification, DPDP consent filtering, k-anonymity validation,
        Zero-PHI safety gate verification, and immutable PostgreSQL audit logging.
        """
        export_id = str(uuid6.uuid7())
        actor_id = principal.actor_id or "unknown_actor"
        actor_role = principal.role.value if hasattr(principal.role, "value") else str(principal.role)

        # 1. Enforce Two-Person Authorization (PRD §21.4)
        try:
            self.validate_two_person_authorization(request, principal)
        except AyuSetuGatewayError as err:
            # Audit log authorization failure
            try:
                self.audit_service.record_event(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action=AuditAction.EXPORT,
                    resource_type="deid_export",
                    resource_id=export_id,
                    outcome=AuditOutcome.DENY,
                    reason=f"Export authorization failed: {err.message}",
                    safe_metadata={
                        "export_id": export_id,
                        "purpose": request.purpose.value,
                        "date_from": request.date_from,
                        "date_to": request.date_to,
                        "approver_1": request.approver_1,
                        "approver_2": request.approver_2,
                    },
                )
            except Exception as log_err:
                logger.error("Failed to log export auth failure to audit: %s", log_err)
            raise

        # 2. DPDP Consent Purpose Filtering
        purpose_str = request.purpose.value
        consented_candidates: List[Dict[str, Any]] = []
        for raw_rec in candidate_records:
            enc_id = raw_rec.get("encounter_id") or raw_rec.get("encounter_uuid")
            # If encounter_id is present and consent_service is active, check DPDP purpose consent
            if enc_id:
                try:
                    if not self.consent_service.check_purpose_consent(str(enc_id), purpose_str):
                        continue
                except Exception as e:
                    logger.warning("Consent check failed for encounter %s, excluding from export: %s", enc_id, e)
                    continue
            consented_candidates.append(raw_rec)

        # 3. Transform Records (Per-patient date shift, 90+ age banding, geography 20k threshold, structured-only)
        shifter = PatientDateShifter()
        deidentified_records: List[DeidentifiedRecord] = []
        for raw_rec in consented_candidates:
            deid_rec = transform_raw_encounter_to_deidentified(
                raw_record=raw_rec,
                shifter=shifter,
                export_salt=export_salt,
            )
            deidentified_records.append(deid_rec)

        # 4. Evaluate k-Anonymity (k >= 5)
        k_result = evaluate_k_anonymity(deidentified_records, k_threshold=MIN_K_ANONYMITY_THRESHOLD)
        if not k_result.is_compliant:
            # Block release per PRD §21.9
            try:
                self.audit_service.record_event(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action=AuditAction.EXPORT,
                    resource_type="deid_export",
                    resource_id=export_id,
                    outcome=AuditOutcome.DENY,
                    reason=f"k-anonymity threshold k>={MIN_K_ANONYMITY_THRESHOLD} not achieved (min_class_size={k_result.min_class_size})",
                    safe_metadata={
                        "export_id": export_id,
                        "purpose": purpose_str,
                        "candidate_count": len(consented_candidates),
                        "min_class_size": k_result.min_class_size,
                        "k_threshold": MIN_K_ANONYMITY_THRESHOLD,
                    },
                )
            except Exception as log_err:
                logger.error("Failed to log k-anonymity failure to audit: %s", log_err)

            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Export rejected: k-anonymity requirement (k>={MIN_K_ANONYMITY_THRESHOLD}) not satisfied (smallest class size: {k_result.min_class_size})",
                422,
            )

        # 5. Zero-PHI Pre-Release Safety Gate
        safety_result = self._safety_gate.evaluate_records(deidentified_records)
        if not safety_result.passed:
            try:
                self.audit_service.record_event(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action=AuditAction.EXPORT,
                    resource_type="deid_export",
                    resource_id=export_id,
                    outcome=AuditOutcome.DENY,
                    reason=f"Zero-PHI safety gate failed: {len(safety_result.violations)} violations detected",
                    safe_metadata={
                        "export_id": export_id,
                        "purpose": purpose_str,
                        "violations_count": len(safety_result.violations),
                    },
                )
            except Exception as log_err:
                logger.error("Failed to log safety gate failure to audit: %s", log_err)

            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                f"Export rejected by Zero-PHI Safety Gate: {'; '.join(safety_result.violations[:3])}",
                500,
            )

        # 6. Immutable PostgreSQL Audit Log (ALLOW)
        try:
            self.audit_service.record_event(
                actor_id=actor_id,
                actor_role=actor_role,
                action=AuditAction.EXPORT,
                resource_type="deid_export",
                resource_id=export_id,
                outcome=AuditOutcome.ALLOW,
                reason=f"Authorized de-identified cohort export ({purpose_str})",
                safe_metadata={
                    "export_id": export_id,
                    "purpose": purpose_str,
                    "cohort_size": len(deidentified_records),
                    "k_anonymity_achieved": True,
                    "min_class_size": k_result.min_class_size,
                    "date_from": request.date_from,
                    "date_to": request.date_to,
                    "approver_1": request.approver_1,
                    "approver_2": request.approver_2,
                    "department": request.department,
                },
            )
        except Exception as log_err:
            logger.error("Failed to record successful export audit event: %s", log_err)

        return DeidExportResponse(
            export_id=export_id,
            status="COMPLETED",
            purpose=purpose_str,
            cohort_size=len(deidentified_records),
            k_anonymity_achieved=True,
            min_class_size=k_result.min_class_size,
            records=deidentified_records,
            exported_at=_utc_now_iso(),
        )


# Global singleton instance
deid_export_service = DeidExportService()
