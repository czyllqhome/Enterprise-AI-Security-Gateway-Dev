from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.review_checkpoint import ReviewCheckpoint
from app.models.review_job import ReviewJob
from app.services.review_checkpoint_service import ReviewCheckpointStore
from app.services.review_job_service import claim_job, ReviewLeaseLost
from test_file_review_permissions import db_session, create_user, create_uploaded_file


def store_for(db):
    create_user(db, "alice")
    file = create_uploaded_file(db, uploaded_by="alice", filename="file.pdf")
    db.add(ReviewJob(file_id=file.id, state="queued", phase="queued", attempts=0))
    db.commit()
    file_id, token = claim_job(db)
    return ReviewCheckpointStore(sessionmaker(bind=db.get_bind()), file_id, "a" * 64, "b" * 64, token), file_id


def test_completed_unit_is_reused_without_repeating_model_call(db_session):
    store, file_id = store_for(db_session)
    evaluate = Mock(return_value={"decision": "allow"})
    arguments = ("visual", "Page 1", b"image", evaluate, lambda value: value,
                 lambda value: value, lambda value: value["decision"] in {"allow", "block"})
    assert store.run(*arguments) == {"decision": "allow"}
    assert store.run(*arguments) == {"decision": "allow"}
    assert evaluate.call_count == 1
    checkpoint = db_session.query(ReviewCheckpoint).filter_by(file_id=file_id).one()
    assert checkpoint.state == "completed" and checkpoint.attempts == 1


def test_failed_unit_only_is_retried(db_session):
    store, file_id = store_for(db_session)
    first = Mock(side_effect=TimeoutError("offline"))
    args = ("privacy", "Page 2", b"text", first, lambda value: value,
            lambda value: value, lambda value: True)
    with pytest.raises(TimeoutError):
        store.run(*args)
    retry = Mock(return_value={"safe": True})
    retry_args = ("privacy", "Page 2", b"text", retry, lambda value: value,
                  lambda value: value, lambda value: True)
    assert store.run(*retry_args) == {"safe": True}
    checkpoint = db_session.query(ReviewCheckpoint).filter_by(file_id=file_id).one()
    assert checkpoint.state == "completed" and checkpoint.attempts == 2


def test_changed_source_or_policy_does_not_reuse_checkpoint(db_session):
    store, file_id = store_for(db_session)
    evaluate = Mock(side_effect=[{"safe": True}, {"safe": True}, {"safe": True}])
    args = ("privacy", "Page 1", b"text", evaluate, lambda value: value,
            lambda value: value, lambda value: True)
    store.run(*args)
    ReviewCheckpointStore(store.session_factory, file_id, "c" * 64, store.policy_hash, store.lease_token).run(*args)
    ReviewCheckpointStore(store.session_factory, file_id, store.source_hash, "d" * 64, store.lease_token).run(*args)
    assert evaluate.call_count == 3
    assert db_session.query(ReviewCheckpoint).filter_by(file_id=file_id).count() == 3


def test_stale_worker_cannot_publish_checkpoint(db_session):
    store, file_id = store_for(db_session)
    job = db_session.get(ReviewJob, file_id)
    job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(ReviewLeaseLost):
        store.run("visual", "Page 1", b"image", lambda: {"safe": True},
                  lambda value: value, lambda value: value, lambda value: True)
    assert db_session.query(ReviewCheckpoint).filter_by(file_id=file_id).count() == 0
