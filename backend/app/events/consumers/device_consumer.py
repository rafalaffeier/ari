import json
from app.core.redis import get_redis


async def consume_device_events():
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("events:devices")
    print("Device consumer started")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            event = json.loads(message["data"])
            await handle_event(event)
        except Exception as e:
            print(f"Device consumer error: {e}")


async def handle_event(event: dict):
    event_type = event.get("type")
    if event_type == "device.offline":
        print(f"Device went offline: {event['device_id']}")
        # TODO: move its queued actions to offline_queue, update audit log
    elif event_type == "device.revoked":
        print(f"Device revoked: {event['device_id']}")
        # TODO: close WS session, reject pending actions
