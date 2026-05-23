from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolEntity:
    name:                 str
    version:              str
    scope:                str          # "backend" | "desktop"
    permission_key:       str
    risk_level:           str = "low"
    requires_confirmation: bool = False
    retryable:            bool = False
    max_retries:          int  = 0
    retry_backoff_seconds: int = 5
    schema:               dict = field(default_factory=dict)

    def is_desktop(self) -> bool:
        return self.scope == "desktop"

    def is_safe_to_retry(self) -> bool:
        return self.retryable and self.risk_level in ("low", "medium")
