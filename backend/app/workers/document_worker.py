"""Run with python -m app.workers.document_worker after database migrations."""
import argparse
import logging
import signal
import threading

from ..core.db import SessionLocal, configure_database
from ..core.logging import configure_logging
from ..services.review_job_service import claim_job, finish_job, heartbeat, ReviewLeaseLost
from ..services.file_review_service import FileReviewService

logger = logging.getLogger(__name__)


def run_one(session_factory=SessionLocal):
    with session_factory() as db:
        claim = claim_job(db)
    if claim is None:
        return False
    file_id, token = claim
    stop = threading.Event()

    def keep_lease():
        while not stop.wait(15):
            try:
                with session_factory() as db:
                    if not heartbeat(db, file_id, token):
                        return
            except Exception:
                logger.exception("Review heartbeat failed for file id %s", file_id)
                return

    thread = threading.Thread(target=keep_lease, daemon=True)
    thread.start()
    try:
        # This method creates its own sessions; avoid initializing a second scanner here.
        service = FileReviewService.__new__(FileReviewService)
        service.process_uploaded_file(file_id, lease_token=token)
        with session_factory() as db:
            finish_job(db, file_id, token)
    except ReviewLeaseLost:
        logger.warning("Review lease lost for file id %s; result will not be published", file_id)
    finally:
        stop.set()
        thread.join(timeout=2)
    return True


def main():
    parser = argparse.ArgumentParser(description="Process durable original-file review jobs")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    args = parser.parse_args()
    configure_logging()
    configure_database()
    stopping = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.set())
    while not stopping.is_set():
        try:
            worked = run_one()
        except Exception:
            logger.exception("Review worker iteration failed")
            worked = False
        if args.once:
            return
        if not worked:
            stopping.wait(5)


if __name__ == "__main__":
    main()
