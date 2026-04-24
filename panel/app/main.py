from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .core import settings
from .db import init_db
from .routes import auth, peers, awg, system, api_info
from .security import is_pbkdf2_hash

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=60 * 60 * 24 * 7)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


def _validate_runtime_security() -> None:
    if not settings.secret_key or settings.secret_key == "change-me":
        raise RuntimeError("SECRET_KEY is not configured")
    if not settings.admin_pass or settings.admin_pass == "change-me":
        raise RuntimeError("ADMIN_PASS is not configured")
    if not is_pbkdf2_hash(settings.admin_pass):
        print("[awgpanel] warning: ADMIN_PASS uses legacy plain-text format; it will be upgraded on next login.")


@app.on_event("startup")
def _startup() -> None:
    _validate_runtime_security()
    init_db()


app.include_router(auth.router)
app.include_router(peers.router)
app.include_router(awg.router)
app.include_router(system.router)
app.include_router(api_info.router)
