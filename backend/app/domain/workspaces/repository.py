from abc import ABC, abstractmethod
from typing import Optional, List
import uuid
from .entities import WorkspaceEntity


class WorkspaceRepository(ABC):

    @abstractmethod
    async def save(self, workspace: WorkspaceEntity) -> WorkspaceEntity: ...

    @abstractmethod
    async def get_by_id(self, workspace_id: uuid.UUID) -> Optional[WorkspaceEntity]: ...

    @abstractmethod
    async def list_for_user(self, user_id: uuid.UUID) -> List[WorkspaceEntity]: ...
