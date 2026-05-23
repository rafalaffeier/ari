import uuid

from fastapi import APIRouter, Depends

from app.api.deps import require_workspace_access
from app.services.duffel import FlightSearchRequest, FlightSearchResponse, search_flights

router = APIRouter()

@router.get("/")
async def list_travel():
    return []


@router.post("/{workspace_id}/flights/search", response_model=FlightSearchResponse)
async def search_workspace_flights(
    body: FlightSearchRequest,
    workspace_id: uuid.UUID = Depends(require_workspace_access),
):
    return await search_flights(body)
