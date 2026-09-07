"""Persist per-unit review results for bounded retry."""
from alembic import op
import sqlalchemy as sa

revision = "20260907_0004"
down_revision = "20260907_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("file_review_checkpoints",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("policy_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("location", sa.String(1024), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("result_json", sa.JSON()),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_file_review_checkpoints_file_id", "file_review_checkpoints", ["file_id"])


def downgrade():
    op.drop_table("file_review_checkpoints")
