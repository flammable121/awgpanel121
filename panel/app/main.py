from __future__ import annotations

import io
import hmac
import platform
import os
import re
import time
import json
import secrets
import subprocess
import threading
from urllib.parse import quote
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request, Depends, Form, HTTPException, Header
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import psutil
import docker
from docker.errors import NotFound as DockerNotFound, APIError as DockerAPIError

from .config import get_settings
from .db import SessionLocal, init_db
from .models import Peer
from .awg import AwgController, AwgError
from .utils import (
    parse_config,
    parse_kv,
    build_config,
    parse_awg_dump,
    utc_now,
    parse_date,
    pick_next_ip,
    generate_i_chain,
    format_date,
)

settings = get_settings()


def _normalize_base_path(value: str) -> str:
    base = (value or "").strip()
    if not base or base == "/":
        return ""
    if not base.startswith("/"):
        base = "/" + base
    return base.rstrip("/")


_BASE_PATH = _normalize_base_path(settings.panel_base_path)


def with_base(path: str) -> str:
    if not _BASE_PATH:
        return path
    if not path.startswith("/"):
        path = "/" + path
    return f"{_BASE_PATH}{path}"


def template_context(request: Request, **extra: Any) -> dict[str, Any]:
    ctx = {"request": request, "base_path": _BASE_PATH}
    ctx.update(extra)
    return ctx

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=60 * 60 * 24 * 7)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

psutil.cpu_percent(interval=None)
_OS_VERSION = ""
_AWG_VERSION_CACHE: dict[str, Any] = {"value": "—", "ts": 0.0}
_TRAFFIC_STATE_FILE = os.path.join(settings.data_dir, "traffic_state.json")
_PEER_TRAFFIC_STATE_FILE = os.path.join(settings.data_dir, "peer_traffic.json")


def _load_peer_traffic_state() -> dict[str, Any]:
    try:
        with open(_PEER_TRAFFIC_STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, TypeError):
        return {"peers": {}}
    if not isinstance(data, dict):
        return {"peers": {}}
    peers = data.get("peers", {})
    if not isinstance(peers, dict):
        peers = {}
    for key, info in list(peers.items()):
        if not isinstance(info, dict):
            peers.pop(key, None)
            continue
        for field in ("offset_rx", "offset_tx", "last_rx", "last_tx"):
            try:
                info[field] = int(info.get(field, 0))
            except (TypeError, ValueError):
                info[field] = 0
    return {"peers": peers}


