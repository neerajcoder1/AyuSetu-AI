"""Initial PostgreSQL schema for AyuSetu

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-07 20:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Patient table
    op.create_table(
        "patient",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("abha_id", sa.String(), unique=True, nullable=True),
        sa.Column("mrn", sa.String(), nullable=True),
        sa.Column("name_enc", sa.LargeBinary(), nullable=True, comment="Field-encrypted, separate DEK"),
        sa.Column("mobile_enc", sa.LargeBinary(), nullable=True, comment="Field-encrypted, separate DEK"),
        sa.Column("dob", sa.Date(), nullable=True),
        sa.Column("sex", sa.String(), nullable=True),
        sa.Column("district", sa.String(), nullable=True),
        sa.Column("is_provisional", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("merged_into", postgresql.UUID(as_uuid=True), sa.ForeignKey("patient.id"), nullable=True),
        sa.CheckConstraint("sex IN ('male', 'female', 'other') OR sex IS NULL", name="chk_patient_sex"),
    )

    # 2. Encounter table
    op.create_table(
        "encounter",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patient.id"), nullable=False),
        sa.Column("department", sa.String(), nullable=False),
        sa.Column("visit_type", sa.String(), nullable=False),
        sa.Column("intake_depth", sa.String(), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("reported_by", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.CheckConstraint("visit_type IN ('new', 'followup_stable', 'followup_new', 'walkin')", name="chk_encounter_visit_type"),
        sa.CheckConstraint("intake_depth IN ('fast', 'interval', 'delta', 'full')", name="chk_encounter_intake_depth"),
        sa.CheckConstraint("channel IN ('kiosk', 'pwa_self', 'pwa_companion', 'assisted')", name="chk_encounter_channel"),
        sa.CheckConstraint("status IN ('draft', 'submitted', 'preliminary', 'final', 'abandoned')", name="chk_encounter_status"),
    )

    # 3. Slot table (The ONLY origin of clinical facts)
    op.create_table(
        "slot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounter.id"), nullable=False),
        sa.Column("path", sa.String(), nullable=False, comment="e.g. hpi.severity"),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("value_coded", sa.String(), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_ref", postgresql.UUID(as_uuid=True), nullable=True, comment="utterance id or document region id"),
        sa.Column("reported_by", sa.String(), nullable=False),
        sa.Column("elicited", sa.Boolean(), server_default=sa.text("true"), nullable=False, comment="false => 'not elicited', never a negative"),
        sa.CheckConstraint("source IN ('utterance', 'touch', 'document', 'derived', 'clinician')", name="chk_slot_source"),
        sa.CheckConstraint("reported_by IN ('patient', 'companion', 'attendant', 'clinician')", name="chk_slot_reported_by"),
        sa.UniqueConstraint("encounter_id", "path", name="uq_slot_encounter_path"),
    )

    # 4. Utterance table
    op.create_table(
        "utterance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounter.id"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("lang", sa.String(), nullable=False),
        sa.Column("asr_confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("audio_uri", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 5. Document table
    op.create_table(
        "document",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounter.id"), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("uri", sa.String(), nullable=False),
        sa.Column("doc_type", sa.String(), nullable=False),
        sa.Column("quality_score", sa.Numeric(3, 2), nullable=False),
        sa.Column("ocr_status", sa.String(), nullable=False),
        sa.Column("doc_date", sa.Date(), nullable=True),
    )

    # 6. ExtractedEntity table
    op.create_table(
        "extracted_entity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document.id"), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("raw_text", sa.String(), nullable=False),
        sa.Column("normalised", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("code_system", sa.String(), nullable=True),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # 7. RedFlagEvent table
    op.create_table(
        "red_flag_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounter.id"), nullable=False),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("trigger_text", sa.String(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.CheckConstraint("tier IN (1, 2, 3)", name="chk_redflag_tier"),
    )

    # 8. ConsentRecord table
    op.create_table(
        "consent_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patient.id"), nullable=False),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounter.id"), nullable=False),
        sa.Column("purposes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("notice_version", sa.String(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abdm_artefact_id", sa.String(), nullable=True),
        sa.Column("chain_hash", sa.LargeBinary(), nullable=True),
    )

    # 9. SummaryVersion table
    op.create_table(
        "summary_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounter.id"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("composition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_by", sa.String(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="preliminary", nullable=False),
        sa.Column("signed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('preliminary', 'final')", name="chk_summary_status"),
    )

    # 10. SummaryEdit table
    op.create_table(
        "summary_edit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("summary_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("summary_version.id"), nullable=False),
        sa.Column("slot_path", sa.String(), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("edited_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 11. AuditEvent table (PRD §21.8)
    op.create_table(
        "audit_event",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("src_device", sa.String(), nullable=True),
        sa.Column("src_ip", sa.String(), nullable=True),
        sa.Column("payload_hash", sa.LargeBinary(), nullable=False),
        sa.Column("prev_hash", sa.LargeBinary(), nullable=False),
        sa.Column("entry_hash", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("action IN ('READ', 'CREATE', 'UPDATE', 'SIGN', 'EXPORT', 'BREAKGLASS')", name="chk_audit_action"),
        sa.CheckConstraint("outcome IN ('ALLOW', 'DENY')", name="chk_audit_outcome"),
    )
    op.create_index("idx_audit_ts", "audit_event", ["ts"])
    op.create_index("idx_audit_encounter", "audit_event", ["encounter_id"])


def downgrade() -> None:
    op.drop_index("idx_audit_encounter", table_name="audit_event")
    op.drop_index("idx_audit_ts", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_table("summary_edit")
    op.drop_table("summary_version")
    op.drop_table("consent_record")
    op.drop_table("red_flag_event")
    op.drop_table("extracted_entity")
    op.drop_table("document")
    op.drop_table("utterance")
    op.drop_table("slot")
    op.drop_table("encounter")
    op.drop_table("patient")
