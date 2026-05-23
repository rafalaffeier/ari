"""
Secondary parser: validates that the parsed intent references a real tool.
"""
from .action_parser import ActionIntent
from app.tools.registry.registry import get_latest


def validate_intent(intent: ActionIntent) -> list[str]:
    """Returns a list of validation errors. Empty = valid."""
    errors = []

    if intent.tool in ("unknown", "clarify"):
        return []  # not an error — AI signalled uncertainty

    tool = get_latest(intent.tool)
    if not tool:
        errors.append(f"Tool '{intent.tool}' is not registered")
        return errors

    if intent.confidence < 0.75:
        errors.append(f"Confidence {intent.confidence:.2f} is below threshold 0.75")

    return errors
