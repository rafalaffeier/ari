from __future__ import annotations

import re
from datetime import date
from pathlib import Path


WORKSPACE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


def validate_workspace_id(workspace_id: str) -> str:
    if not WORKSPACE_RE.fullmatch(workspace_id):
        raise ValueError("workspace_id must be 1-64 chars and contain only letters, numbers, _ or -")
    return workspace_id


def journal_path(root: Path, workspace_id: str, day: date) -> Path:
    workspace = validate_workspace_id(workspace_id)
    return root / workspace / "journal" / f"{day:%Y}" / f"{day:%m}" / f"{day:%Y-%m-%d}.md"


def ensure_inside_root(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_root != resolved_path and resolved_root not in resolved_path.parents:
        raise ValueError("path escapes memory root")
    return resolved_path
