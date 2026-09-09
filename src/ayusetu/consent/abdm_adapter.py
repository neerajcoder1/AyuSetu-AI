"""
ABDM Consent Artefact & HIE Boundary Adapter
=============================================
Manages the lifecycle of ABDM Consent Artefacts per PRD v2.0 §21.7.

CRITICAL INVARIANTS:
1. DPDP consent granted offline is valid immediately for hospital clinical intake,
   but CANNOT manufacture an ABDM consent artefact offline.
2. NO DATA MAY BE SHARED OUTSIDE THE HOSPITAL BEFORE THE ABDM CONSENT ARTEFACT EXISTS.
3. ABDM consent artefacts are strictly generated upon network reconnection through
   an authoritative external Consent Manager (CM) callback.
4. Offline sync must NEVER manufacture an AVAILABLE artefact.

PRODUCTION INTEGRATION BOUNDARY:
This adapter enforces the state machine, offline safety gating, and external sharing boundary.
Production deployment MUST connect this adapter to the official NHA ABDM Gateway APIs
(POST /v0.5/consent-requests/init and webhook callback /v0.5/consent-requests/on-init).
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ayusetu.consent.models import ABDMArtifactStatus, ABDMStatusResponse
from ayusetu.consent.event_hooks import emit_abdm_artifact_event


class ABDMConsentManagerAdapter:
    """
    Adapter managing ABDM Consent Artefact state transitions and external sharing policy.
    Does NOT manufacture fake artefacts during offline synchronization.
    """

    def __init__(self):
        # In-memory lifecycle store: encounter_id -> {status, artefact_id, last_updated}
        self._artifact_store: Dict[str, Dict[str, Any]] = {}

    def initialize_encounter(self, encounter_id: str, abdm_requested: bool, is_offline: bool = False) -> ABDMArtifactStatus:
        """Initialize ABDM lifecycle for an encounter."""
        if not abdm_requested:
            status = ABDMArtifactStatus.NOT_REQUESTED
            artefact_id = None
        elif is_offline:
            # Offline capture CANNOT manufacture an ABDM artefact!
            status = ABDMArtifactStatus.PENDING
            artefact_id = None
        else:
            # Online capture initiates async request to Consent Manager
            status = ABDMArtifactStatus.PENDING
            artefact_id = None
            emit_abdm_artifact_event("ABDM_ARTIFACT_REQUESTED", encounter_id)

        self._artifact_store[encounter_id] = {
            "status": status,
            "artefact_id": artefact_id,
            "last_updated": datetime.now(timezone.utc),
        }
        return status

    def request_artefact(self, encounter_id: str) -> ABDMStatusResponse:
        """
        Request ABDM artefact creation via the external Consent Manager / HIE.
        Sets state to PENDING awaiting authoritative external callback.
        """
        self._artifact_store[encounter_id] = {
            "status": ABDMArtifactStatus.PENDING,
            "artefact_id": None,
            "last_updated": datetime.now(timezone.utc),
        }
        emit_abdm_artifact_event("ABDM_ARTIFACT_REQUESTED", encounter_id)
        return self.get_status(encounter_id)

    def handle_authoritative_artefact_callback(self, encounter_id: str, artefact_id: str) -> ABDMStatusResponse:
        """
        Authoritative callback received from the external ABDM Consent Manager / HIE.
        Transitions the state to AVAILABLE only when a valid external artefact_id is presented.
        """
        if not artefact_id or not str(artefact_id).strip():
            raise ValueError("An authoritative external artefact_id is required to establish AVAILABLE status")

        self._artifact_store[encounter_id] = {
            "status": ABDMArtifactStatus.AVAILABLE,
            "artefact_id": str(artefact_id).strip(),
            "last_updated": datetime.now(timezone.utc),
        }
        emit_abdm_artifact_event("ABDM_ARTIFACT_AVAILABLE", encounter_id, artefact_id=str(artefact_id).strip())
        return self.get_status(encounter_id)

    def handle_artefact_failure_callback(self, encounter_id: str, error_reason: str) -> ABDMStatusResponse:
        """Handle failure callback from Consent Manager."""
        self._artifact_store[encounter_id] = {
            "status": ABDMArtifactStatus.FAILED,
            "artefact_id": None,
            "last_updated": datetime.now(timezone.utc),
        }
        emit_abdm_artifact_event("ABDM_ARTIFACT_FAILED", encounter_id, error_message=error_reason)
        return self.get_status(encounter_id)

    def withdraw_artefact(self, encounter_id: str) -> None:
        """Revoke ABDM sharing when consent is withdrawn."""
        self._artifact_store[encounter_id] = {
            "status": ABDMArtifactStatus.NOT_REQUESTED,
            "artefact_id": None,
            "last_updated": datetime.now(timezone.utc),
        }
        emit_abdm_artifact_event("ABDM_ARTIFACT_WITHDRAWN", encounter_id)

    def get_status(self, encounter_id: str) -> ABDMStatusResponse:
        """Query current ABDM artefact status for an encounter."""
        record = self._artifact_store.get(encounter_id)
        if not record:
            return ABDMStatusResponse(
                encounter_id=encounter_id,
                status=ABDMArtifactStatus.NOT_REQUESTED,
                artefact_id=None,
                is_external_sharing_permitted=False,
                last_updated=datetime.now(timezone.utc),
            )

        status: ABDMArtifactStatus = record["status"]
        artefact_id = record.get("artefact_id")
        is_permitted = (status == ABDMArtifactStatus.AVAILABLE and artefact_id is not None)

        return ABDMStatusResponse(
            encounter_id=encounter_id,
            status=status,
            artefact_id=artefact_id,
            is_external_sharing_permitted=is_permitted,
            last_updated=record["last_updated"],
        )

    def is_external_sharing_permitted(self, encounter_id: str) -> bool:
        """
        Enforce external data sharing gate.
        Returns True ONLY if an authoritative ABDM consent artefact exists in AVAILABLE status.
        """
        status_resp = self.get_status(encounter_id)
        return status_resp.is_external_sharing_permitted

    def clear(self) -> None:
        """Reset state for tests."""
        self._artifact_store.clear()


# Default singleton instance
abdm_manager = ABDMConsentManagerAdapter()
