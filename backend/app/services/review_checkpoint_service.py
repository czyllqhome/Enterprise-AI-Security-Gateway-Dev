import json
from ..models.review_checkpoint import ReviewCheckpoint
from .attachment_integrity import sha256
from .review_job_service import require_lease


class ReviewCheckpointStore:
    def __init__(self, session_factory, file_id, source_hash, policy_hash, lease_token):
        self.session_factory = session_factory
        self.file_id = file_id
        self.source_hash = source_hash
        self.policy_hash = policy_hash
        self.lease_token = lease_token

    def run(self, kind, location, content, evaluate, encode, decode, reusable):
        key = sha256(json.dumps([self.file_id, self.source_hash, self.policy_hash, kind, location, sha256(content)]).encode())
        with self.session_factory() as db:
            require_lease(db, self.file_id, self.lease_token)
            saved = db.get(ReviewCheckpoint, key)
            if saved and saved.state == "completed":
                result = decode(saved.result_json)
                if reusable(result):
                    return result
            if saved is None:
                saved = ReviewCheckpoint(id=key, file_id=self.file_id, source_hash=self.source_hash,
                    policy_hash=self.policy_hash, kind=kind, location=location[:1024], attempts=0)
                db.add(saved)
            saved.state, saved.result_json = "running", None
            saved.attempts += 1
            db.commit()
        try:
            result = evaluate()
        except Exception:
            with self.session_factory() as db:
                require_lease(db, self.file_id, self.lease_token)
                db.get(ReviewCheckpoint, key).state = "failed"
                db.commit()
            raise
        with self.session_factory() as db:
            require_lease(db, self.file_id, self.lease_token)
            saved = db.get(ReviewCheckpoint, key)
            success = reusable(result)
            saved.state = "completed" if success else "failed"
            saved.result_json = encode(result) if success else None
            db.commit()
        return result
