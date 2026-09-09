"""
Offline Station Audit Chain Manager
===================================
Manages local cryptographic audit logging on peripheral stations & devices
during offline clinic intake per PRD v2.0 §21.8.
Maintains local monotonic sequencing anchored to the last known global server head.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

from ayusetu.audit.models import OfflineAuditEventDTO, OfflineAuditSyncBatch
from ayusetu.audit.chain import compute_payload_hash, compute_offline_entry_hash


class OfflineStationAuditChain:
    """
    Manages local append-only audit events on an edge station / kiosk.
    """

    def __init__(self, device_id: str, seed_head_hash: str) -> None:
        self.device_id = device_id
        self.seed_head_hash = seed_head_hash
        self._lock = threading.Lock()
        self._events: List[OfflineAuditEventDTO] = []
        self._current_tip = seed_head_hash

    def record_offline_event(
        self,
        actor_id: str,
        actor_role: str,
        action: str,
        resource_type: str,
        resource_id: str,
        outcome: str = "ALLOW",
        reason: Optional[str] = None,
        patient_id: Optional[str] = None,
        encounter_id: Optional[str] = None,
        safe_metadata: Optional[Dict[str, Any]] = None,
        forced_ts: Optional[str] = None,
    ) -> OfflineAuditEventDTO:
        """
        Append a local audit event to the station's offline chain.
        """
        with self._lock:
            local_seq = len(self._events) + 1
            ts = forced_ts or datetime.now(timezone.utc).isoformat()
            prev_hash = self._current_tip

            payload_hash = compute_payload_hash(safe_metadata)
            entry_hash = compute_offline_entry_hash(
                local_seq=local_seq,
                ts=ts,
                actor_id=str(actor_id),
                actor_role=str(actor_role),
                action=str(action),
                resource_type=str(resource_type),
                resource_id=str(resource_id),
                outcome=str(outcome),
                payload_hash=payload_hash,
                prev_hash=prev_hash,
                src_device=self.device_id,
                patient_id=str(patient_id) if patient_id else None,
                encounter_id=str(encounter_id) if encounter_id else None,
                reason=reason,
            )

            dto = OfflineAuditEventDTO(
                local_seq=local_seq,
                ts=ts,
                actor_id=str(actor_id),
                actor_role=str(actor_role),
                action=str(action),
                resource_type=str(resource_type),
                resource_id=str(resource_id),
                patient_id=str(patient_id) if patient_id else None,
                encounter_id=str(encounter_id) if encounter_id else None,
                outcome=str(outcome),
                reason=reason,
                src_device=self.device_id,
                payload_hash=payload_hash,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )

            self._events.append(dto)
            self._current_tip = entry_hash
            return dto

    def get_sync_batch(self) -> OfflineAuditSyncBatch:
        """Construct the sync batch to transmit to the central server upon reconnection."""
        with self._lock:
            return OfflineAuditSyncBatch(
                device_id=self.device_id,
                seed_head_hash=self.seed_head_hash,
                events=list(self._events),
            )

    def mark_synced(self, new_server_head_hash: str) -> None:
        """
        After successful server acknowledgment and splicing, re-seed the offline chain
        with the latest server head and reset the local event buffer.
        """
        with self._lock:
            self.seed_head_hash = new_server_head_hash
            self._current_tip = new_server_head_hash
            self._events.clear()

    def pending_count(self) -> int:
        """Number of local events waiting to be synced."""
        with self._lock:
            return len(self._events)
