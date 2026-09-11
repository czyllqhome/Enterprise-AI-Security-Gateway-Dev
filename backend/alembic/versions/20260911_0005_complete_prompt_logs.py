"""Record every prompt with its immutable guardrail decision.

Revision ID: 20260911_0005
Revises: 20260907_0004
Create Date: 2026-09-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260911_0005"
down_revision = "20260907_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.add_column(
            sa.Column("decision", sa.String(length=32), nullable=False, server_default="allowed"),
        )
        batch_op.add_column(
            sa.Column("scan_event_id", sa.Integer(), nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_chat_logs_scan_event_id_scan_events",
            "scan_events",
            ["scan_event_id"],
            ["id"],
            ondelete="SET NULL",
        )
    # Before this revision, a null message_id represented a hard block and a
    # populated message_id represented a reviewed sensitive send.
    op.execute(
        "UPDATE chat_logs SET decision = "
        "CASE WHEN message_id IS NULL THEN 'blocked' ELSE 'review' END"
    )
    op.create_index("ix_chat_logs_scan_event_id", "chat_logs", ["scan_event_id"])
    op.create_index(
        "ix_chat_logs_decision_created_at",
        "chat_logs",
        ["decision", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_logs_decision_created_at", table_name="chat_logs")
    op.drop_index("ix_chat_logs_scan_event_id", table_name="chat_logs")
    with op.batch_alter_table("chat_logs") as batch_op:
        batch_op.drop_constraint("fk_chat_logs_scan_event_id_scan_events", type_="foreignkey")
        batch_op.drop_column("scan_event_id")
        batch_op.drop_column("decision")
