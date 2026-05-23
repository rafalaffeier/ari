from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceUser, WorkspaceRole
from pydantic import BaseModel
import uuid

router = APIRouter()

class WorkspaceCreate(BaseModel):
    name: str

class WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    class Config: from_attributes = True

@router.post("/", response_model=WorkspaceOut, status_code=201)
async def create_workspace(
    body: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ws = Workspace(name=body.name, owner_user_id=current_user.id)
    db.add(ws)
    await db.flush()
    db.add(WorkspaceUser(workspace_id=ws.id, user_id=current_user.id, role=WorkspaceRole.owner))
    await db.commit()
    await db.refresh(ws)
    return ws

@router.get("/", response_model=list[WorkspaceOut])
async def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workspace).join(WorkspaceUser).where(WorkspaceUser.user_id == current_user.id)
    )
    return result.scalars().all()
