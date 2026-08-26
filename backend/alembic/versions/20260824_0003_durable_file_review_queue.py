"""Add durable file-review queue leasing and retry metadata.

Revision ID: 20260824_0003
Revises: 20260824_0002
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0003"
down_revision: str | None = "20260824_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("uploaded_files", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("uploaded_files", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("uploaded_files", sa.Column("lease_owner", sa.String(length=128), nullable=True))
    op.add_column("uploaded_files", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("uploaded_files", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("uploaded_files", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_uploaded_files_queue",
        "uploaded_files",
        ["status", "next_attempt_at", "lease_expires_at"],
    )
    op.create_index(
        "ix_uploaded_files_owner_created",
        "uploaded_files",
        ["uploaded_by", "created_at"],
    )
    op.execute("UPDATE uploaded_files SET status = 'queued' WHERE status = 'processing'")


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_owner_created", table_name="uploaded_files")
    op.drop_index("ix_uploaded_files_queue", table_name="uploaded_files")
    op.drop_column("uploaded_files", "completed_at")
    op.drop_column("uploaded_files", "processing_started_at")
    op.drop_column("uploaded_files", "lease_expires_at")
    op.drop_column("uploaded_files", "lease_owner")
    op.drop_column("uploaded_files", "next_attempt_at")
    op.drop_column("uploaded_files", "attempt_count")
