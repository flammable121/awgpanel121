from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.request
from typing import Any

import docker
from docker.errors import DockerException
from docker.types import Mount

from ..core import settings
from ..geodat import load_geoip_cidrs, load_geoip_tags, load_geosite_domains, load_geosite_tags
from .secrets import load_secrets_file, update_secrets_file

ROUTING_SECRET_KEY = "ROUTING_BLOCK"
DEFAULT_GEOIP_URL = "https://github.com/v2fly/geoip/releases/latest/download/geoip.dat"
DEFAULT_GEOSITE_URL = "https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat"
ROUTING_DIR = os.path.join(settings.data_dir, "routing")
GEOIP_PATH = os.path.join(ROUTING_DIR, "geoip.dat")
GEOSITE_PATH = os.path.join(ROUTING_DIR, "geosite.dat")
NFT_RULES_PATH = os.path.join(ROUTING_DIR, "awgpanel-block.nft")
DNSMASQ_CONF_PATH = os.path.join(ROUTING_DIR, "dnsmasq.conf")
NFT_TABLE = "awgpanel_block"
DNS_CONTAINER_NAME = "awgpanel-dnsblock"
DNS_REDIRECT_PORT = 5353


def _default_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "geoip_tags": [],
        "geoip_url": DEFAULT_GEOIP_URL,
        "dns_block_enabled": False,
        "dns_redirect_enabled": True,
        "geosite_tags": [],
        "geosite_url": DEFAULT_GEOSITE_URL,
        "manual_domains": [],
        "last_geoip_update": None,
        "last_geosite_update": None,
        "last_apply": None,
        "last_error": "",
    }


def load_routing_config() -> dict[str, Any]:
    raw = load_secrets_file().get(ROUTING_SECRET_KEY, {})
    config = _default_config()
    if isinstance(raw, dict):
        config.update(raw)
    config["enabled"] = bool(config.get("enabled"))
    tags = config.get("geoip_tags", [])
    if isinstance(tags, str):
        tags = [item.strip() for item in tags.replace("\n", ",").split(",")]
    if not isinstance(tags, list):
        tags = []
    config["geoip_tags"] = sorted({str(tag).strip().lower() for tag in tags if str(tag).strip()})
    config["geoip_url"] = str(config.get("geoip_url") or DEFAULT_GEOIP_URL).strip() or DEFAULT_GEOIP_URL
    config["dns_block_enabled"] = bool(config.get("dns_block_enabled"))
    config["dns_redirect_enabled"] = bool(config.get("dns_redirect_enabled", True))
    geosite_tags = config.get("geosite_tags", [])
    if isinstance(geosite_tags, str):
        geosite_tags = [item.strip() for item in geosite_tags.replace("\n", ",").split(",")]
    if not isinstance(geosite_tags, list):
        geosite_tags = []
    config["geosite_tags"] = sorted({str(tag).strip().lower() for tag in geosite_tags if str(tag).strip()})
    domains = config.get("manual_domains", [])
    if isinstance(domains, str):
        domains = [item.strip() for item in domains.replace("\n", ",").split(",")]
    if not isinstance(domains, list):
        domains = []
    config["manual_domains"] = normalize_domains(domains)
    config["geosite_url"] = str(config.get("geosite_url") or DEFAULT_GEOSITE_URL).strip() or DEFAULT_GEOSITE_URL
    return config


def save_routing_config(updates: dict[str, Any]) -> dict[str, Any]:
    config = load_routing_config()
    config.update(updates)
    if "geoip_tags" in config:
        tags = config["geoip_tags"]
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.replace("\n", ",").split(",")]
        config["geoip_tags"] = sorted({str(tag).strip().lower() for tag in tags if str(tag).strip()})
    config["enabled"] = bool(config.get("enabled"))
    config["geoip_url"] = str(config.get("geoip_url") or DEFAULT_GEOIP_URL).strip() or DEFAULT_GEOIP_URL
    config["dns_block_enabled"] = bool(config.get("dns_block_enabled"))
    config["dns_redirect_enabled"] = bool(config.get("dns_redirect_enabled", True))
    if "geosite_tags" in config:
        tags = config["geosite_tags"]
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.replace("\n", ",").split(",")]
        config["geosite_tags"] = sorted({str(tag).strip().lower() for tag in tags if str(tag).strip()})
    if "manual_domains" in config:
        domains = config["manual_domains"]
        if isinstance(domains, str):
            domains = [item.strip() for item in domains.replace("\n", ",").split(",")]
        config["manual_domains"] = normalize_domains(domains)
    config["geosite_url"] = str(config.get("geosite_url") or DEFAULT_GEOSITE_URL).strip() or DEFAULT_GEOSITE_URL
    update_secrets_file({ROUTING_SECRET_KEY: config})
    return config


def normalize_domains(values: list[Any]) -> list[str]:
    domains: set[str] = set()
    for value in values:
        item = str(value or "").strip().lower().strip(".")
        if not item:
            continue
        if item.startswith("*."):
            item = item[2:]
        if "/" in item or " " in item or item.startswith(".") or "." not in item:
            continue
        domains.add(item)
    return sorted(domains)


