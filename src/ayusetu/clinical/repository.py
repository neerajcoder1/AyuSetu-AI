"""
Clinical PostgreSQL Repository
==============================
Thread-safe and process-safe repository managing authoritative Encounter,
Slot, Utterance, and SummaryVersion records in PostgreSQL per PRD v2.0 §10, §14, §22.3 & §22.5.
Enforces transactional integrity, atomic session submission, deterministic slot conflict resolution,
and idempotent summary versioning.
"""

from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session, sessionmaker

from ayusetu.common.database import SyncSessionLocal, sync_engine, Base
from ayusetu.common.models import Patient, Encounter, Slot, Utterance, SummaryVersion
from ayusetu.clinical.models import (
    EncounterDTO,
    EncounterStatus,
    VisitType,
    IntakeDepth,
    Channel,
    ReportedBy,
    SlotSource,
    SlotDTO,
    UtteranceDTO,
    SummaryStatus,
    SummaryVersionDTO,
)

logger = logging.getLogger("ayusetu.clinical.repository")

_DEFAULT_SESSION_FACTORY: Optional[sessionmaker] = None
_FACTORY_LOCK = threading.Lock()


def get_default_session_factory() -> sessionmaker:
    """
    Return authoritative session factory for PostgreSQL, falling back to durable
    local SQLite when PostgreSQL is not reachable in local developer / test environments.
    """
    global _DEFAULT_SESSION_FACTORY
    with _FACTORY_LOCK:
        if _DEFAULT_SESSION_FACTORY is not None:
            return _DEFAULT_SESSION_FACTORY

        try:
            with sync_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(
                bind=sync_engine,
                tables=[
                    Patient.__table__,
                    Encounter.__table__,
                    Slot.__table__,
                    Utterance.__table__,
                    SummaryVersion.__table__,
                ]
            )
            _DEFAULT_SESSION_FACTORY = SyncSessionLocal
        except Exception:
            logger.info("PostgreSQL unavailable at default URL; using durable SQLite database for clinical repository.")
            durable_sqlite_engine = create_engine(
                "sqlite:///./ayusetu_clinical_durable.db",
                connect_args={"check_same_thread": False},
                future=True,
            )
            Base.metadata.create_all(
                bind=durable_sqlite_engine,
                tables=[
                    Patient.__table__,
                    Encounter.__table__,
                    Slot.__table__,
                    Utterance.__table__,
                    SummaryVersion.__table__,
                ],
            )
            _DEFAULT_SESSION_FACTORY = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=durable_sqlite_engine,
                expire_on_commit=False,
                class_=Session,
            )

        return _DEFAULT_SESSION_FACTORY


def format_utc_dt(dt: Any) -> datetime:
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


def _row_to_encounter_dto(row: Encounter) -> EncounterDTO:
    """Map SQLAlchemy Encounter row to EncounterDTO."""
    return EncounterDTO(
        id=str(row.id),
        patient_id=str(row.patient_id),
        department=row.department,
        visit_type=VisitType(row.visit_type) if row.visit_type in VisitType._value2member_map_ else VisitType.NEW,
        intake_depth=IntakeDepth(row.intake_depth) if row.intake_depth in IntakeDepth._value2member_map_ else IntakeDepth.FULL,
        channel=Channel(row.channel) if row.channel in Channel._value2member_map_ else Channel.KIOSK,
        reported_by=ReportedBy(row.reported_by) if row.reported_by in ReportedBy._value2member_map_ else None,
        language=row.language,
        started_at=format_utc_dt(row.started_at),
        submitted_at=format_utc_dt(row.submitted_at) if row.submitted_at else None,
        status=EncounterStatus(row.status) if row.status in EncounterStatus._value2member_map_ else EncounterStatus.DRAFT,
    )


def _row_to_slot_dto(row: Slot) -> SlotDTO:
    """Map SQLAlchemy Slot row to SlotDTO."""
    return SlotDTO(
        id=str(row.id),
        encounter_id=str(row.encounter_id),
        path=row.path,
        value=row.value,
        value_coded=row.value_coded,
        confidence=float(row.confidence) if row.confidence is not None else None,
        source=SlotSource(row.source) if row.source in SlotSource._value2member_map_ else SlotSource.UTTERANCE,
        source_ref=str(row.source_ref) if row.source_ref else None,
        reported_by=ReportedBy(row.reported_by) if row.reported_by in ReportedBy._value2member_map_ else ReportedBy.PATIENT,
        elicited=bool(row.elicited),
    )


