from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.core.database import engine
from app.core.rate_limit import FixedWindowRateLimitMiddleware
from app.core.redis import get_redis
from app.api.v1.router import api_router

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(FixedWindowRateLimitMiddleware)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
async def ready():
    checks = {"database": "ok", "redis": "ok"}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception:
        checks["database"] = "error"

    try:
        await get_redis().ping()
    except Exception:
        checks["redis"] = "error"

    status_value = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return {"status": status_value, "env": settings.ENV, "checks": checks}

from fastapi import WebSocket, status
from app.agents.websocket import agent_connect, authenticate_agent

@app.websocket("/ws/agent")
async def websocket_agent(websocket: WebSocket, device_id: str = "", token: str = ""):
    device = await authenticate_agent(device_id, token)
    if device is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await agent_connect(websocket, device_id)

from app.tools.registry.loader import load_all_tools

@app.on_event("startup")
async def startup():
    load_all_tools()
    print("Tool registry loaded")
