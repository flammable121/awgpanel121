from __future__ import annotations

import ipaddress
import random
import secrets
from datetime import datetime


def parse_kv(line: str) -> tuple[str, str] | None:
    if not line or line.startswith("#") or line.startswith(";"):
        return None
    if "=" not in line:
        return None
    key, value = line.split("=", 1)
    return key.strip(), value.strip()


def parse_config(text: str) -> tuple[list[str], dict[str, str], list[dict[str, dict[str, str]]]]:
    interface_lines: list[str] = []
    interface_kv: dict[str, str] = {}
    peers: list[dict[str, dict[str, str]]] = []

    section: str | None = None
    current_peer: dict[str, dict[str, str]] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.lower() == "[interface]":
            section = "interface"
            interface_lines.append(raw_line)
            continue
        if line.lower() == "[peer]":
            section = "peer"
            current_peer = {"kv": {}, "lines": [raw_line]}
            peers.append(current_peer)
            continue

        if section == "interface":
            interface_lines.append(raw_line)
            kv = parse_kv(line)
            if kv:
                interface_kv[kv[0]] = kv[1]
        elif section == "peer" and current_peer is not None:
            current_peer["lines"].append(raw_line)
            kv = parse_kv(line)
            if kv:
                current_peer["kv"][kv[0]] = kv[1]

    return interface_lines, interface_kv, peers


def build_config(interface_lines: list[str], peers: list[dict[str, str]]) -> str:
    lines: list[str] = []
    if interface_lines:
        lines.extend(interface_lines)
    else:
        lines.append("[Interface]")

    for peer in peers:
        lines.append("")
        lines.append("[Peer]")
        lines.append(f"PublicKey = {peer['public_key']}")
        if peer.get("preshared_key"):
            lines.append(f"PresharedKey = {peer['preshared_key']}")
        lines.append(f"AllowedIPs = {peer['allowed_ips']}")
        if peer.get("persistent_keepalive"):
            lines.append(f"PersistentKeepalive = {peer['persistent_keepalive']}")

    return "\n".join(lines).rstrip() + "\n"


def _is_pubkey(value: str) -> bool:
    if not value:
        return False
    if len(value) < 40 or len(value) > 64:
        return False
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    return all(ch in allowed for ch in value)


def _to_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_awg_dump(text: str) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) == 1:
            parts = line.split()
        peer_pub = ""
        latest = rx = tx = 0

        if len(parts) >= 9 and _is_pubkey(parts[1]):
            peer_pub = parts[1]
            latest = _to_int(parts[5])
            rx = _to_int(parts[6])
            tx = _to_int(parts[7])
        elif len(parts) >= 13 and _is_pubkey(parts[5]):
            peer_pub = parts[5]
            latest = _to_int(parts[9])
            rx = _to_int(parts[10])
            tx = _to_int(parts[11])
        else:
            continue

        if peer_pub == "(none)":
            continue
        stats[peer_pub] = {
            "latest_handshake": latest,
            "rx": rx,
            "tx": tx,
        }
    return stats


def utc_now() -> datetime:
    return datetime.utcnow()


def parse_date(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%d.%m.%y %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def format_date(value: datetime | None) -> str:
    if not value:
        return ""
    return value.strftime("%d.%m.%y %H:%M")


def pick_next_ip(cidr: str, used_ips: set[str]) -> str:
    return pick_next_ips(cidr, used_ips, 1)[0]


def pick_next_ips(cidr: str, used_ips: set[str], count: int) -> list[str]:
    net = ipaddress.ip_network(cidr, strict=False)
    picked: list[str] = []
    for ip in net.hosts():
        if str(ip) in used_ips:
            continue
        picked.append(f"{ip}/32")
        used_ips.add(str(ip))
        if len(picked) >= count:
            return picked
    raise RuntimeError("No free IPs in subnet")


def generate_cps_packet() -> str:
    b_len = random.randint(8, 20)
    b = secrets.token_bytes(b_len).hex()
    rc_len = random.randint(4, 12)
    r_len = random.randint(10, 40)
    return f"<b 0x{b}><rc {rc_len}><t><r {r_len}>"


def generate_i_chain() -> dict[str, str]:
    return {
        "i1": generate_cps_packet(),
        "i2": generate_cps_packet(),
        "i3": generate_cps_packet(),
        "i4": generate_cps_packet(),
        "i5": generate_cps_packet(),
    }
