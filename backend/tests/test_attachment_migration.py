import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def load_revision(name):
    path = Path(__file__).parents[1] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_attachment_migration_upgrade_and_downgrade():
    initial = load_revision("20260614_0001_initial_product_schema.py")
    attachments = load_revision("20260907_0002_original_attachments.py")
    jobs = load_revision("20260907_0003_review_jobs.py")
    checkpoints = load_revision("20260907_0004_review_checkpoints.py")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            initial.upgrade()
            attachments.upgrade()
            jobs.upgrade()
            checkpoints.upgrade()
            names = set(inspect(connection).get_table_names())
            assert {"attachment_identities", "chat_send_snapshots", "message_attachments"} <= names
            assert "file_review_jobs" in names
            assert "file_review_checkpoints" in names
            assert {c["name"] for c in inspect(connection).get_columns("attachment_identities")} >= {
                "sha256", "owner_user_id", "reviewed_sha256", "review_policy",
            }
            checkpoints.downgrade()
            jobs.downgrade()
            attachments.downgrade()
            remaining = set(inspect(connection).get_table_names())
            assert "uploaded_files" in remaining and "chat_messages" in remaining
            assert not {"attachment_identities", "chat_send_snapshots", "message_attachments"} & remaining
            assert "file_review_checkpoints" not in remaining
    engine.dispose()
