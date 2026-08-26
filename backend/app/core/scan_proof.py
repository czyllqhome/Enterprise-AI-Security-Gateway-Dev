from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from .config import get_settings


class ScanProofError(ValueError):
    pass


def canonical_json_digest(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_scan_proof(
    *,
    event_id: int,
    session_id: int,
    username: str,
    payload_digest: str,
    scanner_config_hash: str,
    attachment_file_id: int | None,
) -> tuple[str, int]:
    settings = get_settings()
    expires_at = int(time.time()) + max(settings.scan_proof_ttl_seconds, 1)
    claims = {
        "v": 1,
        "event_id": event_id,
        "session_id": session_id,
        "username": username,
        "payload_digest": payload_digest,
        "scanner_config_hash": scanner_config_hash,
        "attachment_file_id": attachment_file_id,
        "exp": expires_at,
        "jti": secrets.token_urlsafe(12),
    }
    body = _b64url(
        json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    )
    signature = hmac.new(
        settings.scan_proof_secret.encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{body}.{_b64url(signature)}", expires_at


def decode_scan_proof(token: str) -> dict[str, Any]:
    try:
        body, supplied_signature = token.split(".", 1)
    except ValueError as exc:
        raise ScanProofError("Invalid scan proof.") from exc

    expected_signature = hmac.new(
        get_settings().scan_proof_secret.encode("utf-8"),
        body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64url(expected_signature), supplied_signature):
        raise ScanProofError("Invalid scan proof signature.")

    try:
        claims = json.loads(_b64url_decode(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ScanProofError("Invalid scan proof payload.") from exc
    if not isinstance(claims, dict) or claims.get("v") != 1:
        raise ScanProofError("Unsupported scan proof version.")
    if int(claims.get("exp") or 0) < int(time.time()):
        raise ScanProofError("Scan proof expired.")
    return claims


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _b64url_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(f"{payload}{padding}")
