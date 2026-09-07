from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import and_, or_, select, update
from ..models.review_job import ReviewJob
from ..models.uploaded_file import UploadedFile
from ..models.attachment import AttachmentIdentity

LEASE_SECONDS = 90
MAX_ATTEMPTS = 3


class ReviewLeaseLost(RuntimeError):
    pass


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def require_lease(db, file_id, token):
    job = db.scalar(select(ReviewJob).where(ReviewJob.file_id == file_id).with_for_update()
                    .execution_options(populate_existing=True))
    if (job is None or job.state != "running" or job.lease_token != token
            or job.lease_until is None or utc(job.lease_until) <= datetime.now(timezone.utc)):
        raise ReviewLeaseLost("Review lease expired or was replaced.")
    return job


def claim_job(db):
    now = datetime.now(timezone.utc)
    job = db.scalar(select(ReviewJob).where(or_(
        and_(ReviewJob.state == "queued", ReviewJob.next_attempt_at <= now),
        and_(ReviewJob.state == "running", ReviewJob.lease_until <= now),
    )).order_by(ReviewJob.next_attempt_at, ReviewJob.file_id).with_for_update(skip_locked=True).limit(1))
    if job is None:
        db.rollback()
        return None
    if job.attempts >= MAX_ATTEMPTS:
        job.state, job.phase, job.last_error = "failed", "failed", "Review retry budget exhausted."
        record = db.get(UploadedFile, job.file_id)
        record.status, record.error_message = "failed", job.last_error
        identity = db.get(AttachmentIdentity, job.file_id)
        if identity:
            identity.decision = "unknown"
        db.commit()
        return None
    job.state, job.phase = "running", "starting"
    job.lease_token = str(uuid4())
    job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    job.attempts += 1
    record = db.get(UploadedFile, job.file_id)
    record.status = "processing"
    record.attempt_count = job.attempts
    record.lease_owner = job.lease_token
    record.lease_expires_at = job.lease_until
    record.processing_started_at = record.processing_started_at or now
    claim = (job.file_id, job.lease_token)
    db.commit()
    return claim


def heartbeat(db, file_id, token):
    now = datetime.now(timezone.utc)
    changed = db.execute(update(ReviewJob).where(
        ReviewJob.file_id == file_id, ReviewJob.state == "running", ReviewJob.lease_token == token,
        ReviewJob.lease_until > now,
    ).values(lease_until=now + timedelta(seconds=LEASE_SECONDS))).rowcount
    record = db.get(UploadedFile, file_id)
    if changed == 1 and record is not None and record.lease_owner == token:
        record.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    db.commit()
    return changed == 1


def finish_job(db, file_id, token):
    job = require_lease(db, file_id, token)
    record = db.get(UploadedFile, file_id)
    if record.status == "failed":
        job.last_error = record.error_message
        job.state = "queued" if job.attempts < MAX_ATTEMPTS else "failed"
        if job.state == "queued":
            record.status = "processing"
        job.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=10 * job.attempts)
    else:
        job.state = "completed"
        job.last_error = None
    job.phase = job.state
    job.lease_token = None
    job.lease_until = None
    if record is not None:
        record.lease_owner = None
        record.lease_expires_at = None
        if job.state == "completed":
            record.completed_at = datetime.now(timezone.utc)
    db.commit()
