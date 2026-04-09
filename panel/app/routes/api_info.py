from __future__ import annotations

import secrets
from fastapi import APIRouter, Request

from ..core import settings, BASE_PATH
from ..deps import require_login
from ..services.secrets import update_secrets_file

router = APIRouter()


@router.get("/api/api-info")
def api_info(request: Request):
    require_login(request)
    origin = f"{request.url.scheme}://{request.url.netloc}"
    base_url = f"{origin}{BASE_PATH}" if BASE_PATH else origin
    return {
        "api_token": settings.api_token or "",
        "base_url": base_url,
        "base_path": BASE_PATH,
    }


@router.post("/api/api-token/reset")
def api_token_reset(request: Request):
    require_login(request)
    token = secrets.token_hex(24)
    update_secrets_file({"API_TOKEN": token})
    settings.api_token = token
    return {"ok": True, "api_token": token}
