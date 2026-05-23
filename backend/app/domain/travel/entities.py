from dataclasses import dataclass, field
from typing import Optional, List
from datetime import date
import uuid


@dataclass
class TravelSearchEntity:
    workspace_id:   uuid.UUID
    user_id:        uuid.UUID
    origin:         str
    destination:    str
    departure_date: date
    id:             uuid.UUID      = field(default_factory=uuid.uuid4)
    return_date:    Optional[date] = None
    passengers:     int            = 1
    budget:         Optional[float] = None
    preferences:    dict           = field(default_factory=dict)


@dataclass
class TravelResultEntity:
    travel_search_id: uuid.UUID
    provider:         str
    result_type:      str          # flight | hotel | package
    price:            float
    currency:         str
    booking_url:      str
    id:               uuid.UUID = field(default_factory=uuid.uuid4)
    score:            float     = 0.0
    raw_payload:      dict      = field(default_factory=dict)

    def is_within_budget(self, budget: Optional[float]) -> bool:
        return budget is None or self.price <= budget
