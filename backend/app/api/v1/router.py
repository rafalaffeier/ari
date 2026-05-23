from fastapi import APIRouter
from app.api.v1.endpoints import actions, audit, auth, devices, memory, messages, sync, tools, travel, workspaces

api_router = APIRouter()
api_router.include_router(auth.router,       prefix="/auth",       tags=["auth"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(devices.router,    prefix="/devices",    tags=["devices"])
api_router.include_router(actions.router,    prefix="/actions",    tags=["actions"])
api_router.include_router(audit.router,      prefix="/audit",      tags=["audit"])
api_router.include_router(tools.router,      prefix="/tools",      tags=["tools"])
api_router.include_router(messages.router,   prefix="/messages",   tags=["messages"])
api_router.include_router(travel.router,     prefix="/travel",     tags=["travel"])
api_router.include_router(memory.router,     prefix="/memory",     tags=["memory"])
api_router.include_router(sync.router,       prefix="/sync",       tags=["sync"])
