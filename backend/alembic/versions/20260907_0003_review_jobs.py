"""Durable original-file review jobs."""
from alembic import op
import sqlalchemy as sa

revision = "20260907_0003"
down_revision = "20260907_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("file_review_jobs",
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text()),
    )
    op.create_index("ix_file_review_jobs_state", "file_review_jobs", ["state"])


def downgrade():
    op.drop_table("file_review_jobs")
