from fastapi import APIRouter

from app.services.tool_registry import list_tools as list_registered_tools

router = APIRouter()

@router.get("/")
async def list_tools():
    return list_registered_tools()
