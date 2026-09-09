"""
Consent & DPDP Core Service Engine
===================================
Authoritative engine for:
- DPDP consent granting & immutable versioning
- Granular 4-purpose evaluation & consent gating
- Purpose-level withdrawal and historical retention
- Idempotent erasure handling & downstream propagation
- Offline consent recording & cryptographic verification
- ABDM consent-artifact lifecycle integration
- Session panic-clear decoupling
per PRD v2.0 §21.7 & §21.8.
"""

from datetime import datetime, timezone
import hashlib
import logging
from typing import Any, Dict, List, Optional
import uuid6

logger = logging.getLogger("ayusetu.consent.service")

from ayusetu.common.config import settings
from ayusetu.gateway.auth.models import Principal, Role
from ayusetu.gateway.errors import ErrorCode, AyuSetuGatewayError
from ayusetu.consent.models import (
    Purposes,
    GuardianContext,
    ConsentRecordDTO,
    ConsentStatus,
    ConsentGrantRequest,
    ConsentWithdrawRequest,
    ErasureRequest,
    ErasureResponse,
    ErasureStatus,
    OfflineConsentPayload,
    OfflineSyncResponse,
    utc_now,
)
from ayusetu.consent.guardian import ConsentAuthorityValidator, GuardianVerificationAdapter
from ayusetu.consent.offline_chain import station_consent_chain, canonical_json
from ayusetu.consent.abdm_adapter import abdm_manager
from ayusetu.consent.repository import ConsentRepository
from ayusetu.consent.event_hooks import (
    emit_consent_granted,
    emit_consent_withdrawn,
    emit_erasure_requested,
    emit_erasure_propagated,
    emit_offline_consent_captured,
    emit_offline_consent_synced,
    emit_consent_denied,
)


