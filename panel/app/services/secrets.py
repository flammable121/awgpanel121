from __future__ import annotations

import json
import os
import threading
from typing import Any

from ..core import settings

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
