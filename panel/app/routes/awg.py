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
from ..services.routing import (
    apply_geoip_block,
    clear_geoip_block,
    routing_status,
    save_routing_config,
    update_geoip_database,
    update_geosite_database,
)
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


@router.get("/api/awg/routing")
def api_awg_routing(request: Request):
    require_login(request)
    return routing_status()


@router.post("/api/awg/routing")
async def api_awg_routing_update(request: Request):
    require_login(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    updates = {}
    extra_bypass_geosite_tags = []
    if "enabled" in payload:
        updates["enabled"] = bool(payload.get("enabled"))
    if "geoip_tags" in payload:
        tags = payload.get("geoip_tags")
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.replace("\n", ",").split(",")]
        if not isinstance(tags, list):
            raise HTTPException(status_code=400, detail="geoip_tags must be a list")
        updates["geoip_tags"] = tags
    if "geoip_url" in payload:
        updates["geoip_url"] = str(payload.get("geoip_url") or "").strip()
    if "dns_block_enabled" in payload:
        updates["dns_block_enabled"] = bool(payload.get("dns_block_enabled"))
    if "dns_redirect_enabled" in payload:
        updates["dns_redirect_enabled"] = bool(payload.get("dns_redirect_enabled"))
    if "dns_upstreams" in payload:
        upstreams = payload.get("dns_upstreams")
        if isinstance(upstreams, str):
            upstreams = [item.strip() for item in upstreams.replace("\n", ",").split(",")]
        if not isinstance(upstreams, list):
            raise HTTPException(status_code=400, detail="dns_upstreams must be a list")
        updates["dns_upstreams"] = upstreams
    if "bypass_dns_upstreams" in payload:
        upstreams = payload.get("bypass_dns_upstreams")
        if isinstance(upstreams, str):
            upstreams = [item.strip() for item in upstreams.replace("\n", ",").split(",")]
        if not isinstance(upstreams, list):
            raise HTTPException(status_code=400, detail="bypass_dns_upstreams must be a list")
        updates["bypass_dns_upstreams"] = upstreams
    if "geosite_tags" in payload:
        tags = payload.get("geosite_tags")
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.replace("\n", ",").split(",")]
        if not isinstance(tags, list):
            raise HTTPException(status_code=400, detail="geosite_tags must be a list")
        updates["geosite_tags"] = tags
    if "geosite_url" in payload:
        updates["geosite_url"] = str(payload.get("geosite_url") or "").strip()
    if "manual_domains" in payload:
        domains = payload.get("manual_domains")
        if isinstance(domains, str):
            domains = [item.strip() for item in domains.replace("\n", ",").split(",")]
        if not isinstance(domains, list):
            raise HTTPException(status_code=400, detail="manual_domains must be a list")
        updates["manual_domains"] = domains
    if "bypass_domains" in payload:
        domains = payload.get("bypass_domains")
        if isinstance(domains, str):
            domains = [item.strip() for item in domains.replace("\n", ",").split(",")]
        if not isinstance(domains, list):
            raise HTTPException(status_code=400, detail="bypass_domains must be a list")
        updates["bypass_domains"] = [item for item in domains if "." in str(item or "").strip()]
        extra_bypass_geosite_tags = [item for item in domains if str(item or "").strip() and "." not in str(item or "").strip()]
    if "bypass_geosite_tags" in payload:
        tags = payload.get("bypass_geosite_tags")
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.replace("\n", ",").split(",")]
        if not isinstance(tags, list):
            raise HTTPException(status_code=400, detail="bypass_geosite_tags must be a list")
        updates["bypass_geosite_tags"] = tags + extra_bypass_geosite_tags
    elif extra_bypass_geosite_tags:
        updates["bypass_geosite_tags"] = extra_bypass_geosite_tags

    save_routing_config(updates)
    return {"ok": True, **routing_status()}


@router.post("/api/awg/routing/geoip/update")
async def api_awg_routing_geoip_update(request: Request):
    require_login(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        update_geoip_database(str(payload.get("geoip_url") or "").strip() or None)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, **routing_status()}


@router.post("/api/awg/routing/geosite/update")
async def api_awg_routing_geosite_update(request: Request):
    require_login(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        update_geosite_database(str(payload.get("geosite_url") or "").strip() or None)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, **routing_status()}


@router.post("/api/awg/routing/apply")
def api_awg_routing_apply(request: Request):
    require_login(request)
    try:
        result = apply_geoip_block()
    except Exception as exc:
        save_routing_config({"last_error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {**result, **routing_status()}


@router.post("/api/awg/routing/clear")
def api_awg_routing_clear(request: Request):
    require_login(request)
    try:
        result = clear_geoip_block()
    except Exception as exc:
        save_routing_config({"last_error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {**result, **routing_status()}
