from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import hash_password
from app.models.device import Device, DeviceStatus
from app.models.user import User
from app.models.workspace import WorkspaceUser

router = APIRouter()


class DeviceRegisterRequest(BaseModel):
    device_name: str
    platform: str
    capabilities: List[str] = []
    workspace_id: uuid.UUID | None = None


class DeviceRegisterResponse(BaseModel):
    device_id: uuid.UUID
    agent_token: str


class DeviceOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    device_name: str
    platform: str
    status: str
    trust_level: str
    revoked_at: datetime | None

    class Config:
        from_attributes = True


@router.post("/register", response_model=DeviceRegisterResponse, status_code=201)
async def register_device(
    body: DeviceRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = await _resolve_workspace_id(db, current_user.id, body.workspace_id)
    agent_token = secrets.token_urlsafe(32)
    device = Device(
        user_id=current_user.id,
        workspace_id=workspace_id,
        device_name=body.device_name,
        platform=body.platform,
        agent_token_hash=hash_password(agent_token),
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return DeviceRegisterResponse(device_id=device.id, agent_token=agent_token)


@router.get("/", response_model=list[DeviceOut])
async def list_devices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device)
        .where(Device.user_id == current_user.id)
        .order_by(Device.created_at.desc())
    )
    return list(result.scalars())


@router.post("/{device_id}/revoke", status_code=204)
async def revoke_device(
    device_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.user_id == current_user.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.status = DeviceStatus.offline
    device.agent_token_hash = ""
    device.revoked_at = datetime.now(timezone.utc)
    await db.commit()


async def _resolve_workspace_id(
    db: AsyncSession, user_id: uuid.UUID, requested_workspace_id: uuid.UUID | None
) -> uuid.UUID:
    query = select(WorkspaceUser).where(WorkspaceUser.user_id == user_id)
    if requested_workspace_id:
        query = query.where(WorkspaceUser.workspace_id == requested_workspace_id)
    result = await db.execute(query)
    membership = result.scalars().first()
    if not membership:
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return membership.workspace_id
