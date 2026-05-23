import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1.endpoints.auth import GOOGLE_AUTH_URL, GOOGLE_TOKEN_URL, _safe_loopback_return_to, _safe_return_to
from app.core.config import settings
from app.core.database import get_db
from app.core.token_crypto import decrypt_token, encrypt_token
from app.models.integration import Integration
from app.models.user import User

router = APIRouter()

GOOGLE_PROVIDER = "google"
GOOGLE_INTEGRATION_STATE_TTL_MINUTES = 10
GOOGLE_INTEGRATION_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/contacts.readonly",
]
GOOGLE_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
GOOGLE_PEOPLE_CONNECTIONS_URL = "https://people.googleapis.com/v1/people/me/connections"


class GoogleIntegrationStartRequest(BaseModel):
    client: str = "web"
    return_to: str = "/"


class GoogleIntegrationStartResponse(BaseModel):
    authorization_url: str
    scopes: list[str]


class GoogleIntegrationStatusResponse(BaseModel):
    connected: bool
    provider: str = GOOGLE_PROVIDER
    scopes: list[str] = []
    status: str = "missing"
    expires_at: datetime | None = None


class GoogleCalendarEventRequest(BaseModel):
    title: str
    start: str
    end: str
    timezone: str = "Europe/Madrid"
    description: str | None = None
    location: str | None = None


@router.get("/google/status", response_model=GoogleIntegrationStatusResponse)
async def google_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    integration = await _get_google_integration(db, current_user.id)
    if not integration:
        return GoogleIntegrationStatusResponse(connected=False)
    return GoogleIntegrationStatusResponse(
        connected=integration.status == "connected" and bool(integration.refresh_token_encrypted),
        scopes=integration.scopes,
        status=integration.status,
        expires_at=integration.expires_at,
    )


@router.get("/google/calendar/events")
async def list_google_calendar_events(
    time_min: str | None = Query(None),
    time_max: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    access_token = await _valid_google_access_token(db, current_user.id)
    params = {
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "20",
    }
    if time_min:
        params["timeMin"] = time_min
    if time_max:
        params["timeMax"] = time_max
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(
            GOOGLE_CALENDAR_EVENTS_URL,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Google Calendar events request failed")
    return response.json()


@router.post("/google/calendar/events")
async def create_google_calendar_event(
    body: GoogleCalendarEventRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    access_token = await _valid_google_access_token(db, current_user.id)
    payload = {
        "summary": body.title,
        "start": {"dateTime": body.start, "timeZone": body.timezone},
        "end": {"dateTime": body.end, "timeZone": body.timezone},
    }
    if body.description:
        payload["description"] = body.description
    if body.location:
        payload["location"] = body.location
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            GOOGLE_CALENDAR_EVENTS_URL,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Google Calendar create event failed")
    return response.json()


@router.get("/google/contacts/search")
async def search_google_contacts(
    q: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    access_token = await _valid_google_access_token(db, current_user.id)
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(
            GOOGLE_PEOPLE_CONNECTIONS_URL,
            params={
                "pageSize": 200,
                "personFields": "names,emailAddresses,phoneNumbers",
                "sortOrder": "FIRST_NAME_ASCENDING",
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="Google Contacts request failed")
    needle = q.casefold()
    matches = []
    for person in response.json().get("connections", []):
        names = [item.get("displayName", "") for item in person.get("names", [])]
        phones = [item.get("canonicalForm") or item.get("value", "") for item in person.get("phoneNumbers", [])]
        emails = [item.get("value", "") for item in person.get("emailAddresses", [])]
        haystack = " ".join(names + phones + emails).casefold()
        if needle in haystack:
            matches.append(
                {
                    "resourceName": person.get("resourceName"),
                    "names": names,
                    "phoneNumbers": phones,
                    "emailAddresses": emails,
                }
            )
    return {"contacts": matches[:20]}


@router.post("/google/start", response_model=GoogleIntegrationStartResponse)
async def google_start(
    body: GoogleIntegrationStartRequest,
    current_user: User = Depends(get_current_user),
):
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    if body.client not in {"web", "desktop", "mobile"}:
        raise HTTPException(status_code=400, detail="Invalid Google integration client")
    redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI or "https://ari.flusscreative.com/api/v1/auth/google/callback"
    state = _encode_integration_state(current_user.id, body.client, body.return_to)
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_INTEGRATION_SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent select_account",
    }
    return GoogleIntegrationStartResponse(
        authorization_url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}",
        scopes=GOOGLE_INTEGRATION_SCOPES,
    )


@router.get("/google/callback")
async def google_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
):
    return await handle_google_integration_callback(code=code, state=state, error=error, db=db)


async def handle_google_integration_callback(
    code: str,
    state: str,
    error: str,
    db: AsyncSession,
):
    state_payload = _decode_integration_state(state)
    client = state_payload.get("client", "web")
    return_to = state_payload.get("return_to") or "/"
    if error:
        return _integration_error_response(client, return_to, f"Google rejected access: {error}")
    if not code:
        return _integration_error_response(client, return_to, "Google did not return an authorization code")

    token_data = await _exchange_google_integration_code(code)
    refresh_token = token_data.get("refresh_token")
    existing = await _get_google_integration(db, uuid.UUID(state_payload["user_id"]))
    if not refresh_token and not (existing and existing.refresh_token_encrypted):
        return _integration_error_response(
            client,
            return_to,
            "Google did not return persistent access. Please grant access again.",
        )

    await _upsert_google_integration(db, uuid.UUID(state_payload["user_id"]), token_data, existing)
    return _integration_success_response(client, return_to)


def _encode_integration_state(user_id: uuid.UUID, client: str, return_to: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=GOOGLE_INTEGRATION_STATE_TTL_MINUTES)
    return jwt.encode(
        {
            "typ": "google_integration_state",
            "user_id": str(user_id),
            "client": client,
            "return_to": return_to,
            "exp": expire,
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )


def _decode_integration_state(state: str) -> dict:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="Invalid or expired Google integration state") from exc
    if payload.get("typ") != "google_integration_state" or not payload.get("user_id"):
        raise HTTPException(status_code=400, detail="Invalid Google integration state")
    return payload


async def _exchange_google_integration_code(code: str) -> dict:
    redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI or "https://ari.flusscreative.com/api/v1/auth/google/callback"
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="Google token exchange failed")
    return response.json()


async def _get_google_integration(db: AsyncSession, user_id: uuid.UUID) -> Integration | None:
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == user_id,
            Integration.provider == GOOGLE_PROVIDER,
        )
    )
    return result.scalar_one_or_none()


