"""
Audit Quarantine Management
===========================
Isolates tampered, corrupted, or replayed offline audit chains.
Generates P1 security alerts without contaminating the global audit log.
Guarantees zero PHI retention in quarantine records.
"""

from datetime import datetime, timezone
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from ayusetu.audit.models import QuarantineRecordDTO
from ayusetu.gateway.auth.event_hooks import dispatch_security_event

logger = logging.getLogger("ayusetu.audit.quarantine")


class QuarantineStore:
    """In-memory store for quarantined audit sync batches."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: List[QuarantineRecordDTO] = []

    def quarantine_batch(
        self,
        device_id: str,
        seed_head_hash: str,
        reason: str,
        failure_code: str,
        event_count: int,
        safe_metadata: Optional[Dict[str, Any]] = None,
    ) -> QuarantineRecordDTO:
        """
        Isolate an invalid offline batch and trigger a P1 security event.
        """
        with self._lock:
            record = QuarantineRecordDTO(
                quarantine_id=str(uuid.uuid4()),
                device_id=device_id,
                seed_head_hash=seed_head_hash,
                reason=reason,
                failure_code=failure_code,
                quarantined_at=datetime.now(timezone.utc).isoformat(),
                event_count=event_count,
                safe_metadata=safe_metadata or {},
            )
            self._records.append(record)

        logger.critical(
            "P1 SECURITY ALERT [AUDIT_BATCH_QUARANTINED]: device=%s, reason=%s, code=%s, events=%d",
            device_id,
            reason,
            failure_code,
            event_count,
        )

        # Dispatch security event to M3 security hook
        try:
            dispatch_security_event(
                event_type="OFFLINE_AUDIT_QUARANTINED",
                actor_id=device_id,
                actor_role="device",
                target_resource="audit_chain",
                reason=f"{failure_code}: {reason}",
                metadata={
                    "quarantine_id": record.quarantine_id,
                    "event_count": event_count,
                    "seed_head_hash": seed_head_hash,
                },
            )
        except Exception as e:
            logger.error("Failed to dispatch security event for quarantine: %s", e)

        return record

    def list_records(self) -> List[QuarantineRecordDTO]:
        """List all quarantined batches."""
        with self._lock:
            return list(self._records)

    def clear_for_testing(self) -> None:
        """Clear store for test isolation."""
        with self._lock:
            self._records.clear()


quarantine_store = QuarantineStore()
