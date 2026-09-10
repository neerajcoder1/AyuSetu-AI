"""Database-level audit immutability triggers and quarantine persistence table

Revision ID: 0002_audit_immutability_and_quarantine
Revises: 0001_initial_schema
Create Date: 2026-09-10 10:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_audit_immutability_and_quarantine"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. QuarantinedAuditBatch table (Durable PostgreSQL store for invalid/tampered batches)
    op.create_table(
        "quarantined_audit_batch",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("seed_head_hash", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("failure_code", sa.String(), nullable=False),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("safe_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index("idx_quarantine_device", "quarantined_audit_batch", ["device_id"])
    op.create_index("idx_quarantine_ts", "quarantined_audit_batch", ["quarantined_at"])

    # 2. PostgreSQL Triggers for Audit Immutability (Reject UPDATE & DELETE)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION trg_prevent_audit_event_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Audit events are immutable and cannot be updated or deleted. Violation attempted on seq %', OLD.seq;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_audit_event_no_update
            BEFORE UPDATE ON audit_event
            FOR EACH ROW EXECUTE FUNCTION trg_prevent_audit_event_mutation();
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_audit_event_no_delete
            BEFORE DELETE ON audit_event
            FOR EACH ROW EXECUTE FUNCTION trg_prevent_audit_event_mutation();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_delete ON audit_event;")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_event_no_update ON audit_event;")
        op.execute("DROP FUNCTION IF EXISTS trg_prevent_audit_event_mutation();")

    op.drop_index("idx_quarantine_ts", table_name="quarantined_audit_batch")
    op.drop_index("idx_quarantine_device", table_name="quarantined_audit_batch")
    op.drop_table("quarantined_audit_batch")
