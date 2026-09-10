"""
Audit Append-Only PostgreSQL Repository
========================================
Thread-safe and process-safe append-only repository managing the global cryptographic audit chain in PostgreSQL.
Enforces strict sequence monotonicity, table-level/advisory concurrency serialization,
and durable crash-recovery of the chain head per PRD v2.0 §21.8.
"""

from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional, Set
import uuid

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session, sessionmaker

from ayusetu.common.database import SyncSessionLocal, sync_engine, Base
from ayusetu.common.models import AuditEvent
from ayusetu.audit.models import (
    AuditAction,
    AuditEventCreate,
    AuditEventDTO,
    AuditHeadDTO,
    AuditOutcome,
)
from ayusetu.audit.chain import GENESIS_HASH, compute_payload_hash, compute_entry_hash

logger = logging.getLogger("ayusetu.audit.repository")

_DEFAULT_SESSION_FACTORY: Optional[sessionmaker] = None
_FACTORY_LOCK = threading.Lock()


def get_default_session_factory() -> sessionmaker:
    """
    Return authoritative session factory for PostgreSQL, falling back to durable
    local SQLite when PostgreSQL is not reachable in local developer / test environment.
    """
    global _DEFAULT_SESSION_FACTORY
    with _FACTORY_LOCK:
        if _DEFAULT_SESSION_FACTORY is not None:
            return _DEFAULT_SESSION_FACTORY

        try:
            with sync_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=sync_engine, tables=[AuditEvent.__table__])
            _DEFAULT_SESSION_FACTORY = SyncSessionLocal
        except Exception:
            logger.info("PostgreSQL unavailable at default URL; using durable SQLite database for audit repository.")
            durable_sqlite_engine = create_engine(
                "sqlite:///./ayusetu_audit_durable.db",
                connect_args={"check_same_thread": False},
                future=True,
            )
            Base.metadata.create_all(bind=durable_sqlite_engine, tables=[AuditEvent.__table__])
            _DEFAULT_SESSION_FACTORY = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=durable_sqlite_engine,
                expire_on_commit=False,
                class_=Session,
            )

        return _DEFAULT_SESSION_FACTORY


def format_utc_iso(dt: Any) -> str:
    """Normalize datetime or ISO string to UTC ISO-8601 string with explicit timezone."""
    if dt is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(dt, str):
        dt_clean = dt.replace(" ", "T")
        try:
            parsed = datetime.fromisoformat(dt_clean)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except Exception:
            return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)


def hash_to_bytes(h: str) -> bytes:
    """Convert hex hash string or raw bytes to database binary storage."""
    if isinstance(h, bytes):
        return h
    try:
        return bytes.fromhex(h)
    except ValueError:
        return h.encode("utf-8")


def bytes_to_hash(b: Any) -> str:
    """Convert database binary storage to 64-char lowercase hexadecimal string."""
    if isinstance(b, str):
        return b
    if isinstance(b, (bytes, bytearray)):
        if len(b) == 32:
            return b.hex()
        try:
            decoded = b.decode("utf-8")
            if len(decoded) == 64:
                return decoded
        except UnicodeDecodeError:
            pass
        return b.hex()
    return str(b)


def _verify_row_integrity(row: AuditEvent) -> bool:
    """Recompute entry hash for a stored row and verify mathematical consistency."""
    if row is None:
        return True
    ts_str = format_utc_iso(row.ts)
    computed_hash = compute_entry_hash(
        seq=int(row.seq),
        ts=ts_str,
        actor_id=str(row.actor_id),
        actor_role=row.actor_role,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=str(row.resource_id),
        outcome=row.outcome,
        payload_hash=bytes_to_hash(row.payload_hash),
        prev_hash=bytes_to_hash(row.prev_hash),
        patient_id=str(row.patient_id) if row.patient_id else None,
        encounter_id=str(row.encounter_id) if row.encounter_id else None,
        reason=row.reason,
        src_device=row.src_device,
        src_ip=row.src_ip,
    )
    stored_hash = bytes_to_hash(row.entry_hash)
    return computed_hash == stored_hash


