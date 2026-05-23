from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _catalog_path() -> Path:
    return Path(__file__).resolve().parents[3] / "shared" / "tools" / "catalog.json"


@lru_cache(maxsize=1)
def load_tool_catalog() -> list[dict[str, Any]]:
    with _catalog_path().open(encoding="utf-8") as file:
        return json.load(file)


def get_catalog_tool(name: str) -> dict[str, Any] | None:
    return next((tool for tool in load_tool_catalog() if tool["name"] == name), None)
