from __future__ import annotations

import os
import platform
import subprocess
import threading
import time

import psutil
import docker
from docker.errors import NotFound as DockerNotFound, APIError as DockerAPIError
from fastapi import APIRouter, Request, HTTPException

from ..deps import require_login, awg
from ..core import settings
from ..utils import parse_awg_dump
from ..services.traffic import (
    update_traffic_state,
    reset_traffic_state,
    reset_peer_traffic_state,
    update_peer_traffic_state,
    format_bytes,
)

router = APIRouter()

psutil.cpu_percent(interval=None)

_OS_VERSION = ""
_AWG_VERSION_CACHE: dict[str, float | str] = {"value": "—", "ts": 0.0}


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


def get_awg_version(controller) -> str:
    now = time.time()
    if now - float(_AWG_VERSION_CACHE["ts"]) < 60 and _AWG_VERSION_CACHE["value"]:
        return str(_AWG_VERSION_CACHE["value"])
    try:
        value = controller.version()
    except Exception:
        value = "—"
    _AWG_VERSION_CACHE["value"] = value
    _AWG_VERSION_CACHE["ts"] = now
    return value


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


@router.get("/api/stats")
def api_stats(request: Request):
    require_login(request)
    controller = awg()
    try:
        stats = parse_awg_dump(controller.show_dump())
    except Exception:
        stats = {}
    totals = update_peer_traffic_state(stats)
    peers: list[dict[str, object]] = []
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


@router.get("/api/system")
def api_system(request: Request):
    require_login(request)
    controller = awg()

    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count(logical=False) or psutil.cpu_count() or 1

    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    uptime_seconds = int(time.time() - psutil.boot_time())

    try:
        stats = parse_awg_dump(controller.show_dump())
    except Exception:
        stats = {}
    total_rx = sum(item.get("rx", 0) for item in stats.values())
    total_tx = sum(item.get("tx", 0) for item in stats.values())
    overall_rx, overall_tx = update_traffic_state(total_rx, total_tx)
    current_total = total_rx + total_tx
    overall_total = overall_rx + overall_tx

    return {
        "cpu_percent": cpu_percent,
        "cpu_cores": cpu_cores,
        "mem_total": int(mem.total),
        "mem_used": int(mem.used),
        "mem_percent": mem.percent,
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


@router.post("/api/restart/awg")
def restart_awg(request: Request):
    require_login(request)
    _restart_container(settings.awg_container)
    return {"ok": True}


@router.post("/api/restart/panel")
def restart_panel(request: Request):
    require_login(request)
    container_name = os.environ.get("HOSTNAME") or ""
    if not container_name:
        raise HTTPException(status_code=500, detail="Panel container name not found")
    _restart_container(container_name)
    return {"ok": True}


@router.post("/api/restart/server")
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


@router.post("/api/traffic/reset")
def reset_traffic(request: Request):
    require_login(request)
    controller = awg()
    try:
        stats = parse_awg_dump(controller.show_dump())
    except Exception:
        stats = {}
    total_rx = sum(item.get("rx", 0) for item in stats.values())
    total_tx = sum(item.get("tx", 0) for item in stats.values())
    reset_traffic_state(total_rx, total_tx)
    reset_peer_traffic_state(stats)
    return {"ok": True}
