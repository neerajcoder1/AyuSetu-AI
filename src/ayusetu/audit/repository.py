"""
Audit Append-Only Repository
============================
Thread-safe, append-only repository managing the global cryptographic audit chain.
Enforces strict monotonicity, atomicity, and immutability.
No update or deletion operations are exposed.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

from ayusetu.audit.models import AuditAction, AuditEventCreate, AuditEventDTO, AuditHeadDTO, AuditOutcome
from ayusetu.audit.chain import GENESIS_HASH, compute_payload_hash, compute_entry_hash


class AuditRepository:
    """
    Append-only repository for storing and querying cryptographic audit events.
    Guarantees thread-safe atomic sequence increments and head progression.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: List[AuditEventDTO] = []
        self._head: AuditHeadDTO = AuditHeadDTO(
            seq=0,
            entry_hash=GENESIS_HASH,
            ts=datetime.now(timezone.utc).isoformat(),
        )

    def append(
        self,
        event_create: AuditEventCreate,
        forced_ts: Optional[str] = None,
    ) -> AuditEventDTO:
        """
        Atomically append an event to the global audit chain.
        Allocates the next monotonic sequence number and advances the global head.
        """
        with self._lock:
            next_seq = self._head.seq + 1
            prev_hash = self._head.entry_hash
            ts = forced_ts or datetime.now(timezone.utc).isoformat()

            # Compute hashes
            payload_hash = compute_payload_hash(event_create.safe_metadata)
            entry_hash = compute_entry_hash(
                seq=next_seq,
                ts=ts,
                actor_id=event_create.actor_id,
                actor_role=event_create.actor_role,
                action=event_create.action.value if isinstance(event_create.action, AuditAction) else str(event_create.action),
                resource_type=event_create.resource_type,
                resource_id=event_create.resource_id,
                outcome=event_create.outcome.value if isinstance(event_create.outcome, AuditOutcome) else str(event_create.outcome),
                payload_hash=payload_hash,
                prev_hash=prev_hash,
                patient_id=event_create.patient_id,
                encounter_id=event_create.encounter_id,
                reason=event_create.reason,
                src_device=event_create.src_device,
                src_ip=event_create.src_ip,
            )

            dto = AuditEventDTO(
                seq=next_seq,
                ts=ts,
                actor_id=event_create.actor_id,
                actor_role=event_create.actor_role,
                action=event_create.action.value if isinstance(event_create.action, AuditAction) else str(event_create.action),
                resource_type=event_create.resource_type,
                resource_id=event_create.resource_id,
                patient_id=event_create.patient_id,
                encounter_id=event_create.encounter_id,
                outcome=event_create.outcome.value if isinstance(event_create.outcome, AuditOutcome) else str(event_create.outcome),
                reason=event_create.reason,
                src_device=event_create.src_device,
                src_ip=event_create.src_ip,
                payload_hash=payload_hash,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            )

            self._events.append(dto)
            self._head = AuditHeadDTO(seq=next_seq, entry_hash=entry_hash, ts=ts)
            return dto

    def get_head(self) -> AuditHeadDTO:
        """Retrieve current global audit head."""
        with self._lock:
            return self._head

    def get_by_seq(self, seq: int) -> Optional[AuditEventDTO]:
        """Look up single audit record by monotonic sequence number."""
        with self._lock:
            if 1 <= seq <= len(self._events):
                return self._events[seq - 1]
            return None

    def get_range(
        self,
        from_seq: int = 1,
        to_seq: Optional[int] = None,
        limit: int = 100,
        encounter_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
    ) -> List[AuditEventDTO]:
        """
        Query audit records within a sequence range with optional metadata filtering.
        """
        with self._lock:
            results: List[AuditEventDTO] = []
            for ev in self._events:
                if ev.seq < from_seq:
                    continue
                if to_seq is not None and ev.seq > to_seq:
                    break
                if encounter_id and str(ev.encounter_id) != str(encounter_id):
                    continue
                if patient_id and str(ev.patient_id) != str(patient_id):
                    continue
                if actor_id and str(ev.actor_id) != str(actor_id):
                    continue
                if action and ev.action != action:
                    continue
                if resource_type and ev.resource_type != resource_type:
                    continue
                results.append(ev)
                if len(results) >= limit:
                    break
            return results

    def get_all(self) -> List[AuditEventDTO]:
        """Retrieve all events in sequential order (for verifier)."""
        with self._lock:
            return list(self._events)

    def count(self) -> int:
        """Total number of audit events recorded."""
        with self._lock:
            return len(self._events)

    def known_head_hashes(self) -> set[str]:
        """Set of all historical event hashes including genesis."""
        with self._lock:
            hashes = {GENESIS_HASH}
            for ev in self._events:
                hashes.add(ev.entry_hash)
            return hashes

    def clear_for_testing(self) -> None:
        """Reset in-memory repository state for isolated tests."""
        with self._lock:
            self._events.clear()
            self._head = AuditHeadDTO(
                seq=0,
                entry_hash=GENESIS_HASH,
                ts=datetime.now(timezone.utc).isoformat(),
            )
