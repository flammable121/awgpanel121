from __future__ import annotations

from fastapi.templating import Jinja2Templates

from .config import get_settings

settings = get_settings()


def _normalize_base_path(value: str) -> str:
    base = (value or "").strip()
    if not base or base == "/":
        return ""
    if not base.startswith("/"):
        base = "/" + base
    return base.rstrip("/")


BASE_PATH = _normalize_base_path(settings.panel_base_path)


def with_base(path: str) -> str:
    if not BASE_PATH:
        return path
    if not path.startswith("/"):
        path = "/" + path
    return f"{BASE_PATH}{path}"


def template_context(request, **extra):
    ctx = {"request": request, "base_path": BASE_PATH}
    ctx.update(extra)
    return ctx


templates = Jinja2Templates(directory="app/templates")
