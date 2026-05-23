"""
Action use cases — all business logic lives here.
Depends on abstract repository and event bus, not on concrete implementations.
"""
from typing import Optional
from .entities import ActionEntity, ActionStatus, RiskLevel
from .repository import ActionRepository
from app.events.producers.action_events import ActionEventProducer
import uuid


class CreateActionUseCase:
    def __init__(self, repo: ActionRepository, events: ActionEventProducer):
        self._repo   = repo
        self._events = events

    async def execute(
        self,
        tool_name: str,
        params: dict,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        risk_level: RiskLevel = RiskLevel.low,
        requires_confirmation: bool = False,
        idempotency_key: Optional[str] = None,
        device_id: Optional[uuid.UUID] = None,
    ) -> ActionEntity:

        # Idempotency check
        if idempotency_key:
            existing = await self._repo.get_by_idempotency_key(idempotency_key, workspace_id)
            if existing:
                return existing

        action = ActionEntity(
            tool_name=tool_name,
            params=params,
            workspace_id=workspace_id,
            user_id=user_id,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            idempotency_key=idempotency_key,
            device_id=device_id,
        )

        if action.needs_confirmation():
            action.status = ActionStatus.pending_confirmation

        saved = await self._repo.save(action)
        await self._events.action_requested(saved)
        return saved


class ConfirmActionUseCase:
    def __init__(self, repo: ActionRepository, events: ActionEventProducer):
        self._repo   = repo
        self._events = events

    async def execute(self, action_id: uuid.UUID) -> ActionEntity:
        action = await self._repo.get_by_id(action_id)
        if not action:
            raise ValueError(f"Action {action_id} not found")
        if action.status != ActionStatus.pending_confirmation:
            raise ValueError(f"Action {action_id} is not awaiting confirmation")

        await self._repo.update_status(action_id, ActionStatus.confirmed)
        action.status = ActionStatus.confirmed
        await self._events.action_confirmed(action)
        return action
