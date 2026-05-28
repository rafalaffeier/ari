from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_access
from app.core.database import get_db
from app.models.action import Action, ActionStatus, ConfirmationToken, RiskLevel
from app.models.device import Device
from app.models.user import User
from app.services.tool_registry import get_tool

router = APIRouter()


class ActionCreate(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=100)
    params: dict = Field(default_factory=dict)
    device_id: Optional[uuid.UUID] = None
    idempotency_key: Optional[str] = None


class ActionConfirm(BaseModel):
    confirmation_token: str = Field(..., min_length=16)


class ActionResult(BaseModel):
    status: str = Field(..., pattern="^(done|failed)$")
    result: dict = Field(default_factory=dict)


class ActionOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    device_id: uuid.UUID | None
    tool_name: str
    tool_version: str
    params: dict
    status: str
    risk_level: str
    requires_confirmation: bool
    confirmation_token: str | None = None
    confirmed_at: datetime | None
    result: dict | None
    created_at: datetime


@router.post("/{workspace_id}", response_model=ActionOut, status_code=201)
async def create_action(
    body: ActionCreate,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.idempotency_key:
        existing = await _find_existing_action(db, workspace_id, body.idempotency_key)
        if existing:
            return _action_out(existing)

    tool = get_tool(body.tool_name)
    if not tool:
        raise HTTPException(status_code=400, detail=f"Unknown tool: {body.tool_name}")

    await _validate_device(db, body.device_id, workspace_id, current_user.id)
    required = tool.get("schema", {}).get("required", [])
    missing = [key for key in required if body.params.get(key) in (None, "")]
    if missing:
        raise HTTPException(status_code=422, detail={"missing_required_params": missing})

    requires_confirmation = bool(tool.get("requires_confirmation", False))
    action = Action(
        workspace_id=workspace_id,
        user_id=current_user.id,
        device_id=body.device_id,
        tool_name=body.tool_name,
        tool_version=tool.get("version", "1.0"),
        params=body.params,
        status=ActionStatus.pending_confirmation if requires_confirmation else ActionStatus.pending,
        risk_level=RiskLevel(tool.get("risk_level", "low")),
        requires_confirmation=requires_confirmation,
        confirmation_payload=body.params if requires_confirmation else None,
        idempotency_key=body.idempotency_key,
    )
    db.add(action)
    await db.flush()

    raw_token = None
    if requires_confirmation:
        raw_token = secrets.token_urlsafe(32)
        db.add(
            ConfirmationToken(
                action_id=action.id,
                token_hash=_hash_confirmation_token(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )

    await db.commit()
    await db.refresh(action)
    return _action_out(action, raw_token)


@router.get("/{workspace_id}", response_model=list[ActionOut])
async def list_actions(
    limit: int = 50,
    include_confirmation_tokens: bool = False,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bounded_limit = max(1, min(limit, 200))
    result = await db.execute(
        select(Action)
        .where(Action.workspace_id == workspace_id, Action.user_id == current_user.id)
        .order_by(Action.created_at.desc())
        .limit(bounded_limit)
    )
    actions = list(result.scalars())
    token_by_action: dict[uuid.UUID, str] = {}
    if include_confirmation_tokens:
        for action in actions:
            if action.status == ActionStatus.pending_confirmation and action.requires_confirmation:
                token_by_action[action.id] = await _renew_confirmation_token(db, action)
        if token_by_action:
            await db.commit()
    return [_action_out(action, token_by_action.get(action.id)) for action in actions]


@router.get("/{workspace_id}/{action_id}", response_model=ActionOut)
async def get_action(
    action_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await _get_owned_action(db, action_id, workspace_id, current_user.id)
    return _action_out(action)


@router.post("/{workspace_id}/{action_id}/confirm", response_model=ActionOut)
async def confirm_action(
    action_id: uuid.UUID,
    body: ActionConfirm,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await _get_owned_action(db, action_id, workspace_id, current_user.id)
    if action.status != ActionStatus.pending_confirmation:
        raise HTTPException(status_code=409, detail="Action is not awaiting confirmation")

    token = await db.get(ConfirmationToken, action.id)
    if not token or token.used_at is not None:
        raise HTTPException(status_code=409, detail="Confirmation token is not usable")
    if token.expires_at < datetime.now(timezone.utc):
        action.status = ActionStatus.expired
        await db.commit()
        raise HTTPException(status_code=410, detail="Confirmation token expired")
    if token.token_hash != _hash_confirmation_token(body.confirmation_token):
        raise HTTPException(status_code=403, detail="Invalid confirmation token")

    token.used_at = datetime.now(timezone.utc)
    action.status = ActionStatus.confirmed
    action.confirmed_at = token.used_at
    await db.commit()
    await db.refresh(action)
    return _action_out(action)


@router.post("/{workspace_id}/{action_id}/reject", response_model=ActionOut)
async def reject_action(
    action_id: uuid.UUID,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await _get_owned_action(db, action_id, workspace_id, current_user.id)
    if action.status not in (ActionStatus.pending, ActionStatus.pending_confirmation):
        raise HTTPException(status_code=409, detail="Action cannot be rejected in its current state")
    action.status = ActionStatus.rejected
    token = await db.get(ConfirmationToken, action.id)
    if token and token.used_at is None:
        token.used_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(action)
    return _action_out(action)


@router.post("/{workspace_id}/{action_id}/result", response_model=ActionOut)
async def complete_action(
    action_id: uuid.UUID,
    body: ActionResult,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await _get_owned_action(db, action_id, workspace_id, current_user.id)
    allowed_statuses = (ActionStatus.pending, ActionStatus.confirmed, ActionStatus.running)
    if action.status not in allowed_statuses:
        raise HTTPException(status_code=409, detail="Action cannot be completed in its current state")
    action.status = ActionStatus.done if body.status == "done" else ActionStatus.failed
    action.result = body.result
    await db.commit()
    await db.refresh(action)
    return _action_out(action)


async def _find_existing_action(
    db: AsyncSession, workspace_id: uuid.UUID, idempotency_key: str
) -> Action | None:
    result = await db.execute(
        select(Action).where(
            Action.workspace_id == workspace_id,
            Action.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def _get_owned_action(
    db: AsyncSession, action_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> Action:
    result = await db.execute(
        select(Action).where(
            Action.id == action_id,
            Action.workspace_id == workspace_id,
            Action.user_id == user_id,
        )
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


async def _validate_device(
    db: AsyncSession, device_id: uuid.UUID | None, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    if not device_id:
        return
    result = await db.execute(
        select(Device).where(
            Device.id == device_id,
            Device.workspace_id == workspace_id,
            Device.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="Device does not belong to this workspace")


def _hash_confirmation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _renew_confirmation_token(db: AsyncSession, action: Action) -> str:
    raw_token = secrets.token_urlsafe(32)
    token = await db.get(ConfirmationToken, action.id)
    if token:
        token.token_hash = _hash_confirmation_token(raw_token)
        token.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        token.used_at = None
    else:
        db.add(
            ConfirmationToken(
                action_id=action.id,
                token_hash=_hash_confirmation_token(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        )
    return raw_token


def _enum_value(value) -> str:
    return getattr(value, "value", str(value))


def _action_out(action: Action, confirmation_token: str | None = None) -> ActionOut:
    return ActionOut(
        id=action.id,
        workspace_id=action.workspace_id,
        user_id=action.user_id,
        device_id=action.device_id,
        tool_name=action.tool_name,
        tool_version=action.tool_version,
        params=action.params,
        status=_enum_value(action.status),
        risk_level=_enum_value(action.risk_level),
        requires_confirmation=action.requires_confirmation,
        confirmation_token=confirmation_token,
        confirmed_at=action.confirmed_at,
        result=action.result,
        created_at=action.created_at,
    )
