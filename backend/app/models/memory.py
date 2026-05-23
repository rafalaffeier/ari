from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from .base import TimestampMixin

class Memory(TimestampMixin, Base):
    __tablename__ = "memory"
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scope: Mapped[str] = mapped_column(String(50), default="user")
    type: Mapped[str] = mapped_column(String(50), default="fact")
    data_classification: Mapped[str] = mapped_column(String(20), default="internal")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