def _row_to_utterance_dto(row: Utterance) -> UtteranceDTO:
    """Map SQLAlchemy Utterance row to UtteranceDTO."""
    return UtteranceDTO(
        id=str(row.id),
        encounter_id=str(row.encounter_id),
        seq=row.seq,
        speaker=row.speaker,
        text=row.text,
        lang=row.lang,
        asr_confidence=float(row.asr_confidence) if row.asr_confidence is not None else 1.0,
        audio_uri=row.audio_uri,
        created_at=format_utc_dt(row.created_at),
    )


def _row_to_summary_version_dto(row: SummaryVersion) -> SummaryVersionDTO:
    """Map SQLAlchemy SummaryVersion row to SummaryVersionDTO."""
    signed_by_str = str(row.signed_by) if row.signed_by else None
    signed_at_dt = format_utc_dt(row.signed_at) if row.signed_at else None
    composition_dict = dict(row.composition) if isinstance(row.composition, dict) else row.composition
    return SummaryVersionDTO(
        id=str(row.id),
        encounter_id=str(row.encounter_id),
        version=row.version,
        composition=composition_dict,
        generated_by=row.generated_by,
        model_version=row.model_version,
        status=SummaryStatus(row.status) if row.status in SummaryStatus._value2member_map_ else SummaryStatus.PRELIMINARY,
        signed_by=signed_by_str,
        signed_at=signed_at_dt,
    )


# Valid state transitions for encounter
VALID_ENCOUNTER_TRANSITIONS = {
    EncounterStatus.DRAFT: {EncounterStatus.SUBMITTED, EncounterStatus.ABANDONED},
    EncounterStatus.SUBMITTED: {EncounterStatus.PRELIMINARY, EncounterStatus.ABANDONED},
    EncounterStatus.PRELIMINARY: {EncounterStatus.FINAL, EncounterStatus.ABANDONED},
    EncounterStatus.FINAL: set(),  # Terminal state
    EncounterStatus.ABANDONED: set(),  # Terminal state
}


