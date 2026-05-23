import uuid
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, hash_password
from app.services.email import send_password_reset_email, send_welcome_email
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceRole, WorkspaceUser
from pydantic import BaseModel, EmailStr, Field

router = APIRouter()
logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_SCOPES = "openid email profile"
GOOGLE_STATE_TTL_MINUTES = 10
GOOGLE_EXCHANGE_TTL_MINUTES = 5

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=32)
    password: str = Field(min_length=8)

class GoogleExchangeRequest(BaseModel):
    code: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    default_workspace_id: uuid.UUID | None = None
    email: EmailStr | None = None

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
    _send_welcome_email_safely(user.email)
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token, user_id=user.id, default_workspace_id=workspace.id, email=user.email)

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
        email=user.email,
    )

@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user:
        now = datetime.now(timezone.utc)
        existing_tokens = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
        )
        for existing_token in existing_tokens.scalars():
            existing_token.used_at = now
        raw_token = secrets.token_urlsafe(48)
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_reset_token(raw_token),
            expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
        db.add(reset_token)
        await db.commit()
        reset_url = _password_reset_url(request, raw_token)
        _send_password_reset_email_safely(user.email, reset_url)
    return {"detail": "If the email exists, recovery instructions have been sent"}

@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    token_hash = _hash_reset_token(body.token.strip())
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    reset_token = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not reset_token or reset_token.used_at or reset_token.expires_at < now:
        raise HTTPException(status_code=400, detail="Invalid or expired recovery link")

    user_result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired recovery link")

    user.password_hash = hash_password(body.password)
    reset_token.used_at = now
    await db.commit()
    return {"detail": "Password updated"}

@router.get("/google/start")
async def google_start(
    request: Request,
    client: str = Query("web", pattern="^(web|desktop|mobile)$"),
    return_to: str = "",
):
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        return _google_error_response(client, "Google OAuth is not configured")
    redirect_uri = _google_redirect_uri(request)
    state = _encode_google_state(client=client, return_to=return_to)
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}", status_code=302)

@router.get("/google/callback", name="google_callback")
async def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
):
    _require_google_oauth_configured()
    raw_state_payload = _decode_google_jwt_state(state)
    if raw_state_payload.get("typ") == "google_integration_state":
        from app.api.v1.endpoints.integrations import handle_google_integration_callback

        return await handle_google_integration_callback(code=code, state=state, error=error, db=db)

    state_payload = _decode_google_state(state)
    client = state_payload.get("client", "web")

    if error:
        return _google_error_response(client, f"Google rejected the login: {error}")
    if not code:
        return _google_error_response(client, "Google did not return an authorization code")

    profile = await _exchange_google_code(request, code)
    user, workspace = await _get_or_create_google_user(db, profile["email"])
    auth = TokenResponse(
        access_token=create_access_token(str(user.id)),
        user_id=user.id,
        default_workspace_id=workspace.id,
        email=user.email,
    )

    payload = _encode_google_exchange_code(auth)

    if client == "web":
        return_to = _safe_return_to(state_payload.get("return_to") or "/")
        separator = "&" if "#" in return_to else "#"
        return RedirectResponse(f"{return_to}{separator}google_auth={payload}", status_code=302)

    return_to = _safe_loopback_return_to(state_payload.get("return_to") or "")
    if return_to:
        separator = "&" if "?" in return_to else "?"
        return RedirectResponse(
            f"{return_to}{separator}google_auth={quote(payload)}",
            status_code=302,
        )

    return HTMLResponse(_google_code_page(payload))

@router.post("/google/exchange", response_model=TokenResponse)
async def google_exchange(body: GoogleExchangeRequest):
    try:
        payload = jwt.decode(body.code.strip(), settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired Google login code")
    if payload.get("typ") != "google_exchange":
        raise HTTPException(status_code=400, detail="Invalid Google login code")
    auth = payload.get("auth") or {}
    try:
        return TokenResponse(**auth)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Google login payload")

def _require_google_oauth_configured() -> None:
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")

def _google_redirect_uri(request: Request) -> str:
    if settings.GOOGLE_OAUTH_REDIRECT_URI:
        return settings.GOOGLE_OAUTH_REDIRECT_URI
    return str(request.url_for("google_callback"))

def _encode_google_state(client: str, return_to: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=GOOGLE_STATE_TTL_MINUTES)
    return jwt.encode(
        {"typ": "google_oauth_state", "client": client, "return_to": return_to, "exp": expire},
        settings.SECRET_KEY,
        algorithm="HS256",
    )

def _decode_google_state(state: str) -> dict:
    payload = _decode_google_jwt_state(state)
    if payload.get("typ") != "google_oauth_state":
        raise HTTPException(status_code=400, detail="Invalid Google OAuth state")
    return payload

def _decode_google_jwt_state(state: str) -> dict:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired Google OAuth state")
    return payload

def _encode_google_exchange_code(auth: TokenResponse) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=GOOGLE_EXCHANGE_TTL_MINUTES)
    return jwt.encode(
        {"typ": "google_exchange", "auth": auth.model_dump(mode="json"), "exp": expire},
        settings.SECRET_KEY,
        algorithm="HS256",
    )

