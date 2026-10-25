"""Tokens, token hashes and the login password hashes (PBKDF2-SHA256)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 600_000
_PREFIX = "pbkdf2-sha256"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str, *, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Format pbkdf2-sha256:<iterations>:<salt>:<hash>, without $ so Compose does not interpolate it."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{_PREFIX}:{iterations}:{_b64(salt)}:{_b64(digest)}"


def validate_password_hash(encoded: str) -> None:
    parts = encoded.split(":")
    if len(parts) != 4 or parts[0] != _PREFIX:
        raise ValueError("expected pbkdf2-sha256:<iterations>:<salt>:<hash>, create one with `wordpressmcp hash-password`")
    try:
        if int(parts[1]) < 1000:
            raise ValueError("iteration count too low")
        if len(_unb64(parts[2])) < 8 or len(_unb64(parts[3])) != 32:
            raise ValueError("salt or hash has the wrong length")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid password hash: {exc}") from exc


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, iterations, salt, digest = encoded.split(":")
        expected = _unb64(digest)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
