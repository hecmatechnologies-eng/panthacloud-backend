"""Tool registry (FR-064).

Optimize for Deletion: a tool is removable by deleting its module and its one registration line.
"""

from app.tools.base import Tool


class ToolNotFoundError(Exception):
    """No tool is registered under the requested name."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"No tool named {name!r} is registered.") from None

    def list(self) -> list[Tool]:
        return [self._tools[name] for name in sorted(self._tools)]

    def clear(self) -> None:
        self._tools.clear()


registry = ToolRegistry()
