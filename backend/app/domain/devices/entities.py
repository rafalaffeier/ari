from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid
from datetime import datetime


class DeviceStatus(str, Enum):
    online  = "online"
    offline = "offline"
    busy    = "busy"


class TrustLevel(str, Enum):
    low      = "low"
    standard = "standard"
    trusted  = "trusted"


@dataclass
class DeviceEntity:
    user_id:          uuid.UUID
    workspace_id:     uuid.UUID
    device_name:      str
    platform:         str
    agent_token_hash: str
    id:               uuid.UUID   = field(default_factory=uuid.uuid4)
    status:           DeviceStatus = DeviceStatus.offline
    trust_level:      TrustLevel  = TrustLevel.standard
    last_seen_at:     Optional[datetime] = None
    last_ping_at:     Optional[datetime] = None

    def is_online(self) -> bool:
        return self.status == DeviceStatus.online

    def can_execute_critical(self) -> bool:
        return self.trust_level == TrustLevel.trusted
