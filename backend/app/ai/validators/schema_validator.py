"""
Validates tool params against the tool's JSON Schema.
"""
import jsonschema
from app.tools.registry.registry import get_latest


def validate_params(tool_name: str, params: dict) -> list[str]:
    """Returns validation errors. Empty = valid."""
    tool = get_latest(tool_name)
    if not tool:
        return [f"Unknown tool: {tool_name}"]
    if not tool.schema:
        return []
    try:
        jsonschema.validate(instance=params, schema=tool.schema)
        return []
    except jsonschema.ValidationError as e:
        return [e.message]
