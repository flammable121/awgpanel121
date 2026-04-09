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
    panel_base_path: str = ""

    awg_container: str = "amnezia-awg2"
    awg_config_path: str = "/opt/amnezia/awg/awg0.conf"
    awg_interface: str = "awg0"

    public_endpoint: str | None = None
    default_client_allowed_ips: str = "0.0.0.0/0, ::/0"
    default_client_dns: str | None = None

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
        "secret_key": "secret_key",
        "admin_user": "admin_user",
        "admin_pass": "admin_pass",
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
    ]:
        env_val = os.getenv(env_name)
        if env_val:
            overrides[field] = env_val
        elif field in secrets:
            overrides[field] = secrets[field]
    return Settings(**overrides)
