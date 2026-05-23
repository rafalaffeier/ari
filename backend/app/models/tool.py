from sqlalchemy import String, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from .base import TimestampMixin

class Tool(TimestampMixin, Base):
    __tablename__ = "tools"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[str] = mapped_column(String(20), primary_key=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    permission_key: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    schema: Mapped[dict] = mapped_column(JSONB, default=dict)