def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def _password_reset_url(request: Request, token: str) -> str:
    base_url = settings.PUBLIC_APP_URL.rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base_url}/?reset_token={quote(token)}"

def _send_welcome_email_safely(email: str) -> None:
    try:
        send_welcome_email(email)
    except Exception:
        logger.exception("Failed to send welcome email to %s", email)

def _send_password_reset_email_safely(email: str, reset_url: str) -> None:
    try:
        send_password_reset_email(email, reset_url, settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    except Exception:
        logger.exception("Failed to send password reset email to %s", email)

async def _exchange_google_code(request: Request, code: str) -> dict:
    redirect_uri = _google_redirect_uri(request)
    async with httpx.AsyncClient(timeout=12.0) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code >= 400:
            raise HTTPException(status_code=401, detail="Google token exchange failed")
        token_data = token_response.json()
        id_token = token_data.get("id_token")
        if not id_token:
            raise HTTPException(status_code=401, detail="Google did not return an id token")
        profile_response = await client.get(GOOGLE_TOKENINFO_URL, params={"id_token": id_token})
        if profile_response.status_code >= 400:
            raise HTTPException(status_code=401, detail="Google id token verification failed")
        profile = profile_response.json()
    if profile.get("aud") != settings.GOOGLE_OAUTH_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Google token audience mismatch")
    if profile.get("email_verified") not in {True, "true", "True", "1"}:
        raise HTTPException(status_code=401, detail="Google email is not verified")
    email = str(profile.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Google profile did not include an email")
    return {"email": email, "sub": profile.get("sub")}

async def _get_or_create_google_user(db: AsyncSession, email: str) -> tuple[User, Workspace]:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        user = User(email=email, password_hash=hash_password(uuid.uuid4().hex + uuid.uuid4().hex))
        db.add(user)
        await db.flush()
        workspace = Workspace(name="Personal", owner_user_id=user.id)
        db.add(workspace)
        await db.flush()
        db.add(WorkspaceUser(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.owner))
        await db.commit()
        await db.refresh(user)
        await db.refresh(workspace)
        _send_welcome_email_safely(user.email)
        return user, workspace

    workspace_result = await db.execute(
        select(Workspace).join(WorkspaceUser).where(
            WorkspaceUser.user_id == user.id,
            WorkspaceUser.role == WorkspaceRole.owner,
        )
    )
    workspace = workspace_result.scalar_one_or_none()
    if not workspace:
        workspace = Workspace(name="Personal", owner_user_id=user.id)
        db.add(workspace)
        await db.flush()
        db.add(WorkspaceUser(workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.owner))
        await db.commit()
        await db.refresh(workspace)
    return user, workspace

def _safe_return_to(return_to: str) -> str:
    if return_to.startswith("/"):
        return return_to
    if any(return_to.startswith(origin) for origin in settings.ALLOWED_ORIGINS):
        return return_to
    return "/"

def _safe_loopback_return_to(return_to: str) -> str:
    parsed = urlparse(return_to)
    if parsed.scheme != "http":
        return ""
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return ""
    if parsed.port is None:
        return ""
    return return_to

def _google_error_response(client: str, detail: str):
    if client == "web":
        return RedirectResponse(f"/#google_error={quote(detail)}", status_code=302)
    return HTMLResponse(f"<h1>ARI Google login failed</h1><p>{detail}</p>", status_code=400)

def _google_code_page(exchange_code: str) -> str:
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ARI Google Login</title>
  <style>
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:#1A1208; color:#F7F2EC; font-family:Georgia,serif; }}
    main {{ width:min(720px, calc(100% - 32px)); border:1px solid rgba(201,169,110,.28); padding:32px; background:rgba(20,12,4,.86); }}
    h1 {{ font-weight:300; font-style:italic; letter-spacing:3px; }}
    p {{ color:rgba(247,242,236,.72); line-height:1.5; }}
    code {{ display:block; margin-top:18px; padding:18px; overflow-wrap:anywhere; color:#C9A96E; border:1px solid rgba(201,169,110,.22); background:rgba(201,169,110,.04); font-family:ui-monospace,monospace; }}
  </style>
</head>
<body>
  <main>
    <h1>ARI is ready</h1>
    <p>Copy this short-lived login code back into the desktop or mobile app. The code expires in {GOOGLE_EXCHANGE_TTL_MINUTES} minutes.</p>
    <code>{exchange_code}</code>
  </main>
</body>
</html>
"""
