"""
Audit Quarantine Management
===========================
Isolates tampered, corrupted, or replayed offline audit chains.
Durable PostgreSQL persistence for quarantined batches per PRD v2.0 §21.8.
Generates P1 security alerts without contaminating the global audit log.
Guarantees ZERO PHI retention in quarantine records and fails closed if DB unavailable.
"""

from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import sessionmaker

from ayusetu.audit.models import QuarantineRecordDTO
from ayusetu.audit.repository import get_default_session_factory
from ayusetu.common.database import Base
from ayusetu.common.models import QuarantinedAuditBatch
from ayusetu.gateway.auth.event_hooks import dispatch_security_event

logger = logging.getLogger("ayusetu.audit.quarantine")

# Safe metadata whitelist for quarantine records
SAFE_QUARANTINE_METADATA_WHITELIST = {
    "quarantine_id",
    "device_id",
    "claimed_device_id",
    "authenticated_device_id",
    "event_count",
    "seed_head_hash",
    "failure_code",
    "reason",
}


def sanitize_quarantine_metadata(raw_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Ensure zero PHI in quarantine metadata."""
    if not raw_meta:
        return {}
    sanitized = {}
    for k, v in raw_meta.items():
        if k in SAFE_QUARANTINE_METADATA_WHITELIST:
            if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                sanitized[k] = v
    return sanitized


class QuarantineStore:
    """
    PostgreSQL-backed store for quarantined audit sync batches.
    Survives process restarts and guarantees zero PHI.
    """

    def __init__(self, session_factory: Optional[sessionmaker] = None) -> None:
        self._lock = threading.Lock()
        self._session_factory = session_factory or get_default_session_factory()
        try:
            bind = self._session_factory.kw.get("bind") if hasattr(self._session_factory, "kw") else None
            if bind is not None:
                Base.metadata.create_all(bind=bind, tables=[QuarantinedAuditBatch.__table__])
        except Exception:
            pass

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
        Isolate an invalid offline batch in PostgreSQL and trigger a P1 security event.
        Fails closed if PostgreSQL persistence fails.
        """
        quarantine_uuid = uuid.uuid4()
        now_dt = datetime.now(timezone.utc)
        sanitized_meta = sanitize_quarantine_metadata(safe_metadata)

        with self._lock:
            with self._session_factory() as db:
                try:
                    db_record = QuarantinedAuditBatch(
                        id=quarantine_uuid,
                        device_id=str(device_id),
                        seed_head_hash=str(seed_head_hash),
                        reason=str(reason),
                        failure_code=str(failure_code),
                        quarantined_at=now_dt,
                        event_count=int(event_count),
                        safe_metadata=sanitized_meta,
                    )
                    db.add(db_record)
                    db.commit()
                    db.refresh(db_record)

                    record_dto = QuarantineRecordDTO(
                        quarantine_id=str(db_record.id),
                        device_id=db_record.device_id,
                        seed_head_hash=db_record.seed_head_hash,
                        reason=db_record.reason,
                        failure_code=db_record.failure_code,
                        quarantined_at=db_record.quarantined_at.isoformat(),
                        event_count=db_record.event_count,
                        safe_metadata=db_record.safe_metadata or {},
                    )
                except Exception as db_err:
                    db.rollback()
                    logger.critical("Failed to persist quarantine record to PostgreSQL: %s", db_err)
                    raise

        logger.critical(
            "P1 SECURITY ALERT [AUDIT_BATCH_QUARANTINED]: device=%s, reason=%s, code=%s, events=%d",
            device_id,
            reason,
            failure_code,
            event_count,
        )

        # Dispatch security event to M3 security hook (which records immutable audit event via normal path)
        try:
            device_actor_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ayusetu.device.{device_id}")) if device_id else "00000000-0000-0000-0000-000000000000"
            dispatch_security_event(
                event_type="OFFLINE_AUDIT_QUARANTINED",
                actor_id=device_actor_uuid,
                actor_role="device",
                target_resource="audit_chain",
                reason=f"{failure_code}: {reason}",
                metadata={
                    "quarantine_id": str(quarantine_uuid),
                    "device_id": device_id,
                    "event_count": event_count,
                    "seed_head_hash": seed_head_hash,
                },
            )
        except Exception as e:
            logger.error("Failed to dispatch security event for quarantine: %s", e)

        return record_dto

    def list_records(self) -> List[QuarantineRecordDTO]:
        """List all quarantined batches from PostgreSQL."""
        with self._session_factory() as db:
            rows = db.query(QuarantinedAuditBatch).order_by(QuarantinedAuditBatch.quarantined_at.asc()).all()
            return [
                QuarantineRecordDTO(
                    quarantine_id=str(r.id),
                    device_id=r.device_id,
                    seed_head_hash=r.seed_head_hash,
                    reason=r.reason,
                    failure_code=r.failure_code,
                    quarantined_at=r.quarantined_at.isoformat() if isinstance(r.quarantined_at, datetime) else str(r.quarantined_at),
                    event_count=r.event_count,
                    safe_metadata=r.safe_metadata or {},
                )
                for r in rows
            ]

    def clear_for_testing(self) -> None:
        """Clear quarantine records for test isolation."""
        with self._lock:
            with self._session_factory() as db:
                try:
                    db.query(QuarantinedAuditBatch).delete()
                    db.commit()
                except Exception:
                    db.rollback()


quarantine_store = QuarantineStore()
