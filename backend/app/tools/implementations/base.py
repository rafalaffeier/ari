"""Base class all tool implementations must extend."""
from abc import ABC, abstractmethod
from app.domain.tools.entities import ToolEntity


class BaseTool(ABC):
    tool: ToolEntity  # must be set by subclass

    @abstractmethod
    async def execute(self, params: dict, context: dict) -> dict:
        """Execute the tool. Returns a result dict."""
        ...

    def validate_params(self, params: dict) -> None:
        """Raises ValueError if params don't match schema."""
        import jsonschema
        try:
            jsonschema.validate(instance=params, schema=self.tool.schema)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Invalid params for {self.tool.name}: {e.message}")
