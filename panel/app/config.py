from __future__ import annotations

import os
import json
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    secret_key: str = "change-me"
    admin_user: str = "admin"
    admin_pass: str = "change-me"
    api_token: str = ""
    panel_base_path: str = ""

    awg_container: str = "amnezia-awg2"
    awg_config_path: str = "/opt/amnezia/awg/awg0.conf"
    awg_interface: str = "awg0"

    public_endpoint: str | None = None
    default_client_allowed_ips: str = "0.0.0.0/0, ::/0"
    default_client_dns: str | None = None
    client_name_key: str | None = None

    # WARP/Xray settings removed

    data_dir: str = os.getenv("PANEL_DATA_DIR", "/data")


def _load_secrets_file() -> dict[str, str]:
    path = os.getenv("PANEL_SECRETS_PATH")
    if not path:
        data_dir = os.getenv("PANEL_DATA_DIR", "/data")
        path = os.path.join(data_dir, "secrets.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, str] = {}
    mapping = {
        "SECRET_KEY": "secret_key",
        "ADMIN_USER": "admin_user",
        "ADMIN_PASS": "admin_pass",
        "API_TOKEN": "api_token",
        "PANEL_BASE_PATH": "panel_base_path",
        "AWG_CONTAINER": "awg_container",
        "AWG_CONFIG_PATH": "awg_config_path",
        "AWG_INTERFACE": "awg_interface",
        "PUBLIC_ENDPOINT": "public_endpoint",
        "DEFAULT_CLIENT_ALLOWED_IPS": "default_client_allowed_ips",
        "DEFAULT_CLIENT_DNS": "default_client_dns",
        "CLIENT_NAME_KEY": "client_name_key",
        "secret_key": "secret_key",
        "admin_user": "admin_user",
        "admin_pass": "admin_pass",
        "api_token": "api_token",
        "panel_base_path": "panel_base_path",
        "awg_container": "awg_container",
        "awg_config_path": "awg_config_path",
        "awg_interface": "awg_interface",
        "public_endpoint": "public_endpoint",
        "default_client_allowed_ips": "default_client_allowed_ips",
        "default_client_dns": "default_client_dns",
        "client_name_key": "client_name_key",
    }
    for key, value in data.items():
        if key in mapping and value:
            result[mapping[key]] = str(value)
    return result


@lru_cache
def get_settings() -> Settings:
    secrets = _load_secrets_file()
    overrides: dict[str, str] = {}
    for field, env_name in [
        ("secret_key", "SECRET_KEY"),
        ("admin_user", "ADMIN_USER"),
        ("admin_pass", "ADMIN_PASS"),
        ("api_token", "API_TOKEN"),
        ("panel_base_path", "PANEL_BASE_PATH"),
        ("awg_container", "AWG_CONTAINER"),
        ("awg_config_path", "AWG_CONFIG_PATH"),
        ("awg_interface", "AWG_INTERFACE"),
        ("public_endpoint", "PUBLIC_ENDPOINT"),
        ("default_client_allowed_ips", "DEFAULT_CLIENT_ALLOWED_IPS"),
        ("default_client_dns", "DEFAULT_CLIENT_DNS"),
        ("client_name_key", "CLIENT_NAME_KEY"),
    ]:
        env_val = os.getenv(env_name)
        if env_val:
            overrides[field] = env_val
        elif field in secrets:
            overrides[field] = secrets[field]
    return Settings(**overrides)
