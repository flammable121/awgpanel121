from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import HTTPException, Request

from ..awg import AwgController, AwgError
from ..core import settings
from ..models import Peer
from ..utils import (
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
from .traffic import update_peer_traffic_state


def is_active(peer: Peer) -> bool:
    if not peer.enabled:
        return False
    if peer.expires_at and peer.expires_at <= utc_now():
        return False
    return True


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


def get_peer_status(peer: Peer, now: datetime) -> str:
    if peer.enabled and (not peer.expires_at or peer.expires_at > now):
        return "active"
    if peer.expires_at and peer.expires_at <= now:
        return "expired"
    return "disabled"


def parse_bool(value: Any) -> bool:
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


def _apply_tz_offset(value: datetime, tz_offset: int | None) -> datetime:
    if tz_offset is None:
        return value
    try:
        minutes = int(tz_offset)
    except (TypeError, ValueError):
        return value
    return value + timedelta(minutes=minutes)


def parse_expires_from_form(
    expires_date: str,
    expires_time: str,
    never_expires: str,
    tz_offset: str | int | None = None,
) -> datetime | None:
    if never_expires:
        return None
    expires_date = (expires_date or "").strip()
    expires_time = (expires_time or "").strip()
    if not expires_date:
        return None
    if not expires_time:
        expires_time = "00:00"
    try:
        parsed = datetime.strptime(f"{expires_date} {expires_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        parsed = parse_date(f"{expires_date} {expires_time}")
        if not parsed:
            return None
    return _apply_tz_offset(parsed, tz_offset)


def parse_expires_from_api(payload: dict[str, Any]) -> datetime | None:
    if parse_bool(payload.get("never_expires")):
        return None
    tz_offset = payload.get("tz_offset")
    if "expires_at" in payload:
        parsed = _parse_expires_value(payload.get("expires_at"))
        if not parsed:
            return None
        return _apply_tz_offset(parsed, tz_offset)
    expires_date = str(payload.get("expires_date") or "").strip()
    expires_time = str(payload.get("expires_time") or "").strip()
    if not expires_date and not expires_time:
        return None
    return parse_expires_from_form(expires_date, expires_time, "", tz_offset)


def extract_ips(allowed_ips: str) -> list[str]:
    if not allowed_ips:
        return []
    return [item.strip() for item in allowed_ips.split(",") if item.strip()]


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


def apply_config_from_db(
    db,
    controller: AwgController,
    interface_lines: list[str] | None = None,
    allow_fail: bool = False,
) -> str | None:
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
    try:
        controller.apply_config()
    except AwgError as exc:
        if allow_fail:
            message = str(exc)
            print(f"[awgpanel] apply_config warning: {message}")
            return message
        raise
    return None


def get_server_public_key(controller: AwgController) -> str:
    output = ""
    try:
        output = controller.show()
    except AwgError:
        output = ""

    for line in (output or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        lowered = raw.lower()
        if "public key" not in lowered:
            continue
        if ":" in raw:
            value = raw.split(":", 1)[1].strip()
            if value:
                return value

    # Fallback: derive from server PrivateKey in the config file.
    try:
        interface_lines, interface_kv, _ = parse_config(controller.read_config())
    except AwgError as exc:
        raise AwgError(str(exc) or "Unable to read server config") from exc

    private_key = ""
    for key, value in (interface_kv or {}).items():
        if key.strip().lower() == "privatekey":
            private_key = (value or "").strip()
            break
    if private_key:
        return controller.pubkey(private_key)

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
    if settings.client_name_key and peer.name:
        safe_name = peer.name.replace("\r", " ").replace("\n", " ").strip()
        if safe_name:
            lines.append(f"{settings.client_name_key} = {safe_name}")
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


def safe_filename(name: str, fallback: str) -> str:
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
        "expires_at": (peer.expires_at.isoformat() + "Z") if peer.expires_at else None,
        "expires_display": format_date(peer.expires_at) if peer.expires_at else "∞",
        "created_at": peer.created_at.isoformat() if peer.created_at else None,
        "public_key": peer.public_key,
        "has_private_key": bool(peer.private_key),
    }


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
            apply_config_from_db(db, controller, interface_lines, allow_fail=True)
        except AwgError:
            pass

    peers = db.query(Peer).all()
    try:
        stats = parse_awg_dump(controller.show_dump())
    except AwgError:
        stats = {}
    totals = update_peer_traffic_state(stats)

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
                "expires_at": (peer.expires_at.isoformat() + "Z") if peer.expires_at else None,
                "expires_display": format_date(peer.expires_at) if peer.expires_at else "∞",
                "created_at": peer.created_at.isoformat() if peer.created_at else None,
                "public_key": peer.public_key,
                "has_private_key": bool(peer.private_key),
                "traffic": {
                    "rx": stat.get("rx", 0),
                    "tx": stat.get("tx", 0),
                    "total": total,
                },
                "handshake": {
                    "value": stat.get("latest_handshake", 0),
                    "display": format_handshake(stat.get("latest_handshake", 0)),
                },
            }
        )

    return {
        "interface": interface_kv,
        "rows": rows,
        "server_time": int(datetime.now(tz=timezone.utc).timestamp()),
    }


def build_new_peer(
    name: str,
    controller: AwgController,
    db,
    expires_at: datetime | None,
    allow_apply_fail: bool = False,
) -> Peer:
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
        expires_at=expires_at,
        enabled=True,
        i1=i_chain.get("i1"),
        i2=i_chain.get("i2"),
        i3=i_chain.get("i3"),
        i4=i_chain.get("i4"),
        i5=i_chain.get("i5"),
    )

    db.add(peer)
    db.commit()

    apply_config_from_db(db, controller, interface_lines, allow_fail=allow_apply_fail)
    return peer
