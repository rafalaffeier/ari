"""
Domain entities for actions.
Pure Python — no SQLAlchemy, no FastAPI imports.
These represent the business concepts, not the DB rows.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid
from datetime import datetime


class ActionStatus(str, Enum):
    pending              = "pending"
    pending_confirmation = "pending_confirmation"
    confirmed            = "confirmed"
    rejected             = "rejected"
    queued               = "queued"
    running              = "running"
    done                 = "done"
    failed               = "failed"
    expired              = "expired"


class RiskLevel(str, Enum):
    low      = "low"
    medium   = "medium"
    high     = "high"
    critical = "critical"


@dataclass
class ActionEntity:
    tool_name:            str
    params:               dict
    workspace_id:         uuid.UUID
    user_id:              uuid.UUID
    id:                   uuid.UUID        = field(default_factory=uuid.uuid4)
    status:               ActionStatus     = ActionStatus.pending
    risk_level:           RiskLevel        = RiskLevel.low
    requires_confirmation: bool            = False
    confirmation_payload: Optional[dict]  = None
    device_id:            Optional[uuid.UUID] = None
    idempotency_key:      Optional[str]   = None
    result:               Optional[dict]  = None
    created_at:           datetime        = field(default_factory=datetime.utcnow)

    def needs_confirmation(self) -> bool:
        return self.requires_confirmation or self.risk_level in (RiskLevel.high, RiskLevel.critical)

    def can_retry(self, max_retries: int = 3, current_count: int = 0) -> bool:
        return self.status == ActionStatus.failed and current_count < max_retries
