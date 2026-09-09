"""
AyuSetu Relational Database Models
==================================
Authoritative PostgreSQL models per PRD v2.0 §22.3 and §21.8.
All timestamps are TIMESTAMPTZ (UTC) and identifiers are UUID v7 throughout.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

import uuid6
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    BigInteger,
    Numeric,
    Date,
    DateTime,
    LargeBinary,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.types import JSON, TypeDecorator, CHAR

from ayusetu.common.database import Base


def generate_uuid7() -> uuid.UUID:
    """Generate a time-ordered UUID v7."""
    return uuid6.uuid7()


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


# Cross-database UUID type support (Native Postgres UUID or String fallback for SQLite unit tests)
class UniversalUUID(TypeDecorator):
    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return str(value) if dialect.name != "postgresql" else value
        try:
            val_uuid = uuid.UUID(str(value))
            return val_uuid if dialect.name == "postgresql" else str(val_uuid)
        except (ValueError, AttributeError):
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return str(value)


# Cross-database JSONB / JSON type support
class UniversalJSONB(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class Patient(Base):
    __tablename__ = "patient"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    abha_id = Column(String, unique=True, nullable=True)
    mrn = Column(String, nullable=True)
    name_enc = Column(LargeBinary, nullable=True, comment="Field-encrypted, separate DEK")
    mobile_enc = Column(LargeBinary, nullable=True, comment="Field-encrypted, separate DEK")
    dob = Column(Date, nullable=True)
    sex = Column(String, nullable=True)
    district = Column(String, nullable=True)
    is_provisional = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    merged_into = Column(UniversalUUID, ForeignKey("patient.id"), nullable=True)

    __table_args__ = (
        CheckConstraint("sex IN ('male', 'female', 'other') OR sex IS NULL", name="chk_patient_sex"),
    )


class Encounter(Base):
    __tablename__ = "encounter"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    patient_id = Column(UniversalUUID, ForeignKey("patient.id"), nullable=False)
    department = Column(String, nullable=False)
    visit_type = Column(String, nullable=False)
    intake_depth = Column(String, nullable=False)
    channel = Column(String, nullable=False)
    reported_by = Column(String, nullable=True)
    language = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="draft")

    __table_args__ = (
        CheckConstraint("visit_type IN ('new', 'followup_stable', 'followup_new', 'walkin')", name="chk_encounter_visit_type"),
        CheckConstraint("intake_depth IN ('fast', 'interval', 'delta', 'full')", name="chk_encounter_intake_depth"),
        CheckConstraint("channel IN ('kiosk', 'pwa_self', 'pwa_companion', 'assisted')", name="chk_encounter_channel"),
        CheckConstraint("status IN ('draft', 'submitted', 'preliminary', 'final', 'abandoned')", name="chk_encounter_status"),
    )


class Slot(Base):
    """The ONLY origin of clinical facts in the medical record."""
    __tablename__ = "slot"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    encounter_id = Column(UniversalUUID, ForeignKey("encounter.id"), nullable=False)
    path = Column(String, nullable=False, comment="Ontology path, e.g. 'hpi.severity'")
    value = Column(UniversalJSONB, nullable=True)
    value_coded = Column(String, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=True)
    source = Column(String, nullable=False)
    source_ref = Column(UniversalUUID, nullable=True, comment="utterance id or document region id")
    reported_by = Column(String, nullable=False)
    elicited = Column(Boolean, default=True, nullable=False, comment="false => 'not elicited', never a negative")

    __table_args__ = (
        CheckConstraint("source IN ('utterance', 'touch', 'document', 'derived', 'clinician')", name="chk_slot_source"),
        CheckConstraint("reported_by IN ('patient', 'companion', 'attendant', 'clinician')", name="chk_slot_reported_by"),
        UniqueConstraint("encounter_id", "path", name="uq_slot_encounter_path"),
    )


class Utterance(Base):
    __tablename__ = "utterance"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    encounter_id = Column(UniversalUUID, ForeignKey("encounter.id"), nullable=False)
    seq = Column(Integer, nullable=False)
    speaker = Column(String, nullable=False)
    text = Column(String, nullable=False)
    lang = Column(String, nullable=False)
    asr_confidence = Column(Numeric(3, 2), nullable=False)
    audio_uri = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Document(Base):
    __tablename__ = "document"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    encounter_id = Column(UniversalUUID, ForeignKey("encounter.id"), nullable=False)
    page_no = Column(Integer, nullable=False)
    uri = Column(String, nullable=False)
    doc_type = Column(String, nullable=False)
    quality_score = Column(Numeric(3, 2), nullable=False)
    ocr_status = Column(String, nullable=False)
    doc_date = Column(Date, nullable=True)


class ExtractedEntity(Base):
    __tablename__ = "extracted_entity"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    document_id = Column(UniversalUUID, ForeignKey("document.id"), nullable=False)
    entity_type = Column(String, nullable=False)
    raw_text = Column(String, nullable=False)
    normalised = Column(UniversalJSONB, nullable=True)
    code_system = Column(String, nullable=True)
    code = Column(String, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=False)
    bbox = Column(UniversalJSONB, nullable=True)
    needs_review = Column(Boolean, default=False, nullable=False)


class RedFlagEvent(Base):
    __tablename__ = "red_flag_event"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    encounter_id = Column(UniversalUUID, ForeignKey("encounter.id"), nullable=False)
    rule_id = Column(String, nullable=False)
    tier = Column(Integer, nullable=False)
    trigger_text = Column(String, nullable=False)
    detected_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    acknowledged_by = Column(UniversalUUID, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    outcome = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint("tier IN (1, 2, 3)", name="chk_redflag_tier"),
    )


class ConsentRecord(Base):
    __tablename__ = "consent_record"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    patient_id = Column(UniversalUUID, ForeignKey("patient.id"), nullable=False)
    encounter_id = Column(UniversalUUID, ForeignKey("encounter.id"), nullable=False)
    purposes = Column(UniversalJSONB, nullable=False, comment="{clinical:bool, abdm:bool, qi:bool, research:bool}")
    language = Column(String, nullable=False)
    notice_version = Column(String, nullable=False)
    granted_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    abdm_artefact_id = Column(String, nullable=True)
    chain_hash = Column(LargeBinary, nullable=True)


class SummaryVersion(Base):
    __tablename__ = "summary_version"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    encounter_id = Column(UniversalUUID, ForeignKey("encounter.id"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    composition = Column(UniversalJSONB, nullable=False)
    generated_by = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    status = Column(String, nullable=False, default="preliminary")
    signed_by = Column(UniversalUUID, nullable=True)
    signed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('preliminary', 'final')", name="chk_summary_status"),
    )


class SummaryEdit(Base):
    """Training signal capturing physician edit diffs per PRD §14.2."""
    __tablename__ = "summary_edit"

    id = Column(UniversalUUID, primary_key=True, default=generate_uuid7)
    summary_version_id = Column(UniversalUUID, ForeignKey("summary_version.id"), nullable=False)
    slot_path = Column(String, nullable=False)
    old_value = Column(UniversalJSONB, nullable=True)
    new_value = Column(UniversalJSONB, nullable=True)
    reason = Column(String, nullable=True)
    edited_by = Column(UniversalUUID, nullable=False)
    edited_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditEvent(Base):
    """
    Append-only audit event log per PRD §21.8.
    Gapless, DB-assigned sequence number with cryptographic hash chain.
    """
    __tablename__ = "audit_event"

    seq = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    actor_id = Column(UniversalUUID, nullable=False)
    actor_role = Column(String, nullable=False)
    action = Column(String, nullable=False)
    resource_type = Column(String, nullable=False)
    resource_id = Column(UniversalUUID, nullable=False)
    patient_id = Column(UniversalUUID, nullable=True)
    encounter_id = Column(UniversalUUID, nullable=True)
    outcome = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    src_device = Column(String, nullable=True)
    src_ip = Column(String, nullable=True)
    payload_hash = Column(LargeBinary, nullable=False)
    prev_hash = Column(LargeBinary, nullable=False)
    entry_hash = Column(LargeBinary, nullable=False)

    __table_args__ = (
        CheckConstraint("action IN ('READ', 'CREATE', 'UPDATE', 'SIGN', 'EXPORT', 'BREAKGLASS')", name="chk_audit_action"),
        CheckConstraint("outcome IN ('ALLOW', 'DENY')", name="chk_audit_outcome"),
        Index("idx_audit_ts", "ts"),
        Index("idx_audit_encounter", "encounter_id"),
    )