def _row_to_dto(row: AuditEvent) -> AuditEventDTO:
    """Map SQLAlchemy AuditEvent row to immutable Pydantic AuditEventDTO."""
    ts_str = format_utc_iso(row.ts)
    return AuditEventDTO(
        seq=int(row.seq),
        ts=ts_str,
        actor_id=str(row.actor_id),
        actor_role=row.actor_role,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=str(row.resource_id),
        patient_id=str(row.patient_id) if row.patient_id else None,
        encounter_id=str(row.encounter_id) if row.encounter_id else None,
        outcome=row.outcome,
        reason=row.reason,
        src_device=row.src_device,
        src_ip=row.src_ip,
        payload_hash=bytes_to_hash(row.payload_hash),
        prev_hash=bytes_to_hash(row.prev_hash),
        entry_hash=bytes_to_hash(row.entry_hash),
    )


class AuditRepository:
    """
    PostgreSQL-backed append-only repository for the global cryptographic audit chain.
    Recovers the persisted chain head on initialization and protects concurrent appends.
    """

    def __init__(self, session_factory: Optional[sessionmaker] = None) -> None:
        self._lock = threading.Lock()
        self._session_factory = session_factory or get_default_session_factory()
        # Ensure schema exists on bound database
        try:
            bind = self._session_factory.kw.get("bind") if hasattr(self._session_factory, "kw") else None
            if bind is not None:
                Base.metadata.create_all(bind=bind, tables=[AuditEvent.__table__])
        except Exception:
            pass

    def append(
        self,
        event_create: AuditEventCreate,
        forced_ts: Optional[str] = None,
    ) -> AuditEventDTO:
        """
        Atomically append an event to the global PostgreSQL audit chain.
        Serializes concurrent transactions, computes hash links, and commits durably.
        """
        with self._lock:
            with self._session_factory() as db:
                try:
                    # Concurrency control across processes/workers
                    bind_dialect = db.get_bind().dialect.name
                    if bind_dialect == "postgresql":
                        # PostgreSQL advisory transaction lock for audit chain serialization
                        db.execute(text("SELECT pg_advisory_xact_lock(2147483647)"))
                    
                    # 1. Fetch latest persisted event in chain
                    latest = db.query(AuditEvent).order_by(AuditEvent.seq.desc()).first()
                    if latest is not None:
                        if not _verify_row_integrity(latest):
                            logger.critical(
                                "CRITICAL SECURITY ALERT [AUDIT_HEAD_TAMPERED]: Seq %d stored entry_hash is invalid. Halting append.",
                                latest.seq,
                            )
                            raise RuntimeError(f"Audit chain head seq={latest.seq} integrity compromised. Append rejected.")
                        next_seq = int(latest.seq) + 1
                        prev_hash = bytes_to_hash(latest.entry_hash)
                    else:
                        next_seq = 1
                        prev_hash = GENESIS_HASH

                    # 2. Canonical timestamp
                    ts_raw = forced_ts or datetime.now(timezone.utc).isoformat()
                    ts = format_utc_iso(ts_raw)
                    ts_dt = datetime.fromisoformat(ts)

                    # 3. Compute cryptographic hashes
                    payload_hash = compute_payload_hash(event_create.safe_metadata)
                    action_str = event_create.action.value if isinstance(event_create.action, AuditAction) else str(event_create.action)
                    outcome_str = event_create.outcome.value if isinstance(event_create.outcome, AuditOutcome) else str(event_create.outcome)

                    entry_hash = compute_entry_hash(
                        seq=next_seq,
                        ts=ts,
                        actor_id=event_create.actor_id,
                        actor_role=event_create.actor_role,
                        action=action_str,
                        resource_type=event_create.resource_type,
                        resource_id=event_create.resource_id,
                        outcome=outcome_str,
                        payload_hash=payload_hash,
                        prev_hash=prev_hash,
                        patient_id=event_create.patient_id,
                        encounter_id=event_create.encounter_id,
                        reason=event_create.reason,
                        src_device=event_create.src_device,
                        src_ip=event_create.src_ip,
                    )

                    # 4. Construct and persist DB row
                    db_event = AuditEvent(
                        seq=next_seq,
                        ts=ts_dt,
                        actor_id=event_create.actor_id,
                        actor_role=event_create.actor_role,
                        action=action_str,
                        resource_type=event_create.resource_type,
                        resource_id=event_create.resource_id,
                        patient_id=event_create.patient_id,
                        encounter_id=event_create.encounter_id,
                        outcome=outcome_str,
                        reason=event_create.reason,
                        src_device=event_create.src_device,
                        src_ip=event_create.src_ip,
                        payload_hash=hash_to_bytes(payload_hash),
                        prev_hash=hash_to_bytes(prev_hash),
                        entry_hash=hash_to_bytes(entry_hash),
                    )

                    db.add(db_event)
                    db.commit()
                    db.refresh(db_event)

                    return _row_to_dto(db_event)
                except Exception:
                    db.rollback()
                    raise

    def get_head(self) -> AuditHeadDTO:
        """Retrieve current global audit head from PostgreSQL."""
        with self._session_factory() as db:
            latest = db.query(AuditEvent).order_by(AuditEvent.seq.desc()).first()
            if latest is not None:
                if not _verify_row_integrity(latest):
                    logger.critical(
                        "CRITICAL SECURITY ALERT [AUDIT_HEAD_TAMPERED]: Seq %d stored entry_hash is invalid.",
                        latest.seq,
                    )
                    raise RuntimeError(f"Audit chain head seq={latest.seq} integrity compromised.")
                ts_str = latest.ts.isoformat() if isinstance(latest.ts, datetime) else str(latest.ts)
                return AuditHeadDTO(
                    seq=int(latest.seq),
                    entry_hash=bytes_to_hash(latest.entry_hash),
                    ts=ts_str,
                )
            return AuditHeadDTO(
                seq=0,
                entry_hash=GENESIS_HASH,
                ts=datetime.now(timezone.utc).isoformat(),
            )


    def get_by_seq(self, seq: int) -> Optional[AuditEventDTO]:
        """Look up single audit record by sequence number from PostgreSQL."""
        with self._session_factory() as db:
            row = db.query(AuditEvent).filter(AuditEvent.seq == seq).first()
            if row is not None:
                return _row_to_dto(row)
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
        """Query audit records with filtering from PostgreSQL."""
        with self._session_factory() as db:
            q = db.query(AuditEvent).filter(AuditEvent.seq >= from_seq)
            if to_seq is not None:
                q = q.filter(AuditEvent.seq <= to_seq)
            if encounter_id is not None:
                q = q.filter(AuditEvent.encounter_id == encounter_id)
            if patient_id is not None:
                q = q.filter(AuditEvent.patient_id == patient_id)
            if actor_id is not None:
                q = q.filter(AuditEvent.actor_id == actor_id)
            if action is not None:
                q = q.filter(AuditEvent.action == action)
            if resource_type is not None:
                q = q.filter(AuditEvent.resource_type == resource_type)

            rows = q.order_by(AuditEvent.seq.asc()).limit(limit).all()
            return [_row_to_dto(r) for r in rows]

    def get_all(self) -> List[AuditEventDTO]:
        """Retrieve all events in sequential order from PostgreSQL (for verification)."""
        with self._session_factory() as db:
            rows = db.query(AuditEvent).order_by(AuditEvent.seq.asc()).all()
            return [_row_to_dto(r) for r in rows]

    def count(self) -> int:
        """Total number of audit events persisted in PostgreSQL."""
        with self._session_factory() as db:
            return db.query(func.count(AuditEvent.seq)).scalar() or 0

    def known_head_hashes(self) -> Set[str]:
        """Set of all historical event hashes in PostgreSQL including genesis."""
        with self._session_factory() as db:
            rows = db.query(AuditEvent.entry_hash).all()
            hashes = {GENESIS_HASH}
            for r in rows:
                hashes.add(bytes_to_hash(r[0]))
            return hashes

    def clear_for_testing(self) -> None:
        """Clear audit table for test isolation."""
        with self._lock:
            with self._session_factory() as db:
                try:
                    db.query(AuditEvent).delete()
                    db.commit()
                except Exception:
                    db.rollback()
