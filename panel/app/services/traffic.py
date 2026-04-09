from __future__ import annotations

import json
import os
from typing import Any

from ..core import settings

_TRAFFIC_STATE_FILE = os.path.join(settings.data_dir, "traffic_state.json")
_PEER_TRAFFIC_STATE_FILE = os.path.join(settings.data_dir, "peer_traffic.json")


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


def update_traffic_state(current_rx: int, current_tx: int) -> tuple[int, int]:
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


def reset_traffic_state(current_rx: int, current_tx: int) -> None:
    state = _load_traffic_state()
    state["overall_offset_rx"] = -current_rx
    state["overall_offset_tx"] = -current_tx
    state["last_rx"] = current_rx
    state["last_tx"] = current_tx
    _save_traffic_state(state)


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


def update_peer_traffic_state(stats: dict[str, dict[str, Any]]) -> dict[str, dict[str, int]]:
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


def reset_peer_traffic_state(stats: dict[str, dict[str, Any]]) -> None:
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
