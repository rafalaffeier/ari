from .base import BaseTool
from app.domain.tools.entities import ToolEntity
from app.tools.registry.registry import get


class CreateCalendarEventTool(BaseTool):
    tool: ToolEntity = None

    def __init__(self):
        self.tool = get("create_calendar_event") or ToolEntity(
            name="create_calendar_event", version="1.0",
            scope="backend", permission_key="calendar.write",
        )

    async def execute(self, params: dict, context: dict) -> dict:
        self.validate_params(params)
        # TODO: call Google Calendar API via integration service
        return {
            "status": "created",
            "event": {
                "title": params["title"],
                "date":  params["date"],
                "time":  params["time"],
            }
        }