def _save_peer_traffic_state(state: dict[str, Any]) -> None:
    os.makedirs(settings.data_dir, exist_ok=True)
    with open(_PEER_TRAFFIC_STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def _update_peer_traffic_state(stats: dict[str, dict[str, Any]]) -> dict[str, dict[str, int]]:
    state = _load_peer_traffic_state()
    peers_state: dict[str, dict[str, int]] = state.get("peers", {})
    for pub, stat in stats.items():
        cur_rx = int(stat.get("rx", 0))
        cur_tx = int(stat.get("tx", 0))
        info = peers_state.get(pub, {})
        last_rx = int(info.get("last_rx", 0))
        last_tx = int(info.get("last_tx", 0))
        offset_rx = int(info.get("offset_rx", 0))
        offset_tx = int(info.get("offset_tx", 0))
        if cur_rx < last_rx or cur_tx < last_tx:
            offset_rx += last_rx
            offset_tx += last_tx
        info["offset_rx"] = offset_rx
        info["offset_tx"] = offset_tx
        info["last_rx"] = cur_rx
        info["last_tx"] = cur_tx
        peers_state[pub] = info

    state["peers"] = peers_state
    _save_peer_traffic_state(state)

    totals: dict[str, dict[str, int]] = {}
    for pub, info in peers_state.items():
        total_rx = int(info.get("offset_rx", 0)) + int(info.get("last_rx", 0))
        total_tx = int(info.get("offset_tx", 0)) + int(info.get("last_tx", 0))
        totals[pub] = {"rx": total_rx, "tx": total_tx, "total": total_rx + total_tx}
    return totals


def _reset_peer_traffic_state(stats: dict[str, dict[str, Any]]) -> None:
    state = _load_peer_traffic_state()
    peers_state: dict[str, dict[str, int]] = state.get("peers", {})
    for pub, info in peers_state.items():
        last_rx = int(info.get("last_rx", 0))
        last_tx = int(info.get("last_tx", 0))
        info["offset_rx"] = -last_rx
        info["offset_tx"] = -last_tx
        peers_state[pub] = info
    for pub, stat in stats.items():
        cur_rx = int(stat.get("rx", 0))
        cur_tx = int(stat.get("tx", 0))
        peers_state[pub] = {
            "offset_rx": -cur_rx,
            "offset_tx": -cur_tx,
            "last_rx": cur_rx,
            "last_tx": cur_tx,
        }
    state["peers"] = peers_state
    _save_peer_traffic_state(state)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_login(request: Request) -> None:
    if not request.session.get("user"):
        raise HTTPException(status_code=303, headers={"Location": with_base("/login")})


def awg() -> AwgController:
    return AwgController(settings)


def is_active(peer: Peer) -> bool:
    if not peer.enabled:
        return False
    if peer.expires_at and peer.expires_at <= utc_now():
        return False
    return True


def _to_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if value is None:
        return b""
    return str(value).encode("utf-8")


def verify_password(candidate: str) -> bool:
    return hmac.compare_digest(_to_bytes(candidate), _to_bytes(settings.admin_pass))


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


_SECRETS_LOCK = threading.Lock()


def secrets_file_path() -> str:
    path = os.getenv("PANEL_SECRETS_PATH")
    if path:
        return path
    return os.path.join(settings.data_dir, "secrets.json")


def load_secrets_file() -> dict[str, Any]:
    path = secrets_file_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {}


def save_secrets_file(data: dict[str, Any]) -> None:
    path = secrets_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def update_secrets_file(values: dict[str, Any]) -> dict[str, Any]:
    with _SECRETS_LOCK:
        data = load_secrets_file()
        data.update(values)
        save_secrets_file(data)
    return data


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_expires_value(value: Any) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        try:
            return datetime.fromtimestamp(int(raw))
        except (ValueError, OSError):
            return None
    raw = raw.replace("T", " ").replace("Z", "").strip()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    return parse_date(raw)


def parse_expires_from_api(payload: dict[str, Any]) -> datetime | None:
    if _parse_bool(payload.get("never_expires")):
        return None
    if "expires_at" in payload:
        return _parse_expires_value(payload.get("expires_at"))
    expires_date = str(payload.get("expires_date") or "").strip()
    expires_time = str(payload.get("expires_time") or "").strip()
    if not expires_date and not expires_time:
        return None
    return parse_expires_from_form(expires_date, expires_time, "")


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _load_traffic_state() -> dict[str, int]:
    defaults = {
        "overall_offset_rx": 0,
        "overall_offset_tx": 0,
        "last_rx": 0,
        "last_tx": 0,
    }
    try:
        with open(_TRAFFIC_STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for key in defaults:
            if key in data:
                defaults[key] = int(data[key])
    except (OSError, ValueError, TypeError):
        pass
    return defaults


def _save_traffic_state(state: dict[str, int]) -> None:
    os.makedirs(settings.data_dir, exist_ok=True)
    with open(_TRAFFIC_STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def _update_traffic_state(current_rx: int, current_tx: int) -> tuple[int, int]:
    state = _load_traffic_state()
    last_rx = int(state.get("last_rx", 0))
    last_tx = int(state.get("last_tx", 0))
    if current_rx < last_rx or current_tx < last_tx:
        state["overall_offset_rx"] = int(state.get("overall_offset_rx", 0)) + last_rx
        state["overall_offset_tx"] = int(state.get("overall_offset_tx", 0)) + last_tx
    state["last_rx"] = current_rx
    state["last_tx"] = current_tx
    _save_traffic_state(state)
    overall_rx = int(state.get("overall_offset_rx", 0)) + current_rx
    overall_tx = int(state.get("overall_offset_tx", 0)) + current_tx
    return overall_rx, overall_tx


def _reset_traffic_state(current_rx: int, current_tx: int) -> None:
    state = _load_traffic_state()
    state["overall_offset_rx"] = -current_rx
    state["overall_offset_tx"] = -current_tx
    state["last_rx"] = current_rx
    state["last_tx"] = current_tx
    _save_traffic_state(state)


def update_interface_lines(interface_lines: list[str], updates: dict[str, str]) -> list[str]:
    if not interface_lines:
        interface_lines = ["[Interface]"]
    indices: dict[str, int] = {}
    for idx, raw in enumerate(interface_lines):
        kv = parse_kv(raw.strip())
        if kv:
            indices[kv[0].lower()] = idx

    for key, value in updates.items():
        lowered = key.lower()
        if value is None or value == "":
            if lowered in indices:
                interface_lines[indices[lowered]] = None
            continue
        line = f"{key} = {value}"
        if lowered in indices:
            interface_lines[indices[lowered]] = line
        else:
            interface_lines.append(line)

    return [line for line in interface_lines if line is not None]


def format_handshake(value: int) -> str:
    if value <= 0:
        return "never"
    dt = datetime.fromtimestamp(value, tz=timezone.utc)
    return dt.strftime("%d.%m.%y %H:%M UTC")


def status_label(status: str) -> str:
    labels = {
        "active": "Активен",
        "disabled": "Отключен",
        "expired": "Истек",
    }
    return labels.get(status, status)


def read_os_version() -> str:
    global _OS_VERSION
    if _OS_VERSION:
        return _OS_VERSION
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as fh:
            data = fh.read().splitlines()
        values = {}
        for line in data:
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"')
        name = values.get("PRETTY_NAME") or values.get("NAME") or "Linux"
        _OS_VERSION = name
        return _OS_VERSION
    except OSError:
        _OS_VERSION = platform.platform()
        return _OS_VERSION


def get_awg_version(controller: AwgController) -> str:
    now = time.time()
    if now - _AWG_VERSION_CACHE["ts"] < 60 and _AWG_VERSION_CACHE["value"]:
        return _AWG_VERSION_CACHE["value"]
    try:
        value = controller.version()
    except AwgError:
        value = "—"
    _AWG_VERSION_CACHE["value"] = value
    _AWG_VERSION_CACHE["ts"] = now
    return value


def get_peer_status(peer: Peer, now: datetime) -> str:
    if peer.enabled and (not peer.expires_at or peer.expires_at > now):
        return "active"
    if peer.expires_at and peer.expires_at <= now:
        return "expired"
    return "disabled"


def parse_expires_from_form(expires_date: str, expires_time: str, never_expires: str) -> datetime | None:
    if never_expires:
        return None
    expires_date = (expires_date or "").strip()
    expires_time = (expires_time or "").strip()
    if not expires_date:
        return None
    if not expires_time:
        expires_time = "00:00"
    try:
        return datetime.strptime(f"{expires_date} {expires_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return parse_date(f"{expires_date} {expires_time}")


def extract_ips(allowed_ips: str) -> list[str]:
    if not allowed_ips:
        return []
    return [item.strip() for item in allowed_ips.split(",") if item.strip()]


def sync_db_from_config(
    db, controller: AwgController
) -> tuple[list[str], dict[str, str], list[dict[str, dict[str, str]]]]:
    text = controller.read_config()
    interface_lines, interface_kv, peers_cfg = parse_config(text)

    for peer_cfg in peers_cfg:
        kv = peer_cfg["kv"]
        pub = kv.get("PublicKey")
        if not pub:
            continue
        peer = db.query(Peer).filter_by(public_key=pub).first()
        if not peer:
            peer = Peer(
                name=f"peer-{pub[:6]}",
                public_key=pub,
                allowed_ips=kv.get("AllowedIPs", ""),
                enabled=True,
            )
            db.add(peer)
        else:
            allowed = kv.get("AllowedIPs")
            if allowed and peer.allowed_ips != allowed:
                peer.allowed_ips = allowed
    db.commit()
    return interface_lines, interface_kv, peers_cfg


def read_interface_config(
    controller: AwgController,
) -> tuple[list[str], dict[str, str], list[dict[str, dict[str, str]]]]:
    text = controller.read_config()
    return parse_config(text)


def apply_config_from_db(db, controller: AwgController, interface_lines: list[str] | None = None) -> None:
    if interface_lines is None:
        interface_lines, _, _ = parse_config(controller.read_config())

    peers = db.query(Peer).all()
    active_peers: list[dict[str, str]] = []
    for peer in peers:
        if not is_active(peer):
            continue
        active_peers.append(
            {
                "public_key": peer.public_key,
                "preshared_key": peer.preshared_key or "",
                "allowed_ips": peer.allowed_ips,
            }
        )

    new_config = build_config(interface_lines, active_peers)
    controller.write_config(new_config)
    controller.apply_config()


def get_server_public_key(controller: AwgController) -> str:
    output = controller.show()
    for line in output.splitlines():
        if line.strip().startswith("public key:"):
            return line.split(":", 1)[1].strip()
    raise AwgError("Unable to read server public key")


def get_listen_port(interface_kv: dict[str, str]) -> str:
    for key, value in interface_kv.items():
        if key.lower() == "listenport":
            return value
    return "51820"


def get_param(interface_kv: dict[str, str], name: str) -> str | None:
    for key, value in interface_kv.items():
        if key.lower() == name.lower():
            return value
    return None


def build_client_config(
    peer: Peer,
    interface_kv: dict[str, str],
    server_public_key: str,
    endpoint: str,
) -> str:
    if not peer.private_key:
        raise AwgError("Private key is missing for this peer")

    lines: list[str] = ["[Interface]"]
    lines.append(f"PrivateKey = {peer.private_key}")
    lines.append(f"Address = {peer.allowed_ips}")

    dns = peer.client_dns or settings.default_client_dns
    if dns:
        lines.append(f"DNS = {dns}")

    for key in ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4"]:
        value = get_param(interface_kv, key)
        if value:
            lines.append(f"{key} = {value}")

    if peer.i1:
        lines.append(f"I1 = {peer.i1}")
    if peer.i2:
        lines.append(f"I2 = {peer.i2}")
    if peer.i3:
        lines.append(f"I3 = {peer.i3}")
    if peer.i4:
        lines.append(f"I4 = {peer.i4}")
    if peer.i5:
        lines.append(f"I5 = {peer.i5}")

    lines.append("")
    lines.append("[Peer]")
    lines.append(f"PublicKey = {server_public_key}")
    if peer.preshared_key:
        lines.append(f"PresharedKey = {peer.preshared_key}")
    lines.append(f"Endpoint = {endpoint}")
    lines.append(f"AllowedIPs = {peer.client_allowed_ips or settings.default_client_allowed_ips}")
    lines.append("PersistentKeepalive = 25")

    return "\n".join(lines).rstrip() + "\n"


def _safe_filename(name: str, fallback: str) -> str:
    base = (name or "").strip()
    if not base:
        base = fallback
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")
    return safe or fallback


def ensure_endpoint(request: Request, interface_kv: dict[str, str]) -> str:
    if settings.public_endpoint:
        return settings.public_endpoint
    host = request.url.hostname or "localhost"
    port = get_listen_port(interface_kv)
    return f"{host}:{port}"


def build_peers_payload(db, controller: AwgController) -> dict[str, Any]:
    try:
        interface_lines, interface_kv, _ = sync_db_from_config(db, controller)
    except AwgError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    now = utc_now()
    expired_updates = False
    peers_all = db.query(Peer).all()
    for peer in peers_all:
        if peer.enabled and peer.expires_at and peer.expires_at <= now:
            peer.enabled = False
            expired_updates = True
    if expired_updates:
        db.commit()
        try:
            apply_config_from_db(db, controller, interface_lines)
        except AwgError:
            pass

    peers = db.query(Peer).all()
    try:
        stats = parse_awg_dump(controller.show_dump())
    except AwgError:
        stats = {}
    totals = _update_peer_traffic_state(stats)

    rows: list[dict[str, Any]] = []
    for peer in peers:
        stat = stats.get(peer.public_key, {})
        status = get_peer_status(peer, now)
        total_info = totals.get(peer.public_key)
        total = total_info["total"] if total_info else stat.get("rx", 0) + stat.get("tx", 0)
        rows.append(
            {
                "id": peer.id,
                "name": peer.name,
                "note": peer.note,
                "allowed_ips": peer.allowed_ips,
                "client_allowed_ips": peer.client_allowed_ips,
                "client_dns": peer.client_dns,
                "enabled": peer.enabled,
                "status": status,
                "status_label": status_label(status),
                "expires_at": peer.expires_at.isoformat() if peer.expires_at else None,
                "expires_display": format_date(peer.expires_at) if peer.expires_at else "∞",
                "expires_sort": int(peer.expires_at.timestamp()) if peer.expires_at else 32503680000,
                "created_at": peer.created_at.isoformat() if peer.created_at else None,
                "public_key": peer.public_key,
                "has_private_key": bool(peer.private_key),
                "traffic_display": format_bytes(total),
                "traffic_total": total,
            }
        )

    return {"peers": rows, "interface": interface_kv}


def peer_basic_row(peer: Peer) -> dict[str, Any]:
    status = get_peer_status(peer, utc_now())
    return {
        "id": peer.id,
        "name": peer.name,
        "note": peer.note,
        "allowed_ips": peer.allowed_ips,
        "client_allowed_ips": peer.client_allowed_ips,
        "client_dns": peer.client_dns,
        "enabled": peer.enabled,
        "status": status,
        "status_label": status_label(status),
        "expires_at": peer.expires_at.isoformat() if peer.expires_at else None,
        "expires_display": format_date(peer.expires_at) if peer.expires_at else "∞",
        "created_at": peer.created_at.isoformat() if peer.created_at else None,
        "public_key": peer.public_key,
        "has_private_key": bool(peer.private_key),
    }


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", template_context(request))


@app.post("/login")
def login_action(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
):
    if username == settings.admin_user and verify_password(password):
        request.session["user"] = username
        return RedirectResponse(with_base("/"), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        template_context(request, error="Неверные данные"),
    )


@app.post("/logout")
def logout_action(request: Request):
    request.session.clear()
    return RedirectResponse(with_base("/login"), status_code=303)


@app.get("/")
def index(request: Request):
    require_login(request)
    return templates.TemplateResponse(request, "index.html", template_context(request))


@app.get("/api/peers")
def api_peers(request: Request, db=Depends(get_db)):
    require_login(request)
    controller = awg()
    return build_peers_payload(db, controller)


@app.get("/api/api-info")
def api_info(request: Request):
    require_login(request)
    origin = f"{request.url.scheme}://{request.url.netloc}"
    base_url = f"{origin}{_BASE_PATH}" if _BASE_PATH else origin
    return {
        "api_token": settings.api_token or "",
        "base_url": base_url,
        "base_path": _BASE_PATH,
    }


@app.post("/api/api-token/reset")
def api_token_reset(request: Request):
    require_login(request)
    token = secrets.token_hex(24)
    update_secrets_file({"API_TOKEN": token})
    settings.api_token = token
    return {"ok": True, "api_token": token}


@app.get("/api/awg/settings")
def api_awg_settings(request: Request):
    require_login(request)
    return {
        "public_endpoint": settings.public_endpoint or "",
        "default_client_allowed_ips": settings.default_client_allowed_ips,
        "default_client_dns": settings.default_client_dns or "",
    }


@app.post("/api/awg/settings")
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


@app.get("/api/v1/peers")
def api_v1_peers(request: Request, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    return build_peers_payload(db, controller)


@app.get("/api/v1/peers/{peer_id}")
def api_v1_peer(request: Request, peer_id: str, db=Depends(get_db), _=Depends(require_api_key)):
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    return {"peer": peer_basic_row(peer)}


@app.post("/api/v1/peers")
async def api_v1_create_peer(request: Request, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    interface_lines, interface_kv, peers_cfg = read_interface_config(controller)

    priv = controller.genkey()
    pub = controller.pubkey(priv)
    psk = controller.genpsk()

    used_ips: set[str] = set()
    for peer in db.query(Peer).all():
        for ip in extract_ips(peer.allowed_ips):
            used_ips.add(ip.split("/")[0])
    for peer_cfg in peers_cfg:
        allowed_cfg = peer_cfg["kv"].get("AllowedIPs", "")
        for ip in extract_ips(allowed_cfg):
            used_ips.add(ip.split("/")[0])
    address_raw = get_param(interface_kv, "Address") or "10.8.1.0/24"
    address = address_raw.split(",")[0].strip()
    server_ip = address.split("/")[0]
    used_ips.add(server_ip)
    allowed = pick_next_ip(address, used_ips)

    i_chain = generate_i_chain()

    name = str(payload.get("name") or "").strip()
    client_allowed_ips = str(payload.get("client_allowed_ips") or "").strip() or settings.default_client_allowed_ips
    client_dns = str(payload.get("client_dns") or "").strip() or settings.default_client_dns
    note = str(payload.get("note") or "").strip() or None
    enabled = _parse_bool(payload.get("enabled")) if "enabled" in payload else True
    expires_at = parse_expires_from_api(payload)

    peer = Peer(
        name=name or f"peer-{pub[:6]}",
        public_key=pub,
        private_key=priv,
        preshared_key=psk,
        allowed_ips=allowed,
        client_allowed_ips=client_allowed_ips,
        client_dns=client_dns,
        note=note,
        expires_at=expires_at,
        enabled=enabled,
        i1=i_chain.get("i1"),
        i2=i_chain.get("i2"),
        i3=i_chain.get("i3"),
        i4=i_chain.get("i4"),
        i5=i_chain.get("i5"),
    )
    db.add(peer)
    db.commit()

    apply_config_from_db(db, controller, interface_lines)
    return {"ok": True, "peer": peer_basic_row(peer)}


@app.patch("/api/v1/peers/{peer_id}")
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
        peer.enabled = _parse_bool(payload.get("enabled"))
    if "expires_at" in payload or "expires_date" in payload or "expires_time" in payload or "never_expires" in payload:
        peer.expires_at = parse_expires_from_api(payload)

    db.commit()
    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines)
    return {"ok": True, "peer": peer_basic_row(peer)}


@app.post("/api/v1/peers/{peer_id}/toggle")
def api_v1_toggle_peer(request: Request, peer_id: str, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    peer.enabled = not peer.enabled
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines)
    return {"ok": True, "peer": peer_basic_row(peer)}


@app.delete("/api/v1/peers/{peer_id}")
def api_v1_delete_peer(request: Request, peer_id: str, db=Depends(get_db), _=Depends(require_api_key)):
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    db.delete(peer)
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines)
    return {"ok": True}


@app.get("/api/v1/peers/{peer_id}/config")
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
    safe_name = _safe_filename(raw_name, peer.id)
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


@app.get("/api/v1/peers/{peer_id}/qr")
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


@app.post("/peers")
def create_peer(
    request: Request,
    name: str = Form(""),
    expires_date: str = Form(""),
    expires_time: str = Form(""),
    never_expires: str = Form(""),
    db=Depends(get_db),
):
    require_login(request)
    controller = awg()
    interface_lines, interface_kv, peers_cfg = read_interface_config(controller)

    priv = controller.genkey()
    pub = controller.pubkey(priv)
    psk = controller.genpsk()

    used_ips: set[str] = set()
    for peer in db.query(Peer).all():
        for ip in extract_ips(peer.allowed_ips):
            used_ips.add(ip.split("/")[0])
    for peer_cfg in peers_cfg:
        allowed_cfg = peer_cfg["kv"].get("AllowedIPs", "")
        for ip in extract_ips(allowed_cfg):
            used_ips.add(ip.split("/")[0])
    address_raw = get_param(interface_kv, "Address") or "10.8.1.0/24"
    address = address_raw.split(",")[0].strip()
    server_ip = address.split("/")[0]
    used_ips.add(server_ip)
    allowed = pick_next_ip(address, used_ips)

    i_chain = generate_i_chain()

    peer = Peer(
        name=name.strip() or f"peer-{pub[:6]}",
        public_key=pub,
        private_key=priv,
        preshared_key=psk,
        allowed_ips=allowed,
        client_allowed_ips=settings.default_client_allowed_ips,
        client_dns=settings.default_client_dns,
        note=None,
        expires_at=parse_expires_from_form(expires_date, expires_time, never_expires),
        enabled=True,
        i1=i_chain.get("i1"),
        i2=i_chain.get("i2"),
        i3=i_chain.get("i3"),
        i4=i_chain.get("i4"),
        i5=i_chain.get("i5"),
    )
    db.add(peer)
    db.commit()

    apply_config_from_db(db, controller, interface_lines)
    return RedirectResponse(with_base("/?tab=clients"), status_code=303)


@app.get("/peers/{peer_id}")
def edit_peer_page(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    expires_date = peer.expires_at.strftime("%Y-%m-%d") if peer.expires_at else ""
    expires_time = peer.expires_at.strftime("%H:%M") if peer.expires_at else ""
    return templates.TemplateResponse(
        request,
        "edit.html",
        template_context(
            request,
            peer=peer,
            expires_value=format_date(peer.expires_at),
            expires_date=expires_date,
            expires_time=expires_time,
            never_expires=peer.expires_at is None,
        ),
    )


@app.post("/peers/{peer_id}")
def edit_peer_action(
    request: Request,
    peer_id: str,
    name: str = Form(""),
    expires_date: str = Form(""),
    expires_time: str = Form(""),
    never_expires: str = Form(""),
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
    peer.expires_at = parse_expires_from_form(expires_date, expires_time, never_expires)
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines)
    return RedirectResponse(with_base("/"), status_code=303)


@app.post("/peers/{peer_id}/toggle")
def toggle_peer(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    peer.enabled = not peer.enabled
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines)
    return RedirectResponse(with_base("/"), status_code=303)


@app.post("/api/peers/{peer_id}/toggle")
def toggle_peer_api(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    peer.enabled = not peer.enabled
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines)

    now = utc_now()
    status = get_peer_status(peer, now)
    return {
        "ok": True,
        "enabled": peer.enabled,
        "status": status,
        "status_label": status_label(status),
    }




@app.get("/api/stats")
def api_stats(request: Request):
    require_login(request)
    controller = awg()
    try:
        stats = parse_awg_dump(controller.show_dump())
    except AwgError:
        stats = {}
    totals = _update_peer_traffic_state(stats)
    peers: list[dict[str, Any]] = []
    for pub, stat in stats.items():
        total_info = totals.get(pub)
        total = total_info["total"] if total_info else stat.get("rx", 0) + stat.get("tx", 0)
        peers.append(
            {
                "public_key": pub,
                "rx": stat.get("rx", 0),
                "tx": stat.get("tx", 0),
                "total": total,
                "total_display": format_bytes(total),
                "latest_handshake": stat.get("latest_handshake", 0),
            }
        )
    return {"peers": peers, "server_time": int(time.time())}


@app.get("/api/system")
def api_system(request: Request):
    require_login(request)
    controller = awg()

    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    uptime_seconds = int(time.time() - psutil.boot_time())

    try:
        stats = parse_awg_dump(controller.show_dump())
    except AwgError:
        stats = {}
    total_rx = sum(item.get("rx", 0) for item in stats.values())
    total_tx = sum(item.get("tx", 0) for item in stats.values())
    overall_rx, overall_tx = _update_traffic_state(total_rx, total_tx)
    current_total = total_rx + total_tx
    overall_total = overall_rx + overall_tx

    return {
        "cpu_percent": cpu_percent,
        "cpu_cores": cpu_cores,
        "mem_total": int(mem.total),
        "mem_used": int(mem.used),
        "mem_percent": mem.percent,
        "swap_total": int(swap.total),
        "swap_used": int(swap.used),
        "swap_percent": swap.percent,
        "disk_total": int(disk.total),
        "disk_used": int(disk.used),
        "disk_percent": disk.percent,
        "uptime_seconds": uptime_seconds,
        "os_version": read_os_version(),
        "awg_version": get_awg_version(controller),
        "current_rx": total_rx,
        "current_tx": total_tx,
        "current_total": current_total,
        "current_rx_display": format_bytes(total_rx),
        "current_tx_display": format_bytes(total_tx),
        "current_total_display": format_bytes(current_total),
        "overall_rx": overall_rx,
        "overall_tx": overall_tx,
        "overall_total": overall_total,
        "overall_rx_display": format_bytes(overall_rx),
        "overall_tx_display": format_bytes(overall_tx),
        "overall_total_display": format_bytes(overall_total),
    }


@app.get("/api/awg/params")
def api_awg_params(request: Request):
    require_login(request)
    controller = awg()
    interface_lines, interface_kv, _ = read_interface_config(controller)
    keys = ["Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4"]
    params = {key: interface_kv.get(key, "") for key in keys}
    return {"params": params}


@app.post("/api/awg/params")
async def api_awg_params_update(request: Request, db=Depends(get_db)):
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
    apply_config_from_db(db, controller, interface_lines)

    _, interface_kv, _ = read_interface_config(controller)
    params = {key: interface_kv.get(key, "") for key in keys}
    return {"ok": True, "params": params}


@app.get("/api/awg/i-chain")
def api_awg_i_chain(request: Request):
    require_login(request)
    return generate_i_chain()


def _restart_container(name: str) -> None:
    client = docker.from_env()
    try:
        container = client.containers.get(name)
    except DockerNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Container not found: {name}") from exc
    try:
        container.restart()
    except DockerAPIError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _restart_server() -> None:
    commands = [
        ["/sbin/reboot"],
        ["reboot"],
        ["shutdown", "-r", "now"],
    ]
    last_error: Exception | None = None
    for cmd in commands:
        try:
            subprocess.run(cmd, check=True)
            return
        except FileNotFoundError as exc:
            last_error = exc
            continue
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Fallback: trigger host reboot via a privileged helper container.
    # Requires Docker socket access (mounted in compose).
    client = docker.from_env()
    images = ["busybox:1.36", "alpine:3.20"]
    for image in images:
        try:
            client.containers.run(
                image=image,
                command=["/sbin/reboot", "-f"],
                remove=True,
                privileged=True,
                pid_mode="host",
                network_mode="host",
            )
            return
        except DockerAPIError as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            continue

    raise HTTPException(status_code=500, detail=str(last_error or "reboot failed"))


@app.post("/api/restart/awg")
def restart_awg(request: Request):
    require_login(request)
    _restart_container(settings.awg_container)
    return {"ok": True}


@app.post("/api/restart/panel")
def restart_panel(request: Request):
    require_login(request)
    container_name = os.environ.get("HOSTNAME") or ""
    if not container_name:
        raise HTTPException(status_code=500, detail="Panel container name not found")
    _restart_container(container_name)
    return {"ok": True}


@app.post("/api/restart/server")
def restart_server(request: Request):
    require_login(request)
    def _bg_restart() -> None:
        try:
            time.sleep(1.0)
            _restart_server()
        except Exception as exc:
            print(f"restart server failed: {exc}")

    threading.Thread(target=_bg_restart, daemon=True).start()
    return {"ok": True, "queued": True}


@app.post("/api/traffic/reset")
def reset_traffic(request: Request):
    require_login(request)
    controller = awg()
    try:
        stats = parse_awg_dump(controller.show_dump())
    except AwgError:
        stats = {}
    total_rx = sum(item.get("rx", 0) for item in stats.values())
    total_tx = sum(item.get("tx", 0) for item in stats.values())
    _reset_traffic_state(total_rx, total_tx)
    _reset_peer_traffic_state(stats)
    return {"ok": True}


@app.post("/peers/{peer_id}/delete")
def delete_peer(request: Request, peer_id: str, db=Depends(get_db)):
    require_login(request)
    controller = awg()
    peer = db.query(Peer).filter_by(id=peer_id).first()
    if not peer:
        raise HTTPException(status_code=404)
    db.delete(peer)
    db.commit()

    interface_lines, _, _ = read_interface_config(controller)
    apply_config_from_db(db, controller, interface_lines)
    return RedirectResponse(with_base("/"), status_code=303)


@app.get("/peers/{peer_id}/config")
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
    safe_name = _safe_filename(raw_name, peer.id)
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


@app.get("/peers/{peer_id}/qr")
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
