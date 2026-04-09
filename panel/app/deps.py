from __future__ import annotations

import hmac
from fastapi import Request, HTTPException, Header

from .core import settings, with_base
from .db import SessionLocal
from .awg import AwgController


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def awg() -> AwgController:
    return AwgController(settings)


def _to_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if value is None:
        return b""
    return str(value).encode("utf-8")


def verify_password(candidate: str) -> bool:
    return hmac.compare_digest(_to_bytes(candidate), _to_bytes(settings.admin_pass))


def require_login(request: Request) -> None:
    if not request.session.get("user"):
        raise HTTPException(status_code=303, headers={"Location": with_base("/login")})


def require_api_key(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> None:
    token = (settings.api_token or "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="API token is not configured")
    candidate = ""
    if authorization:
        value = authorization.strip()
        if value.lower().startswith("bearer "):
            candidate = value[7:].strip()
    if not candidate and x_api_key:
        candidate = x_api_key.strip()
    if not candidate or not hmac.compare_digest(_to_bytes(candidate), _to_bytes(token)):
        raise HTTPException(status_code=401, detail="Invalid API token")
