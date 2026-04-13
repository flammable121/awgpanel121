from __future__ import annotations

import io
from urllib.parse import quote

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, Response

from ..deps import require_login, require_api_key, awg, get_db
from ..core import templates, template_context, with_base
from ..models import Peer
from ..utils import format_date, utc_now
from ..services.awg_service import (
    build_peers_payload,
    read_interface_config,
    apply_config_from_db,
    get_server_public_key,
    build_client_config,
    ensure_endpoint,
    parse_expires_from_form,
    parse_expires_from_api,
    get_peer_status,
    status_label,
    build_new_peer,
    peer_basic_row,
    safe_filename,
    parse_bool,
)

router = APIRouter()


@router.get("/api/peers")
def api_peers(request: Request, db=Depends(get_db)):
    require_login(request)
    controller = awg()
    return build_peers_payload(db, controller)


@router.get("/api/v1/peers")
def api_v1_peers(request: Request, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    return build_peers_payload(db, controller)


@router.get("/api/v1/peers/{peer_id}")
def api_v1_peer(request: Request, peer_id: str, db=Depends(get_db), _=Depends(require_api_key)):
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    return {"peer": peer_basic_row(peer)}


@router.post("/api/v1/peers")
async def api_v1_create_peer(request: Request, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    name = str(payload.get("name") or "").strip()
    expires_at = parse_expires_from_api(payload)
    peer = build_new_peer(name, controller, db, expires_at, allow_apply_fail=True)

    if "client_allowed_ips" in payload:
        val = str(payload.get("client_allowed_ips") or "").strip()
        if val:
            peer.client_allowed_ips = val
    if "client_dns" in payload:
        val = str(payload.get("client_dns") or "").strip()
        peer.client_dns = val or None
    if "note" in payload:
        note = str(payload.get("note") or "").strip()
        peer.note = note or None
    if "enabled" in payload:
        peer.enabled = parse_bool(payload.get("enabled"))
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines, allow_fail=True)
    return {"ok": True, "peer": peer_basic_row(peer)}


@router.patch("/api/v1/peers/{peer_id}")
async def api_v1_update_peer(request: Request, peer_id: str, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if "name" in payload:
        peer.name = str(payload.get("name") or "").strip() or peer.name
    if "note" in payload:
        note = str(payload.get("note") or "").strip()
        peer.note = note or None
    if "client_allowed_ips" in payload:
        val = str(payload.get("client_allowed_ips") or "").strip()
        if val:
            peer.client_allowed_ips = val
    if "client_dns" in payload:
        val = str(payload.get("client_dns") or "").strip()
        peer.client_dns = val or None
    if "enabled" in payload:
        peer.enabled = parse_bool(payload.get("enabled"))
    if "expires_at" in payload or "expires_date" in payload or "expires_time" in payload or "never_expires" in payload:
        peer.expires_at = parse_expires_from_api(payload)

    db.commit()
    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines, allow_fail=True)
    return {"ok": True, "peer": peer_basic_row(peer)}


@router.post("/api/v1/peers/{peer_id}/toggle")
def api_v1_toggle_peer(request: Request, peer_id: str, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    peer.enabled = not peer.enabled
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines, allow_fail=True)
    return {"ok": True, "peer": peer_basic_row(peer)}


@router.delete("/api/v1/peers/{peer_id}")
def api_v1_delete_peer(request: Request, peer_id: str, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    db.delete(peer)
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines, allow_fail=True)
    return {"ok": True}


@router.get("/api/v1/peers/{peer_id}/config")
def api_v1_download_config(request: Request, peer_id: str, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    if not peer.private_key:
        raise HTTPException(
            status_code=400,
            detail="Конфиг недоступен: приватный ключ отсутствует. Создайте новый конфиг в панели.",
        )

    interface_lines, interface_kv, _ = read_interface_config(controller)
    server_pub = get_server_public_key(controller)
    endpoint = ensure_endpoint(request, interface_kv)
    config_text = build_client_config(peer, interface_kv, server_pub, endpoint)

    raw_name = peer.name or peer.id
    safe_name = safe_filename(raw_name, peer.id)
    filename = f"{safe_name}.conf"
    encoded = quote(f"{raw_name}.conf")
    return Response(
        content=config_text,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/api/v1/peers/{peer_id}/qr")
def api_v1_qr_config(request: Request, peer_id: str, db=Depends(get_db), _=Depends(require_api_key)):
    import qrcode

    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    if not peer.private_key:
        raise HTTPException(
            status_code=400,
            detail="Конфиг недоступен: приватный ключ отсутствует. Создайте новый конфиг в панели.",
        )

    interface_lines, interface_kv, _ = read_interface_config(controller)
    server_pub = get_server_public_key(controller)
    endpoint = ensure_endpoint(request, interface_kv)
    config_text = build_client_config(peer, interface_kv, server_pub, endpoint)

    img = qrcode.make(config_text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.post("/peers")
def create_peer(
    request: Request,
    name: str = Form(""),
    expires_date: str = Form(""),
    expires_time: str = Form(""),
    never_expires: str = Form(""),
    tz_offset: str = Form(""),
    db=Depends(get_db),
):
    require_login(request)
    controller = awg()
    peer = build_new_peer(
        name,
        controller,
        db,
        parse_expires_from_form(expires_date, expires_time, never_expires, tz_offset),
        allow_apply_fail=True,
    )
    return RedirectResponse(with_base("/?tab=clients"), status_code=303)


@router.get("/peers/{peer_id}")
def edit_peer_page(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    expires_date = peer.expires_at.strftime("%Y-%m-%d") if peer.expires_at else ""
    expires_time = peer.expires_at.strftime("%H:%M") if peer.expires_at else ""
    expires_iso = (peer.expires_at.isoformat() + "Z") if peer.expires_at else ""
    return templates.TemplateResponse(
        request,
        "edit.html",
        template_context(
            request,
            peer=peer,
            expires_value=format_date(peer.expires_at),
            expires_date=expires_date,
            expires_time=expires_time,
            expires_iso=expires_iso,
            never_expires=peer.expires_at is None,
        ),
    )


@router.post("/peers/{peer_id}")
def edit_peer_action(
    request: Request,
    peer_id: str,
    name: str = Form(""),
    expires_date: str = Form(""),
    expires_time: str = Form(""),
    never_expires: str = Form(""),
    tz_offset: str = Form(""),
    note: str = Form(""),
    db=Depends(get_db),
):
    require_login(request)
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)

    peer.name = name.strip() or peer.name
    peer.note = note.strip() or None
    peer.expires_at = parse_expires_from_form(expires_date, expires_time, never_expires, tz_offset)
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines, allow_fail=True)
    return RedirectResponse(with_base("/?tab=clients"), status_code=303)


@router.post("/peers/{peer_id}/toggle")
def toggle_peer(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    peer.enabled = not peer.enabled
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines, allow_fail=True)
    return RedirectResponse(with_base("/"), status_code=303)


@router.post("/api/peers/{peer_id}/toggle")
def toggle_peer_api(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    peer.enabled = not peer.enabled
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines, allow_fail=True)

    status = get_peer_status(peer, utc_now())
    return {
        "ok": True,
        "enabled": peer.enabled,
        "status": status,
        "status_label": status_label(status),
    }


@router.post("/peers/{peer_id}/delete")
def delete_peer(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    db.delete(peer)
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines, allow_fail=True)
    if request.headers.get("x-requested-with") == "fetch":
        return {"ok": True}
    return RedirectResponse(with_base("/"), status_code=303)


@router.get("/peers/{peer_id}/config")
def download_config(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    if not peer.private_key:
        raise HTTPException(
            status_code=400,
            detail="Конфиг недоступен: приватный ключ отсутствует. Создайте новый конфиг в панели.",
        )

    interface_lines, interface_kv, _ = read_interface_config(controller)
    server_pub = get_server_public_key(controller)
    endpoint = ensure_endpoint(request, interface_kv)
    config_text = build_client_config(peer, interface_kv, server_pub, endpoint)

    raw_name = peer.name or peer.id
    safe_name = safe_filename(raw_name, peer.id)
    filename = f"{safe_name}.conf"
    encoded = quote(f"{raw_name}.conf")
    return Response(
        content=config_text,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/peers/{peer_id}/qr")
def qr_config(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    import qrcode

    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    if not peer.private_key:
        raise HTTPException(
            status_code=400,
            detail="Конфиг недоступен: приватный ключ отсутствует. Создайте новый конфиг в панели.",
        )

    interface_lines, interface_kv, _ = read_interface_config(controller)
    server_pub = get_server_public_key(controller)
    endpoint = ensure_endpoint(request, interface_kv)
    config_text = build_client_config(peer, interface_kv, server_pub, endpoint)

    img = qrcode.make(config_text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
