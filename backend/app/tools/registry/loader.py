"""
Boot-time loader — registers every tool from the shared catalog.
Call this once at application startup.
"""

from app.domain.tools.entities import ToolEntity
from app.tools.catalog import load_tool_catalog

from .registry import register


def load_all_tools() -> None:
    for item in load_tool_catalog():
        register(
            ToolEntity(
                name=item["name"],
                version=item.get("version", "1.0"),
                scope=item["scope"],
                permission_key=item["permission_key"],
                risk_level=item.get("risk_level", "low"),
                requires_confirmation=item.get("requires_confirmation", False),
                retryable=item.get("retryable", False),
                max_retries=item.get("max_retries", 0),
                retry_backoff_seconds=item.get("retry_backoff_seconds", 5),
                schema=item.get("schema", {}),
            )
        )
