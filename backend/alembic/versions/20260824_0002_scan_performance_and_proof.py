"""Add scan performance telemetry and single-use confirmation proofs.

Revision ID: 20260824_0002
Revises: 20260614_0001
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0002"
down_revision: str | None = "20260614_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scan_events", sa.Column("input_digest", sa.String(length=64), nullable=True))
    op.add_column("scan_events", sa.Column("scanner_config_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "scan_events",
        sa.Column("scan_duration_ms", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column("scan_events", sa.Column("scanner_timings_json", sa.JSON(), nullable=True))
    op.add_column("scan_events", sa.Column("degraded_scanners_json", sa.JSON(), nullable=True))
    op.add_column("scan_events", sa.Column("proof_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scan_events", sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_scan_events_created_at", "scan_events", ["created_at"])
    op.create_index(
        "ix_scan_events_username_created_at",
        "scan_events",
        ["username", "created_at"],
    )
    op.create_index(
        "ix_scan_events_status_created_at",
        "scan_events",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scan_events_status_created_at", table_name="scan_events")
    op.drop_index("ix_scan_events_username_created_at", table_name="scan_events")
    op.drop_index("ix_scan_events_created_at", table_name="scan_events")
    op.drop_column("scan_events", "consumed_at")
    op.drop_column("scan_events", "proof_expires_at")
    op.drop_column("scan_events", "degraded_scanners_json")
    op.drop_column("scan_events", "scanner_timings_json")
    op.drop_column("scan_events", "scan_duration_ms")
    op.drop_column("scan_events", "scanner_config_hash")
    op.drop_column("scan_events", "input_digest")
