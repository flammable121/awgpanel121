from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

PBKDF2_PREFIX = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 310_000


def _to_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if value is None:
        return b""
    return str(value).encode("utf-8")


def _parse_pbkdf2_hash(value: str) -> tuple[int, bytes, bytes] | None:
    parts = (value or "").split("$")
    if len(parts) != 4:
        return None
    if parts[0] != PBKDF2_PREFIX:
        return None
    try:
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2].encode("ascii"), validate=True)
        digest = base64.b64decode(parts[3].encode("ascii"), validate=True)
    except (ValueError, TypeError, binascii.Error):
        return None
    if iterations <= 0 or not salt or not digest:
        return None
    return iterations, salt, digest


def is_pbkdf2_hash(value: str) -> bool:
    return _parse_pbkdf2_hash(value) is not None


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", _to_bytes(password), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"{PBKDF2_PREFIX}${iterations}${salt_b64}${digest_b64}"


def verify_password(candidate: str, stored: str) -> bool:
    parsed = _parse_pbkdf2_hash(stored)
    if parsed:
        iterations, salt, expected = parsed
        current = hashlib.pbkdf2_hmac("sha256", _to_bytes(candidate), salt, iterations)
        return hmac.compare_digest(current, expected)
    return hmac.compare_digest(_to_bytes(candidate), _to_bytes(stored))


def password_requires_upgrade(stored: str) -> bool:
    parsed = _parse_pbkdf2_hash(stored)
    if not parsed:
        return True
    iterations, _, _ = parsed
    return iterations < PBKDF2_ITERATIONS
