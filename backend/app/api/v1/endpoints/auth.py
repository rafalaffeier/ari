import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, hash_password
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceRole, WorkspaceUser
from pydantic import BaseModel, EmailStr

router = APIRouter()

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    default_workspace_id: uuid.UUID | None = None

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    workspace = Workspace(name="Personal", owner_user_id=user.id)
    db.add(workspace)
    await db.flush()
    db.add(WorkspaceUser(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.owner))
    await db.commit()
    await db.refresh(user)
    await db.refresh(workspace)
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user_id=user.id, default_workspace_id=workspace.id)

@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    workspace_result = await db.execute(
        select(WorkspaceUser).where(WorkspaceUser.user_id == user.id, WorkspaceUser.role == WorkspaceRole.owner)
    )
    default_workspace = workspace_result.scalar_one_or_none()
    token = create_access_token(str(user.id))
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        default_workspace_id=default_workspace.workspace_id if default_workspace else None,
    )
