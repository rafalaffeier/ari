from .base import BaseTool
from app.domain.tools.entities import ToolEntity
from app.tools.registry.registry import get


class SearchFlightsTool(BaseTool):
    tool: ToolEntity = None

    def __init__(self):
        self.tool = get("search_flights") or ToolEntity(
            name="search_flights", version="1.0",
            scope="backend", permission_key="travel.read",
        )

    async def execute(self, params: dict, context: dict) -> dict:
        self.validate_params(params)
        # TODO: call Amadeus / Skyscanner API
        # Return normalized results
        return {
            "results": [],
            "provider": "amadeus",
            "search_id": str(context.get("travel_search_id", "")),
        }


class SearchHotelsTool(BaseTool):
    tool: ToolEntity = None

    def __init__(self):
        self.tool = get("search_hotels") or ToolEntity(
            name="search_hotels", version="1.0",
            scope="backend", permission_key="travel.read",
        )

    async def execute(self, params: dict, context: dict) -> dict:
        self.validate_params(params)
        # TODO: call Expedia Rapid API
        return {"results": [], "provider": "expedia"}
