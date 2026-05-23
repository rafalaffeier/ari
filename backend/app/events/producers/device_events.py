import json
from app.core.redis import get_redis


class DeviceEventProducer:

    CHANNEL = "events:devices"

    async def _publish(self, event_type: str, payload: dict) -> None:
        r = get_redis()
        await r.publish(self.CHANNEL, json.dumps({"type": event_type, **payload}))

    async def device_online(self, device_id: str) -> None:
        await self._publish("device.online", {"device_id": device_id})

    async def device_offline(self, device_id: str) -> None:
        await self._publish("device.offline", {"device_id": device_id})

    async def device_revoked(self, device_id: str) -> None:
        await self._publish("device.revoked", {"device_id": device_id})
