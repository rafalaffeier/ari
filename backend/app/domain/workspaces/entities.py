from dataclasses import dataclass, field
from enum import Enum
import uuid
from datetime import datetime


class WorkspaceRole(str, Enum):
    owner  = "owner"
    admin  = "admin"
    member = "member"
    viewer = "viewer"


@dataclass
class WorkspaceEntity:
    name:          str
    owner_user_id: uuid.UUID
    id:            uuid.UUID  = field(default_factory=uuid.uuid4)
    created_at:    datetime   = field(default_factory=datetime.utcnow)

    def is_owner(self, user_id: uuid.UUID) -> bool:
        return self.owner_user_id == user_id
