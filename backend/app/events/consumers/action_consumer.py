"""
Action event consumer.
Runs as a background task — subscribes to Redis Pub/Sub
and reacts to action events (dispatch to agent, update DB, notify client).
"""
import json
import asyncio
from app.core.redis import get_redis


async def consume_action_events():
    r = get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("events:actions")
    print("Action consumer started")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            event = json.loads(message["data"])
            await handle_event(event)
        except Exception as e:
            print(f"Consumer error: {e}")


async def handle_event(event: dict):
    event_type = event.get("type")

    if event_type == "action.confirmed":
        # Dispatch to the right executor (agent or backend tool)
        print(f"Dispatching confirmed action: {event['action_id']}")
        # TODO: route to desktop agent or backend tool executor

    elif event_type == "action.failed":
        print(f"Action failed: {event['action_id']} — {event.get('error')}")
        # TODO: notify user, trigger retry if applicable
