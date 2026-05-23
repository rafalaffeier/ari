"""
Parses raw AI output into a structured ActionIntent.
Includes repair logic for malformed JSON.
"""
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class ActionIntent:
    intent:     str
    tool:       str
    confidence: float
    params:     dict
    raw:        str


def parse(raw: str) -> ActionIntent:
    """
    Parse AI output. Raises ValueError if parsing fails after repair attempt.
    """
    text = raw.strip()

    # Attempt 1: direct parse
    try:
        data = json.loads(text)
        return _build(data, raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip markdown fences and retry
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        try:
            data = json.loads(text.strip())
            return _build(data, raw)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse AI output: {raw[:200]}")


def _build(data: dict, raw: str) -> ActionIntent:
    return ActionIntent(
        intent=data.get("intent", ""),
        tool=data.get("tool", "unknown"),
        confidence=float(data.get("confidence", 0.0)),
        params=data.get("params", {}),
        raw=raw,
    )
