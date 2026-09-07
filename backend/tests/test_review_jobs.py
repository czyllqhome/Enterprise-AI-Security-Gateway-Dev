from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from test_file_review_permissions import db_session, create_user, create_uploaded_file
from app.models.review_job import ReviewJob
from app.services.review_job_service import claim_job, heartbeat, require_lease, finish_job, ReviewLeaseLost


def enqueue(db):
    create_user(db, "alice")
    file = create_uploaded_file(db, uploaded_by="alice", filename="file.pdf")
    db.add(ReviewJob(file_id=file.id, state="queued", phase="queued", attempts=0))
    db.commit()
    return file


def test_job_is_claimed_once_and_can_be_renewed(db_session):
    file = enqueue(db_session)
    claim = claim_job(db_session)
    assert claim[0] == file.id
    assert claim_job(db_session) is None
    assert heartbeat(db_session, *claim)
    assert require_lease(db_session, *claim).state == "running"


def test_expired_worker_is_fenced_after_recovery(db_session):
    enqueue(db_session)
    old = claim_job(db_session)
    job = db_session.get(ReviewJob, old[0])
    job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    replacement = claim_job(db_session)
    assert replacement[0] == old[0] and replacement[1] != old[1]
    assert not heartbeat(db_session, *old)
    with pytest.raises(ReviewLeaseLost):
        require_lease(db_session, *old)
    assert require_lease(db_session, *replacement).attempts == 2


def test_completed_review_is_not_reclaimed(db_session):
    file = enqueue(db_session)
    claim = claim_job(db_session)
    file.status = "completed"
    db_session.commit()
    finish_job(db_session, *claim)
    assert claim_job(db_session) is None
    assert db_session.get(ReviewJob, file.id).state == "completed"


def test_failed_review_uses_bounded_retry(db_session):
    file = enqueue(db_session)
    for attempt in range(1, 4):
        claim = claim_job(db_session)
        assert claim is not None
        file.status, file.error_message = "failed", "test failure"
        db_session.commit()
        finish_job(db_session, *claim)
        job = db_session.get(ReviewJob, file.id)
        assert job.attempts == attempt
        if attempt < 3:
            assert job.state == "queued" and file.status == "processing"
            job.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db_session.commit()
    assert job.state == "failed"
    assert claim_job(db_session) is None
