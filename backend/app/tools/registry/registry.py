"""
Central tool registry.
All tools must be registered here before they can be used.
"""
from typing import Dict, Optional
from app.domain.tools.entities import ToolEntity

_registry: Dict[str, ToolEntity] = {}


def register(tool: ToolEntity) -> None:
    key = f"{tool.name}:{tool.version}"
    _registry[key] = tool


def get(name: str, version: str = "1.0") -> Optional[ToolEntity]:
    return _registry.get(f"{name}:{version}")


def get_latest(name: str) -> Optional[ToolEntity]:
    matches = [t for k, t in _registry.items() if t.name == name]
    return sorted(matches, key=lambda t: t.version, reverse=True)[0] if matches else None


def all_tools() -> list[ToolEntity]:
    return list(_registry.values())


def is_registered(name: str) -> bool:
    return any(t.name == name for t in _registry.values())
