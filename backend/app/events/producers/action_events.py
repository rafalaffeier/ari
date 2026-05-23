"""
Action event producer.
Publishes events to Redis Pub/Sub so consumers and WebSocket clients
can react without coupling to the action service directly.
"""
import json
from app.core.redis import get_redis
from app.domain.actions.entities import ActionEntity


class ActionEventProducer:

    CHANNEL = "events:actions"

    async def _publish(self, event_type: str, payload: dict) -> None:
        r = get_redis()
        await r.publish(self.CHANNEL, json.dumps({"type": event_type, **payload}))

    async def action_requested(self, action: ActionEntity) -> None:
        await self._publish("action.requested", {
            "action_id":  str(action.id),
            "tool":       action.tool_name,
            "risk_level": action.risk_level,
            "workspace_id": str(action.workspace_id),
        })

    async def action_confirmed(self, action: ActionEntity) -> None:
        await self._publish("action.confirmed", {
            "action_id": str(action.id),
            "tool":      action.tool_name,
        })

    async def action_completed(self, action_id: str, result: dict) -> None:
        await self._publish("action.completed", {
            "action_id": action_id,
            "result":    result,
        })

    async def action_failed(self, action_id: str, error: str) -> None:
        await self._publish("action.failed", {
            "action_id": action_id,
            "error":     error,
        })
