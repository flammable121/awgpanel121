from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Peer(Base):
    __tablename__ = "peers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), default="")

    public_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    preshared_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    allowed_ips: Mapped[str] = mapped_column(String(64))
    client_allowed_ips: Mapped[str] = mapped_column(String(200), default="0.0.0.0/0, ::/0")
    client_dns: Mapped[str | None] = mapped_column(String(200), nullable=True)

    i1: Mapped[str | None] = mapped_column(Text, nullable=True)
    i2: Mapped[str | None] = mapped_column(Text, nullable=True)
    i3: Mapped[str | None] = mapped_column(Text, nullable=True)
    i4: Mapped[str | None] = mapped_column(Text, nullable=True)
    i5: Mapped[str | None] = mapped_column(Text, nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_devices: Mapped[int] = mapped_column(Integer, default=0)
