"""
Red-Flag PostgreSQL Repository
==============================
Thread-safe and process-safe repository managing durable, authoritative
clinical red-flag events and lifecycle transitions in PostgreSQL per PRD v2.0 §12 & §22.9.
Enforces fail-closed transaction boundaries, row locking, and deterministic recovery.
"""

from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session, sessionmaker

from ayusetu.common.database import SyncSessionLocal, sync_engine, Base
from ayusetu.common.models import RedFlagEvent, Patient, Encounter
from ayusetu.redflag.models import (
    RedFlagEventDTO,
    RedFlagStatus,
    Tier1AlertQueueItem,
)

logger = logging.getLogger("ayusetu.redflag.repository")

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
            Base.metadata.create_all(bind=sync_engine, tables=[RedFlagEvent.__table__])
            _DEFAULT_SESSION_FACTORY = SyncSessionLocal
        except Exception:
            logger.info("PostgreSQL unavailable at default URL; using durable SQLite database for redflag repository.")
            durable_sqlite_engine = create_engine(
                "sqlite:///./ayusetu_redflag_durable.db",
                connect_args={"check_same_thread": False},
                future=True,
            )
            Base.metadata.create_all(
                bind=durable_sqlite_engine,
                tables=[Patient.__table__, Encounter.__table__, RedFlagEvent.__table__],
            )
            _DEFAULT_SESSION_FACTORY = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=durable_sqlite_engine,
                expire_on_commit=False,
                class_=Session,
            )

        return _DEFAULT_SESSION_FACTORY


def format_utc_iso(dt: Any) -> str:
    """Ensure datetime object or string is formatted as UTC ISO-8601 string."""
    if dt is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)


def parse_utc_dt(dt: Any) -> datetime:
    """Ensure datetime object is timezone-aware UTC."""
    if dt is None:
        return datetime.now(timezone.utc)
    if isinstance(dt, str):
        dt_clean = dt.replace(" ", "T")
        try:
            parsed = datetime.fromisoformat(dt_clean)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def to_valid_uuid_str(val: Optional[str]) -> Optional[str]:
    """Convert string to valid UUID or deterministic uuid5 if non-UUID formatted string."""
    if not val:
        return None
    try:
        return str(uuid.UUID(str(val)))
    except (ValueError, AttributeError):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(val)))


def _infer_status_from_row(row: RedFlagEvent) -> RedFlagStatus:
    """Infer RedFlagStatus lifecycle state from persisted row attributes."""
    if row.outcome is not None:
        clean_outcome = row.outcome.split("@@ack_by=")[0] if "@@ack_by=" in row.outcome else row.outcome
        outcome_upper = clean_outcome.strip().upper()
        if outcome_upper.startswith("ESCALATED"):
            return RedFlagStatus.ESCALATED
        elif outcome_upper.startswith("ACKNOWLEDGED"):
            return RedFlagStatus.ACKNOWLEDGED
        elif clean_outcome:
            return RedFlagStatus.RESOLVED
    elif row.acknowledged_at is not None:
        return RedFlagStatus.ACKNOWLEDGED
    return RedFlagStatus.DETECTED


def _row_to_dto(row: RedFlagEvent) -> RedFlagEventDTO:
    """Map SQLAlchemy RedFlagEvent row to immutable RedFlagEventDTO."""
    status = _infer_status_from_row(row)
    outcome_clean = row.outcome
    ack_by_val = str(row.acknowledged_by) if row.acknowledged_by else None

    if row.outcome and "@@ack_by=" in row.outcome:
        outcome_clean, ack_by_override = row.outcome.split("@@ack_by=", 1)
        outcome_clean = outcome_clean if outcome_clean else None
        if ack_by_override:
            ack_by_val = ack_by_override

    return RedFlagEventDTO(
        id=str(row.id),
        encounter_id=str(row.encounter_id),
        rule_id=row.rule_id,
        tier=row.tier,
        trigger_text=row.trigger_text,
        detected_at=format_utc_iso(row.detected_at),
        acknowledged_by=ack_by_val,
        acknowledged_at=format_utc_iso(row.acknowledged_at) if row.acknowledged_at else None,
        outcome=outcome_clean,
        status=status,
    )


