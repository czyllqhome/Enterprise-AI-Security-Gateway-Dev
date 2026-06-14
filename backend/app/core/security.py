import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from .config import get_settings


class TokenDecodeError(Exception):
    pass


try:
    import jwt
except ImportError:
    jwt = None

try:
    from passlib.context import CryptContext
except ImportError:
    CryptContext = None


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto") if CryptContext else None


def hash_password(password: str) -> str:
    if pwd_context is not None:
        return pwd_context.hash(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 260000)
    return f"pbkdf2_sha256${salt}${base64.urlsafe_b64encode(digest).decode('ascii')}"


def verify_password(password: str, password_hash: str) -> bool:
    if pwd_context is not None and not password_hash.startswith("pbkdf2_sha256$"):
        return pwd_context.verify(password, password_hash)
    try:
        _, salt, expected = password_hash.split("$", 2)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 260000)
    actual = base64.urlsafe_b64encode(digest).decode("ascii")
    return hmac.compare_digest(actual, expected)


def create_access_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_expires_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expires_at,
        "iat": datetime.now(UTC),
    }
    if claims:
        payload.update(claims)
    if jwt is not None:
        return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")
    return _encode_hs256(payload, settings.jwt_secret_key)


def decode_access_token(token: str) -> dict[str, Any]:
    if jwt is not None:
        try:
            return jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
        except Exception as exc:
            raise TokenDecodeError("Invalid token.") from exc
    return _decode_hs256(token, get_settings().jwt_secret_key)


def _encode_hs256(payload: dict[str, Any], secret: str) -> str:
    json_payload = dict(payload)
    for key in ("exp", "iat"):
        if isinstance(json_payload.get(key), datetime):
            json_payload[key] = int(json_payload[key].timestamp())
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _b64url(json.dumps(json_payload, separators=(",", ":")).encode("utf-8")),
        ],
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def _decode_hs256(token: str, secret: str) -> dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split(".", 2)
    except ValueError as exc:
        raise TokenDecodeError("Invalid token.") from exc

    signing_input = f"{header_part}.{payload_part}"
    expected = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url(expected), signature_part):
        raise TokenDecodeError("Invalid token signature.")

    payload = json.loads(_b64url_decode(payload_part))
    expires_at = payload.get("exp")
    if expires_at is not None and datetime.now(UTC).timestamp() > float(expires_at):
        raise TokenDecodeError("Token expired.")
    return payload


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")
