from __future__ import annotations

import uuid
from datetime import date
from sqlalchemy import String, ForeignKey, Date, Integer, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from .base import UUIDMixin, TimestampMixin

class TravelSearch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "travel_searches"
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    origin: Mapped[str] = mapped_column(String(10), nullable=False)
    destination: Mapped[str] = mapped_column(String(10), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    passengers: Mapped[int] = mapped_column(Integer, default=1)
    budget: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)

class TravelResult(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "travel_results"
    travel_search_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("travel_searches.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    result_type: Mapped[str] = mapped_column(String(20), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(5), default="EUR")
    score: Mapped[float] = mapped_column(Numeric(4, 2), default=0)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    booking_url: Mapped[str] = mapped_column(Text, nullable=False)

class TravelPriceAlert(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "travel_price_alerts"
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    travel_search_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("travel_searches.id"), nullable=False)
    target_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
