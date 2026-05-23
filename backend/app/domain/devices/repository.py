from abc import ABC, abstractmethod
from typing import Optional
import uuid
from .entities import DeviceEntity


class DeviceRepository(ABC):

    @abstractmethod
    async def save(self, device: DeviceEntity) -> DeviceEntity: ...

    @abstractmethod
    async def get_by_id(self, device_id: uuid.UUID) -> Optional[DeviceEntity]: ...

    @abstractmethod
    async def revoke(self, device_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def mark_online(self, device_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def mark_offline(self, device_id: uuid.UUID) -> None: ...