class ConsentService:
    """Core domain service for DPDP consent management and gating."""

    def __init__(self, repository: Optional[ConsentRepository] = None):
        # Authoritative PostgreSQL repository for immutable, versioned consent records
        self._repo = repository or ConsentRepository()
        # Erasure store: request_id -> ErasureResponse, and (patient_id, encounter_id) -> request_id
        self._erasure_store: Dict[str, ErasureResponse] = {}
        self._erasure_index: Dict[str, str] = {}

    def grant_consent(
        self,
        request: ConsentGrantRequest,
        principal: Optional[Principal] = None,
        is_offline: bool = False,
        device_id: Optional[str] = None,
    ) -> ConsentRecordDTO:
        """
        Grant or update DPDP consent for an encounter.
        Creates an immutable, versioned consent record.
        """
        enc_id = str(request.encounter_id)
        pat_id = str(request.patient_id)
        actor_id = principal.actor_id if principal else pat_id

        # 1. Enforce Guardian / Minor & Companion Authority Boundary
        ConsentAuthorityValidator.validate_grant_authority(
            principal=principal,
            patient_id=pat_id,
            is_minor=request.is_minor,
            guardian_context=request.guardian_context,
        )

        purposes_dict = request.purposes.to_dict()

        # 2. Determine Version Number from PostgreSQL
        history = self._repo.get_consent_history(enc_id)
        version = len(history) + 1

        # 3. Calculate deterministic chain hash
        consent_id = str(uuid6.uuid7())
        guardian_id = request.guardian_context.guardian_id if request.guardian_context else None
        payload_meta = {
            "consent_id": consent_id,
            "patient_id": pat_id,
            "encounter_id": enc_id,
            "purposes": purposes_dict,
            "version": version,
            "notice_version": request.notice_version,
            "is_minor": request.is_minor,
            "guardian_id": guardian_id,
        }
        chain_hash = hashlib.sha256(canonical_json(payload_meta)).hexdigest()

        # 4. Initialize ABDM lifecycle (PENDING or NOT_REQUESTED; never creates fake artefact)
        abdm_manager.initialize_encounter(
            encounter_id=enc_id,
            abdm_requested=request.purposes.abdm,
            is_offline=is_offline,
        )

        record_dto = ConsentRecordDTO(
            id=consent_id,
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=purposes_dict,
            language=request.language,
            notice_version=request.notice_version,
            granted_at=utc_now(),
            withdrawn_at=None,
            abdm_artefact_id=None,
            chain_hash=chain_hash,
            version=version,
            status=ConsentStatus.ACTIVE,
            is_offline=is_offline,
            guardian_id=guardian_id,
        )

        # Store durably in PostgreSQL (fail-closed)
        saved_record = self._repo.save_consent(record_dto)

        # 5. Emit zero-PHI security event
        emit_consent_granted(
            patient_id=pat_id,
            encounter_id=enc_id,
            consent_id=consent_id,
            purposes=purposes_dict,
            notice_version=request.notice_version,
            actor_id=actor_id,
            is_offline=is_offline,
            is_minor=request.is_minor,
            guardian_id=guardian_id,
        )

        return saved_record

    def get_active_consent(self, encounter_id: str) -> Optional[ConsentRecordDTO]:
        """Retrieve latest active consent record for an encounter from PostgreSQL."""
        return self._repo.get_active_consent(encounter_id)

    def get_consent_history(self, encounter_id: str) -> List[ConsentRecordDTO]:
        """Retrieve complete immutable version trail for an encounter from PostgreSQL."""
        return self._repo.get_consent_history(encounter_id)

    def withdraw_consent(
        self,
        request: ConsentWithdrawRequest,
        principal: Optional[Principal] = None,
    ) -> ConsentRecordDTO:
        """
        Withdraw specific or all consent purposes.
        Creates a new immutable versioned record without mutating any previous records.
        """
        enc_id = str(request.encounter_id)
        current = self.get_active_consent(enc_id)
        if not current:
            raise AyuSetuGatewayError(
                ErrorCode.RESOURCE_NOT_FOUND,
                f"No active consent record found for encounter {enc_id}",
                404
            )

        actor_id = principal.actor_id if principal else current.patient_id

        # Calculate updated purposes for the new version
        new_purposes = dict(current.purposes)
        withdrawn_list = []

        if "all" in [p.lower() for p in request.purposes_to_withdraw]:
            for p in new_purposes:
                new_purposes[p] = False
            withdrawn_list = list(current.purposes.keys())
            status = ConsentStatus.WITHDRAWN
        else:
            for p in request.purposes_to_withdraw:
                p_clean = p.lower().strip()
                if p_clean in new_purposes:
                    new_purposes[p_clean] = False
                    withdrawn_list.append(p_clean)

            # Check if any purpose is still active
            if any(new_purposes.values()):
                status = ConsentStatus.PARTIALLY_WITHDRAWN
            else:
                status = ConsentStatus.WITHDRAWN

        # If ABDM withdrawn, notify ABDM manager
        if not new_purposes.get("abdm", False):
            abdm_manager.withdraw_artefact(enc_id)

        # Create new versioned record in PostgreSQL - DO NOT mutate `current` (true immutability!)
        history = self._repo.get_consent_history(enc_id)
        version = len(history) + 1
        new_consent_id = str(uuid6.uuid7())
        now = utc_now()

        payload_meta = {
            "consent_id": new_consent_id,
            "patient_id": current.patient_id,
            "encounter_id": enc_id,
            "purposes": new_purposes,
            "version": version,
            "status": status.value,
            "withdrawn_purposes": withdrawn_list,
        }
        chain_hash = hashlib.sha256(canonical_json(payload_meta)).hexdigest()

        new_record = ConsentRecordDTO(
            id=new_consent_id,
            patient_id=current.patient_id,
            encounter_id=enc_id,
            purposes=new_purposes,
            language=current.language,
            notice_version=current.notice_version,
            granted_at=current.granted_at,
            withdrawn_at=now,
            abdm_artefact_id=None,
            chain_hash=chain_hash,
            version=version,
            status=status,
            is_offline=current.is_offline,
            guardian_id=current.guardian_id,
        )

        saved_record = self._repo.save_consent(new_record)

        # Emit audit event
        emit_consent_withdrawn(
            patient_id=current.patient_id,
            encounter_id=enc_id,
            consent_id=new_consent_id,
            withdrawn_purposes=withdrawn_list,
            remaining_purposes=new_purposes,
            actor_id=actor_id,
            reason=request.reason,
        )

        return saved_record

    def request_erasure(
        self,
        request: ErasureRequest,
        principal: Optional[Principal] = None,
    ) -> ErasureResponse:
        """
        Handle DPDP erasure request idempotently with downstream propagation event.
        """
        pat_id = str(request.patient_id)
        enc_id = str(request.encounter_id) if request.encounter_id else None
        index_key = f"{pat_id}:{enc_id or 'all'}"

        # Idempotency check: if identical erasure was already requested, return existing response
        existing_req_id = self._erasure_index.get(index_key)
        if existing_req_id and existing_req_id in self._erasure_store:
            return self._erasure_store[existing_req_id]

        actor_id = principal.actor_id if principal else pat_id
        req_id = str(uuid6.uuid7())
        now = utc_now()

        # Emit initial request event
        emit_erasure_requested(
            request_id=req_id,
            patient_id=pat_id,
            encounter_id=enc_id,
            actor_id=actor_id,
            reason=request.reason,
        )

        # Emit propagation event to downstream stores
        target_stores = ["derived_feature_store", "transcription_cache", "analytics_staging"]
        emit_erasure_propagated(
            request_id=req_id,
            patient_id=pat_id,
            encounter_id=enc_id,
            target_stores=target_stores,
        )

        resp = ErasureResponse(
            request_id=req_id,
            patient_id=pat_id,
            encounter_id=enc_id,
            status=ErasureStatus.PROPAGATED,
            requested_at=now,
            propagated_at=now,
        )

        self._erasure_store[req_id] = resp
        self._erasure_index[index_key] = req_id
        return resp

    def get_erasure_status(self, request_id: str) -> Optional[ErasureResponse]:
        """Retrieve status of an erasure request."""
        return self._erasure_store.get(request_id)

    def capture_offline_consent(
        self,
        payload: OfflineConsentPayload,
        principal: Optional[Principal] = None,
    ) -> ConsentRecordDTO:
        """
        Capture offline consent with cryptographic hash chain integrity.
        Valid immediately for local clinical intake, but does NOT create an ABDM artefact.
        """
        enc_id = str(payload.encounter_id)
        pat_id = str(payload.patient_id)

        # Validate authority via trusted adapter
        ConsentAuthorityValidator.validate_grant_authority(
            principal=principal,
            patient_id=pat_id,
            is_minor=payload.is_minor,
            guardian_context=payload.guardian_context,
        )

        purposes_dict = payload.purposes.to_dict()

        # 1. Append to local deterministic SHA-256 hash chain
        chain_payload = {
            "patient_id": pat_id,
            "encounter_id": enc_id,
            "purposes": purposes_dict,
            "language": payload.language,
            "notice_version": payload.notice_version,
            "device_id": payload.device_id,
            "is_minor": payload.is_minor,
            "guardian_id": payload.guardian_context.guardian_id if payload.guardian_context else None,
        }
        entry = station_consent_chain.append(
            payload=chain_payload,
            ts_str=payload.captured_at.isoformat(),
        )

        # 2. Initialize ABDM state as PENDING (no fake artefact offline!)
        abdm_manager.initialize_encounter(
            encounter_id=enc_id,
            abdm_requested=payload.purposes.abdm,
            is_offline=True,
        )

        history = self._repo.get_consent_history(enc_id)
        version = len(history) + 1
        consent_id = str(uuid6.uuid7())

        record = ConsentRecordDTO(
            id=consent_id,
            patient_id=pat_id,
            encounter_id=enc_id,
            purposes=purposes_dict,
            language=payload.language,
            notice_version=payload.notice_version,
            granted_at=payload.captured_at,
            withdrawn_at=None,
            abdm_artefact_id=None,
            chain_hash=entry.entry_hash,
            version=version,
            status=ConsentStatus.ACTIVE,
            is_offline=True,
            guardian_id=payload.guardian_context.guardian_id if payload.guardian_context else None,
        )

        saved_record = self._repo.save_consent(record)

        # 3. Emit offline capture event
        emit_offline_consent_captured(
            encounter_id=enc_id,
            patient_id=pat_id,
            device_id=payload.device_id,
            seq=entry.seq,
            entry_hash=entry.entry_hash,
        )

        return saved_record

    def sync_offline_consent(self) -> OfflineSyncResponse:
        """
        Synchronize pending offline consent chain to server upon network reconnection.
        Verifies full cryptographic chain integrity before synchronization.
        Does NOT manufacture fake ABDM artefacts (requests them via CM, remaining PENDING).
        """
        # 1. Cryptographic chain integrity verification
        if not station_consent_chain.verify_chain():
            raise AyuSetuGatewayError(
                ErrorCode.POLICY_DENIED,
                "Offline consent hash chain integrity check failed: chain is corrupted or tampered",
                400
            )

        pending_entries = station_consent_chain.get_pending_sync_entries()
        synced_count = 0
        pending_abdm = 0

        seqs_to_mark = []
        for entry in pending_entries:
            enc_id = entry.payload.get("encounter_id")
            purposes = entry.payload.get("purposes", {})
            if enc_id:
                # If ABDM was requested offline, queue request to CM (state remains PENDING awaiting callback)
                if purposes.get("abdm", False):
                    abdm_manager.request_artefact(enc_id)
                    pending_abdm += 1
            seqs_to_mark.append(entry.seq)
            synced_count += 1

        station_consent_chain.mark_synced(seqs_to_mark)

        head_hash = station_consent_chain.get_head_hash()
        emit_offline_consent_synced(synced_count=synced_count, head_hash=head_hash)

        return OfflineSyncResponse(
            synced_count=synced_count,
            pending_abdm_requests=pending_abdm,
            chain_verified=True,
            status="synchronized",
        )

    def check_clinical_consent(self, encounter_id: str) -> bool:
        """
        Consent Gating Check:
        Returns True if and only if valid, non-withdrawn clinical consent exists.
        Fails closed on database failure or missing consent.
        """
        try:
            record = self.get_active_consent(encounter_id)
            if not record:
                return False
            if record.status == ConsentStatus.WITHDRAWN:
                return False
            return bool(record.purposes.get("clinical", False))
        except Exception as e:
            logger.error("Database error during clinical consent check for encounter %s: %s", encounter_id, e)
            return False

    def check_purpose_consent(self, encounter_id: str, purpose: str) -> bool:
        """
        Check if a specific purpose (clinical, abdm, qi, research) is active.
        Fails closed on database failure or missing consent.
        """
        try:
            record = self.get_active_consent(encounter_id)
            if not record:
                return False
            if record.status == ConsentStatus.WITHDRAWN:
                return False
            return bool(record.purposes.get(purpose.lower(), False))
        except Exception as e:
            logger.error("Database error during purpose consent check (%s) for encounter %s: %s", purpose, encounter_id, e)
            return False

    def is_external_sharing_permitted(self, encounter_id: str) -> bool:
        """
        External Sharing Gate:
        Sharing outside the hospital is permitted ONLY if:
        1. ABDM purpose is explicitly consented, AND
        2. Authoritative ABDM artefact is in AVAILABLE status.
        Fails closed on database failure.
        """
        if not self.check_purpose_consent(encounter_id, "abdm"):
            return False
        return abdm_manager.is_external_sharing_permitted(encounter_id)

    def handle_session_panic_clear(self, session_id: str, encounter_id: Optional[str] = None) -> None:
        """
        Panic-Clear Integration:
        Invalidates active session credentials without falsely erasing/withdrawing
        the patient's historical consent records.
        """
        from ayusetu.common.session_cache import SessionCache
        session_cache = SessionCache()
        session_cache.panic_clear(session_id)
        if encounter_id:
            session_cache.panic_clear(encounter_id)

    def reset_state(self) -> None:
        """Reset service state for test suite isolation."""
        self._repo.clear_for_testing()
        self._erasure_store.clear()
        self._erasure_index.clear()
        station_consent_chain.clear()
        abdm_manager.clear()
        GuardianVerificationAdapter.clear()


# Default singleton instance
consent_service = ConsentService()