def _geoip_status() -> dict[str, Any]:
    try:
        stat = os.stat(GEOIP_PATH)
    except OSError:
        return {"exists": False, "size": 0, "mtime": None, "tags": []}
    try:
        tags = load_geoip_tags(GEOIP_PATH)
    except Exception:
        tags = []
    return {
        "exists": True,
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "tags": tags,
    }


def _geosite_status() -> dict[str, Any]:
    try:
        stat = os.stat(GEOSITE_PATH)
    except OSError:
        return {"exists": False, "size": 0, "mtime": None, "tags": []}
    try:
        tags = load_geosite_tags(GEOSITE_PATH)
    except Exception:
        tags = []
    return {
        "exists": True,
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "tags": tags,
    }


def routing_status() -> dict[str, Any]:
    config = load_routing_config()
    return {
        "config": config,
        "geoip": _geoip_status(),
        "geosite": _geosite_status(),
        "nft_table": NFT_TABLE,
        "interface": settings.awg_interface,
    }


def update_geoip_database(url: str | None = None) -> dict[str, Any]:
    config = load_routing_config()
    source_url = (url or config.get("geoip_url") or DEFAULT_GEOIP_URL).strip()
    os.makedirs(ROUTING_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="geoip-", suffix=".dat", dir=ROUTING_DIR)
    os.close(fd)
    try:
        with urllib.request.urlopen(source_url, timeout=60) as response:
            with open(tmp_path, "wb") as fh:
                fh.write(response.read())
        tags = load_geoip_tags(tmp_path)
        if not tags:
            raise RuntimeError("Downloaded geoip.dat does not contain GEOIP tags")
        os.replace(tmp_path, GEOIP_PATH)
        config = save_routing_config(
            {
                "geoip_url": source_url,
                "last_geoip_update": int(time.time()),
                "last_error": "",
            }
        )
        return {"ok": True, "config": config, "geoip": _geoip_status()}
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        save_routing_config({"last_error": str(exc)})
        raise


def update_geosite_database(url: str | None = None) -> dict[str, Any]:
    config = load_routing_config()
    source_url = (url or config.get("geosite_url") or DEFAULT_GEOSITE_URL).strip()
    os.makedirs(ROUTING_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="geosite-", suffix=".dat", dir=ROUTING_DIR)
    os.close(fd)
    try:
        with urllib.request.urlopen(source_url, timeout=60) as response:
            with open(tmp_path, "wb") as fh:
                fh.write(response.read())
        tags = load_geosite_tags(tmp_path)
        if not tags:
            raise RuntimeError("Downloaded geosite.dat does not contain GEOSITE tags")
        os.replace(tmp_path, GEOSITE_PATH)
        config = save_routing_config(
            {
                "geosite_url": source_url,
                "last_geosite_update": int(time.time()),
                "last_error": "",
            }
        )
        return {"ok": True, "config": config, "geosite": _geosite_status()}
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        save_routing_config({"last_error": str(exc)})
        raise


def _nft_elements(items: list[str]) -> str:
    if not items:
        return ""
    lines = [f"      {item}" for item in items]
    return ",\n".join(lines)


def build_nft_rules(v4: list[str], v6: list[str], dns_redirect: bool = False) -> str:
    parts = [f"table inet {NFT_TABLE} {{"]
    if v4:
        parts.extend(
            [
                "  set geoip_block_v4 {",
                "    type ipv4_addr",
                "    flags interval",
                "    elements = {",
                _nft_elements(v4),
                "    }",
                "  }",
            ]
        )
    if v6:
        parts.extend(
            [
                "  set geoip_block_v6 {",
                "    type ipv6_addr",
                "    flags interval",
                "    elements = {",
                _nft_elements(v6),
                "    }",
                "  }",
            ]
        )

    parts.extend(["  chain forward {", "    type filter hook forward priority 0; policy accept;"])
    if v4:
        parts.append(f"    iifname {json.dumps(settings.awg_interface)} ip daddr @geoip_block_v4 counter drop")
    if v6:
        parts.append(f"    iifname {json.dumps(settings.awg_interface)} ip6 daddr @geoip_block_v6 counter drop")
    parts.extend(["  }", "}"])
    if dns_redirect:
        parts.insert(
            -1,
            "\n".join(
                [
                    "  chain dns_redirect {",
                    "    type nat hook prerouting priority dstnat; policy accept;",
                    f"    iifname {json.dumps(settings.awg_interface)} udp dport 53 counter redirect to :{DNS_REDIRECT_PORT}",
                    f"    iifname {json.dumps(settings.awg_interface)} tcp dport 53 counter redirect to :{DNS_REDIRECT_PORT}",
                    "  }",
                ]
            ),
        )
    return "\n".join(parts) + "\n"


