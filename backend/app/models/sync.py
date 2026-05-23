from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from .base import TimestampMixin, UUIDMixin


class FileVersion(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "file_versions"
    __table_args__ = (UniqueConstraint("workspace_id", "path", name="uq_file_versions_workspace_path"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    modified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    encryption_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)


class SyncEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sync_events"

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    file_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("file_versions.id"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class WorkspaceKeyWrap(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspace_key_wraps"
    __table_args__ = (
        UniqueConstraint("workspace_id", "device_id", "key_id", name="uq_workspace_key_wraps_workspace_device_key"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False)
    key_id: Mapped[str] = mapped_column(String(200), nullable=False)
    wrapping_algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    wrapped_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)


class WorkspaceRecoveryWrap(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspace_recovery_wraps"
    __table_args__ = (UniqueConstraint("workspace_id", "key_id", name="uq_workspace_recovery_wraps_workspace_key"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    key_id: Mapped[str] = mapped_column(String(200), nullable=False)
    wrapping_algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    wrapped_key: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
