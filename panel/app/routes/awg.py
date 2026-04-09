from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from ..deps import require_login, awg
from ..services.awg_service import (
    read_interface_config,
    update_interface_lines,
    apply_config_from_db,
)
from ..utils import generate_i_chain
from ..core import settings
from ..services.secrets import update_secrets_file
from ..db import SessionLocal

router = APIRouter()


@router.get("/api/awg/params")
def api_awg_params(request: Request):
    require_login(request)
    controller = awg()
    _, interface_kv, _ = read_interface_config(controller)
    keys = ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4"]
    params = {key: interface_kv.get(key, "") for key in keys}
    return {"params": params}


@router.post("/api/awg/params")
async def api_awg_params_update(request: Request):
    require_login(request)
    payload = await request.json()
    keys = ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4"]
    updates: dict[str, str] = {}
    for key in keys:
        if key in payload:
            value = str(payload.get(key, "")).strip()
            updates[key] = value

    controller = awg()
    interface_lines, _, _ = read_interface_config(controller)
    interface_lines = update_interface_lines(interface_lines, updates)
    db = SessionLocal()
    try:
        apply_config_from_db(db, controller, interface_lines)
    finally:
        db.close()

    _, interface_kv, _ = read_interface_config(controller)
    params = {key: interface_kv.get(key, "") for key in keys}
    return {"ok": True, "params": params}


@router.get("/api/awg/i-chain")
def api_awg_i_chain(request: Request):
    require_login(request)
    return generate_i_chain()


@router.get("/api/awg/settings")
def api_awg_settings(request: Request):
    require_login(request)
    return {
        "public_endpoint": settings.public_endpoint or "",
        "default_client_allowed_ips": settings.default_client_allowed_ips,
        "default_client_dns": settings.default_client_dns or "",
    }


@router.post("/api/awg/settings")
async def api_awg_settings_update(request: Request):
    require_login(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    updates: dict[str, str] = {}

    if "public_endpoint" in payload:
        value = str(payload.get("public_endpoint") or "").strip()
        updates["PUBLIC_ENDPOINT"] = value
        settings.public_endpoint = value or None

    if "default_client_allowed_ips" in payload:
        value = str(payload.get("default_client_allowed_ips") or "").strip()
        if not value:
            raise HTTPException(status_code=400, detail="DEFAULT_CLIENT_ALLOWED_IPS is required")
        updates["DEFAULT_CLIENT_ALLOWED_IPS"] = value
        settings.default_client_allowed_ips = value

    if "default_client_dns" in payload:
        value = str(payload.get("default_client_dns") or "").strip()
        updates["DEFAULT_CLIENT_DNS"] = value
        settings.default_client_dns = value or None

    if updates:
        update_secrets_file(updates)

    return {
        "ok": True,
        "public_endpoint": settings.public_endpoint or "",
        "default_client_allowed_ips": settings.default_client_allowed_ips,
        "default_client_dns": settings.default_client_dns or "",
    }
