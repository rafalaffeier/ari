from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_access
from app.core.database import get_db
from app.models.audit import AuditLog
from app.models.user import User

router = APIRouter()


class AuditEventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100)
    tool_name: str | None = Field(None, max_length=100)
    payload: dict = Field(default_factory=dict)
    device_id: uuid.UUID | None = None


class AuditEventOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID | None
    user_id: uuid.UUID | None
    device_id: uuid.UUID | None
    event_type: str
    payload: dict
    hash_previous: str | None
    hash_current: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/{workspace_id}/events", response_model=AuditEventOut, status_code=201)
async def create_audit_event(
    body: AuditEventCreate,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    previous = await _latest_hash(db, workspace_id)
    payload = dict(body.payload)
    if body.tool_name:
        payload.setdefault("tool_name", body.tool_name)
    event = AuditLog(
        workspace_id=workspace_id,
        user_id=current_user.id,
        device_id=body.device_id,
        event_type=body.event_type,
        payload=payload,
        hash_previous=previous,
        hash_current=_event_hash(previous, body.event_type, payload),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


@router.get("/{workspace_id}/events", response_model=list[AuditEventOut])
async def list_audit_events(
    limit: int = 50,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    db: AsyncSession = Depends(get_db),
):
    bounded_limit = max(1, min(limit, 200))
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.workspace_id == workspace_id)
        .order_by(AuditLog.created_at.desc())
        .limit(bounded_limit)
    )
    return list(result.scalars())


async def _latest_hash(db: AsyncSession, workspace_id: uuid.UUID) -> str | None:
    result = await db.execute(
        select(AuditLog.hash_current)
        .where(AuditLog.workspace_id == workspace_id)
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _event_hash(previous: str | None, event_type: str, payload: dict) -> str:
    canonical = json.dumps(
        {"previous": previous, "event_type": event_type, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
