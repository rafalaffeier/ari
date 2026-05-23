from __future__ import annotations

from typing import Optional

from app.models.action import RiskLevel
from app.tools.catalog import get_catalog_tool, load_tool_catalog


def _with_model_types(tool: dict) -> dict:
    item = dict(tool)
    item["risk_level"] = RiskLevel(item.get("risk_level", "low"))
    return item


def get_tool(name: str) -> Optional[dict]:
    tool = get_catalog_tool(name)
    return _with_model_types(tool) if tool else None


def list_tools() -> list:
    return [{"name": tool["name"], **_with_model_types(tool)} for tool in load_tool_catalog()]