def _panel_image_and_data_mount() -> tuple[str, Mount | None]:
    client = docker.from_env()
    container_id = os.environ.get("HOSTNAME") or ""
    if not container_id:
        raise RuntimeError("Panel container id not found")
    container = client.containers.get(container_id)
    image_id = container.image.id
    data_mount = None
    for mount in container.attrs.get("Mounts", []):
        if mount.get("Destination") != settings.data_dir:
            continue
        source = mount.get("Source")
        if source:
            data_mount = Mount(target=settings.data_dir, source=source, type="bind")
            break
    return image_id, data_mount


def _run_nft_helper(command: str) -> None:
    client = docker.from_env()
    image_id, data_mount = _panel_image_and_data_mount()
    mounts = [data_mount] if data_mount is not None else []
    try:
        container = client.containers.run(
            image_id,
            command=["sh", "-lc", command],
            detach=True,
            privileged=True,
            network_mode="host",
            mounts=mounts,
        )
        result = container.wait(timeout=180)
        logs = container.logs(stdout=True, stderr=True).decode(errors="ignore").strip()
        try:
            container.remove(force=True)
        except DockerException:
            pass
    except DockerException as exc:
        raise RuntimeError(str(exc)) from exc

    status_code = int(result.get("StatusCode", 1))
    if status_code != 0:
        raise RuntimeError(logs or f"nft helper failed with exit code {status_code}")


def _remove_dns_container(client) -> None:
    try:
        container = client.containers.get(DNS_CONTAINER_NAME)
    except DockerException:
        return
    try:
        container.remove(force=True)
    except DockerException:
        pass


def build_dnsmasq_config(domains: list[str]) -> str:
    lines = [
        f"port={DNS_REDIRECT_PORT}",
        "no-resolv",
        "server=1.1.1.1",
        "server=8.8.8.8",
        "bind-dynamic",
        "log-queries",
    ]
    for domain in domains:
        lines.append(f"address=/{domain}/0.0.0.0")
        lines.append(f"address=/{domain}/::")
    return "\n".join(lines) + "\n"


def _dns_block_domains(config: dict[str, Any]) -> list[str]:
    domains = set(config.get("manual_domains", []))
    if config.get("geosite_tags"):
        if not os.path.exists(GEOSITE_PATH):
            raise RuntimeError("geosite.dat is not downloaded yet")
        domains.update(load_geosite_domains(GEOSITE_PATH, config["geosite_tags"]))
    return normalize_domains(list(domains))


def start_dns_block(domains: list[str]) -> None:
    os.makedirs(ROUTING_DIR, exist_ok=True)
    with open(DNSMASQ_CONF_PATH, "w", encoding="utf-8") as fh:
        fh.write(build_dnsmasq_config(domains))

    client = docker.from_env()
    image_id, data_mount = _panel_image_and_data_mount()
    mounts = [data_mount] if data_mount is not None else []
    _remove_dns_container(client)
    try:
        client.containers.run(
            image_id,
            name=DNS_CONTAINER_NAME,
            command=["dnsmasq", "--keep-in-foreground", f"--conf-file={DNSMASQ_CONF_PATH}"],
            detach=True,
            network_mode="host",
            restart_policy={"Name": "unless-stopped"},
            mounts=mounts,
        )
    except DockerException as exc:
        raise RuntimeError(str(exc)) from exc


def stop_dns_block() -> None:
    _remove_dns_container(docker.from_env())


def clear_geoip_block() -> dict[str, Any]:
    stop_dns_block()
    _run_nft_helper(f"nft delete table inet {NFT_TABLE} 2>/dev/null || true")
    config = save_routing_config({"last_apply": int(time.time()), "last_error": ""})
    return {"ok": True, "config": config, "rules": {"ipv4": 0, "ipv6": 0}}


def apply_geoip_block() -> dict[str, Any]:
    config = load_routing_config()
    if not config["enabled"] and not config["dns_block_enabled"]:
        return clear_geoip_block()
    if config["enabled"] and not os.path.exists(GEOIP_PATH):
        raise RuntimeError("geoip.dat is not downloaded yet")

    v4, v6 = ([], [])
    if config["enabled"]:
        v4, v6 = load_geoip_cidrs(GEOIP_PATH, config["geoip_tags"])

    dns_domains: list[str] = []
    if config["dns_block_enabled"]:
        dns_domains = _dns_block_domains(config)
        if not dns_domains:
            raise RuntimeError("DNS Block is enabled, but no domains are selected")
        start_dns_block(dns_domains)
    else:
        stop_dns_block()

    os.makedirs(ROUTING_DIR, exist_ok=True)
    with open(NFT_RULES_PATH, "w", encoding="utf-8") as fh:
        fh.write(build_nft_rules(v4, v6, config["dns_block_enabled"] and config["dns_redirect_enabled"]))

    if not v4 and not v6 and not config["dns_block_enabled"]:
        return clear_geoip_block()

    command = f"nft delete table inet {NFT_TABLE} 2>/dev/null || true; nft -f {NFT_RULES_PATH}"
    _run_nft_helper(command)
    config = save_routing_config({"last_apply": int(time.time()), "last_error": ""})
    return {"ok": True, "config": config, "rules": {"ipv4": len(v4), "ipv6": len(v6), "domains": len(dns_domains)}}
