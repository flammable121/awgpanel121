from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .core import settings
from .db import init_db
from .routes import auth, peers, awg, system, api_info

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, max_age=60 * 60 * 24 * 7)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


app.include_router(auth.router)
app.include_router(peers.router)
app.include_router(awg.router)
app.include_router(system.router)
app.include_router(api_info.router)
