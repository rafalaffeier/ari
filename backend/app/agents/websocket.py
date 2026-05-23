from datetime import datetime, timezone
from typing import Dict
import json
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from app.core.database import AsyncSessionLocal
from app.core.security import verify_password
from app.models.device import Device, DeviceStatus

# In-memory registry of connected agents {device_id: WebSocket}
connected_agents: Dict[str, WebSocket] = {}


async def authenticate_agent(device_id: str, agent_token: str) -> Device | None:
    try:
        parsed_device_id = uuid.UUID(device_id)
    except ValueError:
        return None
    async with AsyncSessionLocal() as db:
        device = await db.get(Device, parsed_device_id)
        if not device or not device.agent_token_hash:
            return None
        if not verify_password(agent_token, device.agent_token_hash):
            return None
        device.status = DeviceStatus.online
        device.last_seen_at = datetime.now(timezone.utc)
        device.last_ping_at = device.last_seen_at
        await db.commit()
        return device

async def agent_connect(websocket: WebSocket, device_id: str):
    await websocket.accept()
    connected_agents[device_id] = websocket
    print(f"Agent connected: {device_id}")
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await record_agent_ping(device_id)
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif msg.get("type") == "result":
                await handle_result(device_id, msg)
    except WebSocketDisconnect:
        connected_agents.pop(device_id, None)
        await mark_agent_offline(device_id)
        print(f"Agent disconnected: {device_id}")

async def send_command(device_id: str, command: dict) -> bool:
    ws = connected_agents.get(device_id)
    if not ws:
        return False
    await ws.send_text(json.dumps(command))
    return True

async def handle_result(device_id: str, msg: dict):
    # TODO: update action status in DB, emit event
    print(f"Result from {device_id}: {msg}")


async def record_agent_ping(device_id: str) -> None:
    try:
        parsed_device_id = uuid.UUID(device_id)
    except ValueError:
        return
    async with AsyncSessionLocal() as db:
        device = await db.get(Device, parsed_device_id)
        if device:
            device.status = DeviceStatus.online
            device.last_ping_at = datetime.now(timezone.utc)
            device.last_seen_at = device.last_ping_at
            await db.commit()


async def mark_agent_offline(device_id: str) -> None:
    try:
        parsed_device_id = uuid.UUID(device_id)
    except ValueError:
        return
    async with AsyncSessionLocal() as db:
        device = await db.get(Device, parsed_device_id)
        if device:
            device.status = DeviceStatus.offline
            await db.commit()
