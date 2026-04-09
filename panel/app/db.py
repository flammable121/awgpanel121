from __future__ import annotations

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import get_settings


class Base(DeclarativeBase):
    pass


def _db_url() -> str:
    settings = get_settings()
    os.makedirs(settings.data_dir, exist_ok=True)
    return f"sqlite:///{settings.data_dir}/panel.db"


engine = create_engine(_db_url(), connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(peers)"))}
        if "max_devices" not in cols:
            conn.execute(text("ALTER TABLE peers ADD COLUMN max_devices INTEGER DEFAULT 0"))
        conn.commit()