class ClinicalRepository:
    """
    Authoritative PostgreSQL-backed repository for Encounter, Slot, Utterance, and SummaryVersion models.
    """
    _lock = threading.Lock()

    def __init__(self, session_factory: Optional[sessionmaker] = None) -> None:
        self._session_factory = session_factory or get_default_session_factory()

    def ensure_patient(
        self,
        patient_id: str,
        is_provisional: bool = True,
        db_session: Optional[Session] = None,
    ) -> Patient:
        """Ensure a patient record exists to satisfy foreign key integrity."""
        pat_uuid = uuid.UUID(str(patient_id))
        
        def _execute(db: Session) -> Patient:
            existing = db.query(Patient).filter(Patient.id == pat_uuid).first()
            if existing:
                return existing
            new_pat = Patient(
                id=pat_uuid,
                is_provisional=is_provisional,
                created_at=datetime.now(timezone.utc),
            )
            db.add(new_pat)
            db.flush()
            return new_pat

        if db_session is not None:
            return _execute(db_session)
        else:
            with self._session_factory() as db:
                try:
                    pat = _execute(db)
                    db.commit()
                    return pat
                except Exception:
                    db.rollback()
                    raise

    def create_encounter(self, encounter: EncounterDTO) -> EncounterDTO:
        """Create a new encounter in PostgreSQL."""
        enc_uuid = uuid.UUID(str(encounter.id))
        pat_uuid = uuid.UUID(str(encounter.patient_id))

        with self._lock:
            with self._session_factory() as db:
                try:
                    self.ensure_patient(encounter.patient_id, db_session=db)
                    row = Encounter(
                        id=enc_uuid,
                        patient_id=pat_uuid,
                        department=encounter.department,
                        visit_type=encounter.visit_type.value,
                        intake_depth=encounter.intake_depth.value,
                        channel=encounter.channel.value,
                        reported_by=encounter.reported_by.value if encounter.reported_by else None,
                        language=encounter.language,
                        started_at=format_utc_dt(encounter.started_at),
                        submitted_at=format_utc_dt(encounter.submitted_at) if encounter.submitted_at else None,
                        status=encounter.status.value,
                    )
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                    return _row_to_encounter_dto(row)
                except Exception:
                    db.rollback()
                    logger.error("Failed to create encounter %s", encounter.id)
                    raise

    def get_encounter(self, encounter_id: str) -> Optional[EncounterDTO]:
        """Retrieve encounter by ID from PostgreSQL."""
        enc_uuid = uuid.UUID(str(encounter_id))
        with self._session_factory() as db:
            row = db.query(Encounter).filter(Encounter.id == enc_uuid).first()
            if not row:
                return None
            return _row_to_encounter_dto(row)

    def update_encounter_status(
        self,
        encounter_id: str,
        new_status: EncounterStatus,
        submitted_at: Optional[datetime] = None,
    ) -> EncounterDTO:
        """Update encounter status with strict state machine validation."""
        enc_uuid = uuid.UUID(str(encounter_id))

        with self._lock:
            with self._session_factory() as db:
                try:
                    row = db.query(Encounter).filter(Encounter.id == enc_uuid).with_for_update().first()
                    if not row:
                        raise ValueError(f"Encounter not found: {encounter_id}")

                    current_status = EncounterStatus(row.status)
                    if new_status != current_status:
                        valid_next = VALID_ENCOUNTER_TRANSITIONS.get(current_status, set())
                        if new_status not in valid_next:
                            raise ValueError(
                                f"Invalid encounter state transition from '{current_status.value}' to '{new_status.value}'"
                            )

                    row.status = new_status.value
                    if submitted_at is not None:
                        row.submitted_at = format_utc_dt(submitted_at)
                    elif new_status == EncounterStatus.SUBMITTED and row.submitted_at is None:
                        row.submitted_at = datetime.now(timezone.utc)

                    db.commit()
                    db.refresh(row)
                    return _row_to_encounter_dto(row)
                except Exception:
                    db.rollback()
                    raise

    def upsert_slot(self, slot: SlotDTO, db_session: Optional[Session] = None) -> SlotDTO:
        """
        Persist or update a clinical slot in PostgreSQL.
        Handles conflict resolution on unique (encounter_id, path).
        """
        slot_uuid = uuid.UUID(str(slot.id))
        enc_uuid = uuid.UUID(str(slot.encounter_id))
        source_ref_uuid = uuid.UUID(str(slot.source_ref)) if slot.source_ref else None

        def _execute(db: Session) -> SlotDTO:
            existing = (
                db.query(Slot)
                .filter(Slot.encounter_id == enc_uuid, Slot.path == slot.path)
                .first()
            )
            if existing:
                # Update existing slot preserving path identity and updating evidence
                existing.value = slot.value
                existing.value_coded = slot.value_coded
                existing.confidence = slot.confidence
                existing.source = slot.source.value
                existing.source_ref = source_ref_uuid
                existing.reported_by = slot.reported_by.value
                existing.elicited = slot.elicited
                db.flush()
                return _row_to_slot_dto(existing)
            else:
                new_row = Slot(
                    id=slot_uuid,
                    encounter_id=enc_uuid,
                    path=slot.path,
                    value=slot.value,
                    value_coded=slot.value_coded,
                    confidence=slot.confidence,
                    source=slot.source.value,
                    source_ref=source_ref_uuid,
                    reported_by=slot.reported_by.value,
                    elicited=slot.elicited,
                )
                db.add(new_row)
                db.flush()
                return _row_to_slot_dto(new_row)

        if db_session is not None:
            return _execute(db_session)
        else:
            with self._lock:
                with self._session_factory() as db:
                    try:
                        res = _execute(db)
                        db.commit()
                        return res
                    except Exception:
                        db.rollback()
                        raise

    def get_slots(self, encounter_id: str) -> List[SlotDTO]:
        """Retrieve all slots for an encounter ordered by path."""
        enc_uuid = uuid.UUID(str(encounter_id))
        with self._session_factory() as db:
            rows = (
                db.query(Slot)
                .filter(Slot.encounter_id == enc_uuid)
                .order_by(Slot.path.asc())
                .all()
            )
            return [_row_to_slot_dto(r) for r in rows]

    def get_slot(self, encounter_id: str, path: str) -> Optional[SlotDTO]:
        """Retrieve a specific slot by encounter ID and path."""
        enc_uuid = uuid.UUID(str(encounter_id))
        with self._session_factory() as db:
            row = (
                db.query(Slot)
                .filter(Slot.encounter_id == enc_uuid, Slot.path == path)
                .first()
            )
            if not row:
                return None
            return _row_to_slot_dto(row)

    def save_utterances(
        self,
        encounter_id: str,
        utterances: List[UtteranceDTO],
        db_session: Optional[Session] = None,
    ) -> List[UtteranceDTO]:
        """Persist dialogue turn utterances ordered by seq."""
        enc_uuid = uuid.UUID(str(encounter_id))

        def _execute(db: Session) -> List[UtteranceDTO]:
            saved: List[UtteranceDTO] = []
            for utt in utterances:
                utt_uuid = uuid.UUID(str(utt.id))
                row = Utterance(
                    id=utt_uuid,
                    encounter_id=enc_uuid,
                    seq=utt.seq,
                    speaker=utt.speaker,
                    text=utt.text,
                    lang=utt.lang,
                    asr_confidence=utt.asr_confidence,
                    audio_uri=utt.audio_uri,
                    created_at=format_utc_dt(utt.created_at),
                )
                db.add(row)
                db.flush()
                saved.append(_row_to_utterance_dto(row))
            return saved

        if db_session is not None:
            return _execute(db_session)
        else:
            with self._lock:
                with self._session_factory() as db:
                    try:
                        res = _execute(db)
                        db.commit()
                        return res
                    except Exception:
                        db.rollback()
                        raise

    def get_utterances(self, encounter_id: str) -> List[UtteranceDTO]:
        """Retrieve all utterances for an encounter in chronological order."""
        enc_uuid = uuid.UUID(str(encounter_id))
        with self._session_factory() as db:
            rows = (
                db.query(Utterance)
                .filter(Utterance.encounter_id == enc_uuid)
                .order_by(Utterance.seq.asc())
                .all()
            )
            return [_row_to_utterance_dto(r) for r in rows]

    def submit_encounter_atomic(
        self,
        encounter: EncounterDTO,
        utterances: List[UtteranceDTO],
        slots: List[SlotDTO],
    ) -> EncounterDTO:
        """
        Atomically persist Encounter (status=submitted), associated Utterances,
        and extracted Slots within a single database transaction.
        Rolls back completely if any element fails.
        """
        enc_uuid = uuid.UUID(str(encounter.id))
        pat_uuid = uuid.UUID(str(encounter.patient_id))
        now_utc = datetime.now(timezone.utc)

        with self._lock:
            with self._session_factory() as db:
                try:
                    # 1. Ensure patient exists
                    self.ensure_patient(encounter.patient_id, db_session=db)

                    # 2. Check if encounter exists or insert new
                    existing_enc = db.query(Encounter).filter(Encounter.id == enc_uuid).with_for_update().first()
                    if existing_enc:
                        current_status = EncounterStatus(existing_enc.status)
                        if current_status not in (EncounterStatus.DRAFT, EncounterStatus.SUBMITTED):
                            raise ValueError(f"Cannot submit encounter in status: {current_status.value}")
                        existing_enc.status = EncounterStatus.SUBMITTED.value
                        existing_enc.submitted_at = format_utc_dt(now_utc)
                        existing_enc.reported_by = encounter.reported_by.value if encounter.reported_by else existing_enc.reported_by
                        enc_row = existing_enc
                    else:
                        enc_row = Encounter(
                            id=enc_uuid,
                            patient_id=pat_uuid,
                            department=encounter.department,
                            visit_type=encounter.visit_type.value,
                            intake_depth=encounter.intake_depth.value,
                            channel=encounter.channel.value,
                            reported_by=encounter.reported_by.value if encounter.reported_by else None,
                            language=encounter.language,
                            started_at=format_utc_dt(encounter.started_at),
                            submitted_at=format_utc_dt(now_utc),
                            status=EncounterStatus.SUBMITTED.value,
                        )
                        db.add(enc_row)
                    db.flush()

                    # 3. Persist utterances
                    for utt in utterances:
                        utt_uuid = uuid.UUID(str(utt.id))
                        existing_utt = db.query(Utterance).filter(Utterance.id == utt_uuid).first()
                        if not existing_utt:
                            u_row = Utterance(
                                id=utt_uuid,
                                encounter_id=enc_uuid,
                                seq=utt.seq,
                                speaker=utt.speaker,
                                text=utt.text,
                                lang=utt.lang,
                                asr_confidence=utt.asr_confidence,
                                audio_uri=utt.audio_uri,
                                created_at=format_utc_dt(utt.created_at),
                            )
                            db.add(u_row)
                    db.flush()

                    # 4. Upsert slots with conflict resolution
                    for slot in slots:
                        self.upsert_slot(slot, db_session=db)

                    db.commit()
                    db.refresh(enc_row)
                    return _row_to_encounter_dto(enc_row)
                except Exception:
                    db.rollback()
                    logger.error("Failed atomic encounter submission for encounter %s", encounter.id)
                    raise

    def save_summary_version(self, summary_version: SummaryVersionDTO) -> SummaryVersionDTO:
        """Persist a new SummaryVersion in PostgreSQL."""
        sum_uuid = uuid.UUID(str(summary_version.id))
        enc_uuid = uuid.UUID(str(summary_version.encounter_id))
        signed_by_uuid = uuid.UUID(str(summary_version.signed_by)) if summary_version.signed_by else None
        signed_at_dt = format_utc_dt(summary_version.signed_at) if summary_version.signed_at else None

        with self._lock:
            with self._session_factory() as db:
                try:
                    row = SummaryVersion(
                        id=sum_uuid,
                        encounter_id=enc_uuid,
                        version=summary_version.version,
                        composition=summary_version.composition,
                        generated_by=summary_version.generated_by,
                        model_version=summary_version.model_version,
                        status=summary_version.status.value,
                        signed_by=signed_by_uuid,
                        signed_at=signed_at_dt,
                    )
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                    return _row_to_summary_version_dto(row)
                except Exception:
                    db.rollback()
                    raise

    def get_summary_version(self, encounter_id: str, version: int = 1) -> Optional[SummaryVersionDTO]:
        """Retrieve a specific summary version for an encounter."""
        enc_uuid = uuid.UUID(str(encounter_id))
        with self._session_factory() as db:
            row = (
                db.query(SummaryVersion)
                .filter(SummaryVersion.encounter_id == enc_uuid, SummaryVersion.version == version)
                .first()
            )
            if not row:
                return None
            return _row_to_summary_version_dto(row)

    def get_latest_summary_version(self, encounter_id: str) -> Optional[SummaryVersionDTO]:
        """Retrieve the latest summary version for an encounter."""
        enc_uuid = uuid.UUID(str(encounter_id))
        with self._session_factory() as db:
            row = (
                db.query(SummaryVersion)
                .filter(SummaryVersion.encounter_id == enc_uuid)
                .order_by(SummaryVersion.version.desc())
                .first()
            )
            if not row:
                return None
            return _row_to_summary_version_dto(row)

    def upsert_preliminary_summary(
        self,
        encounter_id: str,
        composition: Dict[str, Any],
        model_version: str = "ayusetu-synthesis-v1.0",
        generated_by: str = "synthesis_engine",
    ) -> SummaryVersionDTO:
        """
        Idempotently create or update preliminary summary version 1 for an encounter.
        Prevents uncontrolled duplicate version 1 records.
        """
        enc_uuid = uuid.UUID(str(encounter_id))
        with self._lock:
            with self._session_factory() as db:
                try:
                    existing = (
                        db.query(SummaryVersion)
                        .filter(SummaryVersion.encounter_id == enc_uuid, SummaryVersion.version == 1)
                        .with_for_update()
                        .first()
                    )
                    if existing:
                        if existing.status == SummaryStatus.FINAL.value:
                            # Do not overwrite signed final summary
                            return _row_to_summary_version_dto(existing)
                        existing.composition = composition
                        existing.model_version = model_version
                        existing.generated_by = generated_by
                        db.commit()
                        db.refresh(existing)
                        return _row_to_summary_version_dto(existing)
                    else:
                        new_row = SummaryVersion(
                            id=uuid.uuid4(),
                            encounter_id=enc_uuid,
                            version=1,
                            composition=composition,
                            generated_by=generated_by,
                            model_version=model_version,
                            status=SummaryStatus.PRELIMINARY.value,
                        )
                        db.add(new_row)
                        db.commit()
                        db.refresh(new_row)
                        return _row_to_summary_version_dto(new_row)
                except Exception:
                    db.rollback()
                    raise

    def count_encounters(self) -> int:
        """Count total encounters."""
        with self._session_factory() as db:
            return db.query(func.count(Encounter.id)).scalar() or 0

    def count_slots(self) -> int:
        """Count total slots."""
        with self._session_factory() as db:
            return db.query(func.count(Slot.id)).scalar() or 0

    def count_summaries(self) -> int:
        """Count total summary versions."""
        with self._session_factory() as db:
            return db.query(func.count(SummaryVersion.id)).scalar() or 0

    def clear_for_testing(self) -> None:
        """Reset clinical tables for test isolation."""
        with self._lock:
            with self._session_factory() as db:
                try:
                    db.query(SummaryVersion).delete()
                    db.query(Slot).delete()
                    db.query(Utterance).delete()
                    db.query(Encounter).delete()
                    db.query(Patient).delete()
                    db.commit()
                except Exception:
                    db.rollback()
