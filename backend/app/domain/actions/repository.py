"""Abstract repository — the domain does not know about SQLAlchemy."""
from abc import ABC, abstractmethod
from typing import Optional
import uuid
from .entities import ActionEntity


class ActionRepository(ABC):

    @abstractmethod
    async def save(self, action: ActionEntity) -> ActionEntity: ...

    @abstractmethod
    async def get_by_id(self, action_id: uuid.UUID) -> Optional[ActionEntity]: ...

    @abstractmethod
    async def get_by_idempotency_key(self, key: str, workspace_id: uuid.UUID) -> Optional[ActionEntity]: ...

    @abstractmethod
    async def update_status(self, action_id: uuid.UUID, status: str, result: Optional[dict] = None) -> None: ...
