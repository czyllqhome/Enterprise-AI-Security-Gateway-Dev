from __future__ import annotations

import logging
import os
import socket
from threading import Event, Thread
from uuid import uuid4

from ..core.config import get_settings
from ..core.db import configure_database
from .document_worker import run_one


logger = logging.getLogger(__name__)


class FileReviewWorker:
    def __init__(self, *, worker_id: str | None = None) -> None:
        self.settings = get_settings()
        self.worker_id = worker_id or (
            f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
        )
        self._stop_event = Event()
        self._thread: Thread | None = None

    def run_once(self) -> bool:
        return run_one()

    def run_forever(self) -> None:
        poll_seconds = max(self.settings.file_review_worker_poll_seconds, 0.1)
        logger.info("File-review worker started. worker=%s", self.worker_id)
        while not self._stop_event.is_set():
            try:
                processed = self.run_once()
            except Exception:
                logger.exception("File-review worker loop failed. worker=%s", self.worker_id)
                processed = False
            if not processed:
                self._stop_event.wait(poll_seconds)
        logger.info("File-review worker stopped. worker=%s", self.worker_id)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = Thread(
            target=self.run_forever,
            name=f"file-review-{self.worker_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)


def main() -> None:
    configure_database()
    worker = FileReviewWorker()
    try:
        worker.run_forever()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    main()