async def _valid_google_access_token(db: AsyncSession, user_id: uuid.UUID) -> str:
    integration = await _get_google_integration(db, user_id)
    if not integration or integration.status != "connected" or not integration.refresh_token_encrypted:
        raise HTTPException(status_code=403, detail="Google integration is not connected")
    now = datetime.now(timezone.utc)
    if integration.access_token_encrypted and integration.expires_at and integration.expires_at > now + timedelta(minutes=2):
        return decrypt_token(integration.access_token_encrypted)
    refresh_token = decrypt_token(integration.refresh_token_encrypted)
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
    if response.status_code >= 400:
        integration.status = "expired"
        db.add(integration)
        await db.commit()
        raise HTTPException(status_code=403, detail="Google integration expired or was revoked")
    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=403, detail="Google did not return an access token")
    integration.access_token_encrypted = encrypt_token(access_token)
    integration.expires_at = now + timedelta(seconds=int(token_data.get("expires_in") or 3600))
    if token_data.get("scope"):
        integration.scopes = sorted(set(str(token_data["scope"]).split()))
    integration.status = "connected"
    db.add(integration)
    await db.commit()
    return access_token


async def _upsert_google_integration(
    db: AsyncSession,
    user_id: uuid.UUID,
    token_data: dict,
    existing: Integration | None,
) -> Integration:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=int(token_data.get("expires_in") or 3600))
    integration = existing or Integration(user_id=user_id, provider=GOOGLE_PROVIDER)
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    if access_token:
        integration.access_token_encrypted = encrypt_token(access_token)
    if refresh_token:
        integration.refresh_token_encrypted = encrypt_token(refresh_token)
    integration.scopes = sorted(set(str(token_data.get("scope") or "").split()) or set(GOOGLE_INTEGRATION_SCOPES))
    integration.expires_at = expires_at
    integration.status = "connected"
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return integration


def _integration_success_response(client: str, return_to: str):
    return _integration_redirect_or_page(client, return_to, "connected", "ARI connected Google Agenda and Contacts.")


def _integration_error_response(client: str, return_to: str, detail: str):
    return _integration_redirect_or_page(client, return_to, f"error:{detail}", detail, status_code=400)


def _integration_redirect_or_page(client: str, return_to: str, value: str, message: str, status_code: int = 302):
    target = _safe_loopback_return_to(return_to) if client in {"desktop", "mobile"} else _safe_return_to(return_to)
    if target:
        separator = "&" if "?" in target else "?"
        return RedirectResponse(f"{target}{separator}google_integration={quote(value)}", status_code=302)
    return HTMLResponse(f"<h1>Google integration</h1><p>{message}</p>", status_code=status_code)