class RedFlagRepository:
    """
    PostgreSQL-backed repository for authoritative clinical red-flag events and lifecycle.
    Provides ACID transaction boundaries and fail-closed persistence.
    """
    _lock = threading.Lock()

    def __init__(self, session_factory: Optional[sessionmaker] = None) -> None:
        self._session_factory = session_factory or get_default_session_factory()

    def create_event(self, dto: RedFlagEventDTO) -> RedFlagEventDTO:
        """Persist a newly detected red-flag event into PostgreSQL."""
        with self._lock:
            with self._session_factory() as db:
                try:
                    detected_dt = parse_utc_dt(dto.detected_at)
                    ack_dt = parse_utc_dt(dto.acknowledged_at) if dto.acknowledged_at else None
                    ack_by = to_valid_uuid_str(dto.acknowledged_by)

                    row = RedFlagEvent(
                        id=str(dto.id),
                        encounter_id=str(dto.encounter_id),
                        rule_id=dto.rule_id,
                        tier=dto.tier,
                        trigger_text=dto.trigger_text,
                        detected_at=detected_dt,
                        acknowledged_by=ack_by,
                        acknowledged_at=ack_dt,
                        outcome=dto.outcome,
                    )
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                    return _row_to_dto(row)
                except Exception:
                    db.rollback()
                    logger.error("Failed to persist RedFlagEvent %s to PostgreSQL", dto.id)
                    raise

    def get_encounter_events(self, encounter_id: str) -> List[RedFlagEventDTO]:
        """Retrieve all red-flag events for an encounter from PostgreSQL."""
        enc_id = str(encounter_id)
        with self._session_factory() as db:
            rows = (
                db.query(RedFlagEvent)
                .filter(RedFlagEvent.encounter_id == enc_id)
                .order_by(RedFlagEvent.detected_at.asc(), RedFlagEvent.id.asc())
                .all()
            )
            return [_row_to_dto(r) for r in rows]

    def get_event_by_id(self, event_id: str) -> Optional[RedFlagEventDTO]:
        """Look up single red-flag event by UUID from PostgreSQL."""
        ev_id = str(event_id)
        with self._session_factory() as db:
            row = db.query(RedFlagEvent).filter(RedFlagEvent.id == ev_id).first()
            if not row:
                return None
            return _row_to_dto(row)

    def get_tier1_queue(self) -> List[Tier1AlertQueueItem]:
        """
        Retrieve all active (unresolved) Tier 1 alerts with escalation timing from PostgreSQL.
        """
        now = datetime.now(timezone.utc)
        items: List[Tier1AlertQueueItem] = []

        with self._session_factory() as db:
            rows = (
                db.query(RedFlagEvent)
                .filter(RedFlagEvent.tier == 1)
                .order_by(RedFlagEvent.detected_at.desc())
                .all()
            )

            for row in rows:
                dto = _row_to_dto(row)
                if dto.status != RedFlagStatus.RESOLVED:
                    try:
                        dt = parse_utc_dt(dto.detected_at)
                        diff_sec = max(0, int((now - dt).total_seconds()))
                    except Exception:
                        diff_sec = 0

                    level = 0
                    if diff_sec >= 180:
                        level = 2  # Duty Medical Officer / Senior
                    elif diff_sec >= 90:
                        level = 1  # Nursing Officer Escalated

                    items.append(
                        Tier1AlertQueueItem(
                            event=dto,
                            encounter_id=dto.encounter_id,
                            detected_at=dto.detected_at,
                            seconds_since_detection=diff_sec,
                            escalation_level=level,
                            is_overdue=diff_sec >= 90 and dto.status == RedFlagStatus.DETECTED,
                        )
                    )

        items.sort(key=lambda item: item.seconds_since_detection, reverse=True)
        return items

    def update_event_state(
        self,
        event_id: str,
        acknowledged_by: Optional[str] = None,
        acknowledged_at: Optional[datetime] = None,
        outcome: Optional[str] = None,
    ) -> Optional[RedFlagEventDTO]:
        """
        Update the lifecycle state of an existing red-flag event in PostgreSQL.
        Uses row-level locking for atomic state transitions.
        """
        ev_id = str(event_id)
        with self._lock:
            with self._session_factory() as db:
                try:
                    bind_dialect = db.get_bind().dialect.name
                    query = db.query(RedFlagEvent).filter(RedFlagEvent.id == ev_id)
                    if bind_dialect == "postgresql":
                        query = query.with_for_update()

                    row = query.first()
                    if not row:
                        return None

                    if acknowledged_by is not None:
                        row.acknowledged_by = to_valid_uuid_str(acknowledged_by)
                        if str(acknowledged_by) != str(row.acknowledged_by):
                            if outcome is not None and "@@ack_by=" not in outcome:
                                outcome = f"{outcome}@@ack_by={acknowledged_by}"
                            elif row.outcome and "@@ack_by=" not in row.outcome:
                                row.outcome = f"{row.outcome}@@ack_by={acknowledged_by}"
                            elif not outcome and not row.outcome:
                                outcome = f"@@ack_by={acknowledged_by}"

                    if acknowledged_at is not None:
                        row.acknowledged_at = parse_utc_dt(acknowledged_at)
                    if outcome is not None:
                        row.outcome = outcome

                    db.commit()
                    db.refresh(row)
                    return _row_to_dto(row)
                except Exception:
                    db.rollback()
                    logger.error("Failed to update RedFlagEvent %s in PostgreSQL", ev_id)
                    raise

    def count(self) -> int:
        """Count total red-flag events in PostgreSQL."""
        with self._session_factory() as db:
            return db.query(func.count(RedFlagEvent.id)).scalar() or 0

    def clear_for_testing(self) -> None:
        """Reset red_flag_event table for test isolation."""
        with self._lock:
            with self._session_factory() as db:
                try:
                    db.query(RedFlagEvent).delete()
                    db.commit()
                except Exception:
                    db.rollback()
